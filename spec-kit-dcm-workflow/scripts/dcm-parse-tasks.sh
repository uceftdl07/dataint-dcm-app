#!/usr/bin/env bash
# Deterministic parser for specs/<spec>/tasks.md — the single source of truth for
# task_id / status / domain / slug / branch, so no agent re-derives a branch name
# and gets a different answer each run. Full contract: CONTRACTS.md.
#
# Usage: dcm-parse-tasks.sh --spec <spec-folder-name> [--json] [--repo-root PATH]
#   --spec        folder name (009-widget-inactive-cluster) or a repo-relative path;
#                 a bare name is looked up in specs/ then spec-kit-dcm-workflow/specs/
#   --json        one JSON object on stdout
#   --repo-root   default: two levels above this script
#
# Default output — TAB separated, data lines only, so a caller can do
#   while IFS=$'\t' read -r id status domain slug branch sub title; do
#   task_id <TAB> status <TAB> domain <TAB> slug <TAB> branch <TAB> sub_spec <TAB> title
# sub_spec is "-" when the line references none; summary and warnings go to stderr.
#
# Exit codes:
#   0  at least one task parsed
#   1  usage error: unknown arg, missing --spec, spec dir or tasks.md not found
#   2  tasks.md exists but contains ZERO conforming lines — FORMAT DIVERGENCE.
#      Never reported as "0 tasks": a caller would read that as "nothing to dispatch".
#   3  git.domains or git.child_branch_pattern unreadable — fail closed, nothing
#      is hardcoded silently.
#
# Recognised line, marker [ ] pending · [~] in_progress · [x]/[X] completed:
#   - [ ] T001 Frontend inactive cluster widget → [stories/T001-x.md](stories/T001-x.md)
# Bold ids and leading bracket tags ([P], [US1], `[DataEng][P]`) are tolerated —
# real files in this repo use all three shapes. Any other marker is skipped with a
# warning, never silently "pending"; on a duplicate id the first occurrence wins.
#
# domain  a leading tag naming a known domain wins, else the first title word,
#         validated against git.domains — unrecognised → misc AND a warning.
# slug    title minus its first word ONLY when that word is the domain (else kept:
#         dropping it would lose title information), ASCII-folded, [^a-z0-9] → "-",
#         capped at SLUG_MAX_LEN on a word boundary, empty → task id + a warning.
# branch  git.child_branch_pattern, never hardcoded; spec_num = the folder's
#         leading 3 digits, else "000" + a warning.
# title   sub-spec ref and Jira key extracted — project.key only, a generic
#         [A-Z]+-\d+ would eat ids like FR-011 — inline branch refs and markdown
#         noise dropped.
#
# Config, first readable wins: .specify/extensions/dcm/dcm-config.yml then
# spec-kit-dcm-workflow/dcm-config.template.yml. Minimal reader — yq not required.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SPEC=""
JSON_OUT=false

usage() {
  echo "Usage: $0 --spec <spec-folder-name> [--json] [--repo-root PATH]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --spec) SPEC="${2:-}"; shift 2 ;;
    --json) JSON_OUT=true; shift ;;
    --repo-root) REPO_ROOT="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "$SPEC" ]]; then
  echo "ERROR: --spec required" >&2
  usage >&2
  exit 1
fi

if [[ ! -d "$REPO_ROOT" ]]; then
  echo "ERROR: repo root not found: $REPO_ROOT" >&2
  exit 1
fi

# So --spec specs/009-x/ behaves like specs/009-x
SPEC="${SPEC%/}"

# Explicit path, then specs/, then the workflow's own specs/
SPEC_DIR=""
if [[ "$SPEC" == */* ]]; then
  [[ -d "$REPO_ROOT/$SPEC" ]] && SPEC_DIR="$REPO_ROOT/$SPEC"
else
  if [[ -d "$REPO_ROOT/specs/$SPEC" ]]; then
    SPEC_DIR="$REPO_ROOT/specs/$SPEC"
  elif [[ -d "$REPO_ROOT/spec-kit-dcm-workflow/specs/$SPEC" ]]; then
    SPEC_DIR="$REPO_ROOT/spec-kit-dcm-workflow/specs/$SPEC"
  fi
fi

if [[ -z "$SPEC_DIR" ]]; then
  echo "ERROR: spec dir not found for --spec '$SPEC'" >&2
  echo "       looked in $REPO_ROOT/specs/ and $REPO_ROOT/spec-kit-dcm-workflow/specs/" >&2
  exit 1
fi

TASKS_FILE="$SPEC_DIR/tasks.md"
if [[ ! -f "$TASKS_FILE" ]]; then
  echo "ERROR: tasks.md not found: $TASKS_FILE" >&2
  echo "       run /speckit.dcm.tasks for this spec before parsing." >&2
  exit 1
fi

CONFIG_FILE=""
for candidate in \
  "$REPO_ROOT/.specify/extensions/dcm/dcm-config.yml" \
  "$REPO_ROOT/spec-kit-dcm-workflow/dcm-config.template.yml"
do
  if [[ -f "$candidate" ]]; then
    CONFIG_FILE="$candidate"
    break
  fi
done

if [[ -z "$CONFIG_FILE" ]]; then
  echo "ERROR: no dcm-config found — looked for" >&2
  echo "       .specify/extensions/dcm/dcm-config.yml" >&2
  echo "       spec-kit-dcm-workflow/dcm-config.template.yml" >&2
  exit 3
fi

python3 - "$REPO_ROOT" "$SPEC_DIR" "$TASKS_FILE" "$CONFIG_FILE" "$JSON_OUT" <<'PY'
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

repo_root = Path(sys.argv[1])
spec_dir = Path(sys.argv[2])
tasks_file = Path(sys.argv[3])
config_file = Path(sys.argv[4])
json_out = sys.argv[5].lower() == "true"

SLUG_MAX_LEN = 40
DEFAULT_STATUS_BY_MARKER = {" ": "pending", "~": "in_progress", "x": "completed", "X": "completed"}

warnings = []


def warn(msg):
    warnings.append(msg)
    sys.stderr.write("WARN: %s\n" % msg)


def rel(path):
    try:
        return str(Path(path).relative_to(repo_root))
    except ValueError:
        return str(path)


def die(code, message, *details):
    """stderr always; in --json mode also emit an error object on stdout."""
    sys.stderr.write("ERROR: %s\n" % message)
    for d in details:
        sys.stderr.write("       %s\n" % d)
    if json_out:
        print(json.dumps({
            "spec": spec_dir.name,
            "tasks_file": rel(tasks_file),
            "error": message,
            "details": list(details),
            "exit_code": code,
            "tasks": [],
        }, indent=2, ensure_ascii=False))
    sys.exit(code)


# Minimal indentation-based YAML reader — no yq, no PyYAML.
def read_block(path, key):
    """Return the raw lines of a top-level `<key>:` mapping."""
    block = []
    inside = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not inside:
            if re.match(r"^%s:\s*(#.*)?$" % re.escape(key), raw):
                inside = True
            continue
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            block.append(raw)
            continue
        if not raw[:1].isspace():   # back to column 0 → end of the git: mapping
            break
        block.append(raw)
    return block


def scalar(line):
    value = line.split(":", 1)[1]
    value = re.sub(r"\s+#.*$", "", value).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return value


git_block = read_block(config_file, "git")
branch_pattern = ""
domains = []
in_domains = False
for line in git_block:
    stripped = line.strip()
    if in_domains:
        if stripped.startswith("- "):
            domains.append(scalar("x:" + stripped[2:]))
            continue
        in_domains = False
    if re.match(r"^child_branch_pattern\s*:", stripped):
        branch_pattern = scalar(stripped)
    elif re.match(r"^domains\s*:\s*(#.*)?$", stripped):
        in_domains = True

domains = [d.lower() for d in domains if d]
if not domains:
    die(3, "git.domains is empty or unreadable in %s" % rel(config_file),
        "The domain list is authoritative — refusing to hardcode a fallback.")
if not branch_pattern:
    die(3, "git.child_branch_pattern is missing in %s" % rel(config_file),
        'Expected e.g. child_branch_pattern: "{domain}/{spec_num}-{slug}"')

project_key = ""
for line in read_block(config_file, "project"):
    stripped = line.strip()
    if re.match(r"^key\s*:", stripped):
        project_key = scalar(stripped)
        break
if not project_key:
    warn("project.key not found in %s — Jira keys will not be extracted from "
         "task titles (a generic [A-Z]+-nnn pattern would eat ids like FR-011)"
         % rel(config_file))

spec_name = spec_dir.name
m = re.match(r"^(\d{3})", spec_name)
if m:
    spec_num = m.group(1)
else:
    spec_num = "000"
    warn("spec folder '%s' has no leading 3-digit number — spec_num=000" % spec_name)

TASK_RE = re.compile(r"^\s*[-*]\s+\[(.)\]\s+(?:\*\*|__)?(T\d{3,})(?:\*\*|__)?\s*(.*)$")
TAG_RE = re.compile(r"^\s*`?\[([A-Za-z0-9\[\]|,/+.\- ]{1,40}?)\]`?")
RANGE_RE = re.compile(r"^\s*[-–—]\s*(T\d{3,})")
SUBSPEC_LINK_RE = re.compile(r"\[[^\]]*\]\(\s*(?:\./)?(stories/[^)\s]+\.md)\s*\)")
SUBSPEC_BARE_RE = re.compile(r"`?(?:\./)?(stories/[^\s`)\]\"']+\.md)`?")
BRANCHREF_RE = re.compile(r"`([A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+)`")
if project_key:
    JIRA_LINK_RE = re.compile(r"\[(%s-\d+)\]\([^)]*\)" % re.escape(project_key))
    JIRA_BARE_RE = re.compile(r"\b(%s-\d+)\b" % re.escape(project_key))
else:
    JIRA_LINK_RE = None
    JIRA_BARE_RE = None
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
GLYPH_RE = re.compile(r"[☐☑☒✅]")

branch_prefixes = tuple(list(domains) + ["feature", "feat", "fix", "hotfix", "release", "chore"])


def slugify(text):
    # Non-ASCII dashes (Pd) and math symbols (Sm) are word SEPARATORS: a space
    # before folding, else "N1–N3" gives "n1n3". Other non-ASCII is folded.
    text = "".join(
        " " if (ord(c) > 127 and unicodedata.category(c) in ("Pd", "Sm")) else c
        for c in text
    )
    ascii_text = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in ascii_text if not unicodedata.combining(c))
    ascii_text = ascii_text.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
    ascii_text = re.sub(r"-{2,}", "-", ascii_text).strip("-")
    if len(ascii_text) > SLUG_MAX_LEN:
        cut = ascii_text[:SLUG_MAX_LEN]
        # cut landed inside a word → drop the trailing partial word
        if ascii_text[SLUG_MAX_LEN] != "-" and "-" in cut:
            cut = cut.rsplit("-", 1)[0]
        ascii_text = cut.strip("-") or ascii_text[:SLUG_MAX_LEN].strip("-")
    return ascii_text


def clean_title(remainder):
    """Return (title, sub_spec, jira_key). Order matters — see the header."""
    text = remainder
    sub_spec = None

    m_link = SUBSPEC_LINK_RE.search(text)
    if m_link:
        sub_spec = m_link.group(1)
        text = text[:m_link.start()] + " " + text[m_link.end():]
    m_bare = SUBSPEC_BARE_RE.search(text)
    while m_bare:
        if sub_spec is None:
            sub_spec = m_bare.group(1)
        text = text[:m_bare.start()] + " " + text[m_bare.end():]
        m_bare = SUBSPEC_BARE_RE.search(text)

    # backticked inline branch reference — noise, not title text
    for m_branch in list(BRANCHREF_RE.finditer(text)):
        if m_branch.group(1).lower().startswith(branch_prefixes):
            text = text.replace(m_branch.group(0), " ")

    jira_key = None
    if JIRA_LINK_RE is not None:
        m_jira = JIRA_LINK_RE.search(text)
        if m_jira:
            jira_key = m_jira.group(1)
            text = text[:m_jira.start()] + " " + text[m_jira.end():]
        for m_jira in list(JIRA_BARE_RE.finditer(text)):
            if jira_key is None:
                jira_key = m_jira.group(1)
            text = text.replace(m_jira.group(0), " ")

    text = MD_LINK_RE.sub(r"\1", text)
    text = text.replace("**", "").replace("`", "").replace("\\_", "_").replace("\\", "")
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip(" -:–—→·")
    text = re.sub(r"\s+", " ", text).strip()
    return text, sub_spec, jira_key


tasks = []
seen = {}
bad_markers = 0
glyph_lines = 0
table_task_rows = 0

for lineno, raw in enumerate(tasks_file.read_text(encoding="utf-8").splitlines(), start=1):
    if GLYPH_RE.search(raw):
        glyph_lines += 1
    if raw.lstrip().startswith("|") and re.search(r"\|\s*(T\d{3,})\s*\|", raw):
        table_task_rows += 1

    m = TASK_RE.match(raw)
    if not m:
        continue
    marker, task_id, remainder = m.group(1), m.group(2), m.group(3)
    status = DEFAULT_STATUS_BY_MARKER.get(marker)
    if status is None:
        bad_markers += 1
        warn("%s:%d unknown checkbox marker '[%s]' for %s — line skipped "
             "(expected [ ], [~] or [x])" % (rel(tasks_file), lineno, marker, task_id))
        continue

    if task_id in seen:
        warn("%s:%d duplicate task id %s (first seen line %d) — line skipped"
             % (rel(tasks_file), lineno, task_id, seen[task_id]))
        continue
    seen[task_id] = lineno

    # id range such as "T001–T004" → only the first id is a real task
    m_range = RANGE_RE.match(remainder)
    if m_range:
        warn("%s:%d %s looks like an id RANGE up to %s — only %s is parsed"
             % (rel(tasks_file), lineno, task_id, m_range.group(1), task_id))
        remainder = remainder[m_range.end():]

    # leading bracket tags: [P], [US1], [DataEng], `[DataEng][P]`
    tags = []
    while True:
        m_tag = TAG_RE.match(remainder)
        if not m_tag:
            break
        tags.extend(p.strip() for p in re.split(r"\]\s*\[", m_tag.group(1)))
        remainder = remainder[m_tag.end():]

    title, sub_spec, jira_key = clean_title(remainder)

    domain = None
    domain_source = None
    for tag in tags:
        if tag.lower() in domains:
            domain = tag.lower()
            domain_source = "tag"
            break

    words = title.split()
    first_word_is_domain = False
    if domain is None:
        candidate = re.sub(r"[^a-z0-9]", "", words[0].lower()) if words else ""
        if candidate in domains:
            domain = candidate
            domain_source = "first_word"
            first_word_is_domain = True
        else:
            domain = "misc"
            domain_source = "fallback_misc"
            warn("%s:%d %s first word %r is not a known domain (%s) — domain=misc"
                 % (rel(tasks_file), lineno, task_id,
                    words[0] if words else "", ", ".join(domains)))

    slug_source = " ".join(words[1:]) if first_word_is_domain else " ".join(words)
    slug = slugify(slug_source)
    if not slug:
        slug = task_id.lower()
        warn("%s:%d %s produced an empty slug from title %r — slug=%s"
             % (rel(tasks_file), lineno, task_id, title, slug))

    branch = (branch_pattern
              .replace("{domain}", domain)
              .replace("{spec_num}", spec_num)
              .replace("{slug}", slug))
    leftover = re.findall(r"\{([a-z_]+)\}", branch)
    if leftover:
        warn("%s: unsupported placeholder(s) %s left in branch %r "
             "(known: {domain} {spec_num} {slug})"
             % (rel(config_file), ", ".join(sorted(set(leftover))), branch))

    sub_spec_exists = bool(sub_spec) and (spec_dir / sub_spec).is_file()
    if sub_spec and not sub_spec_exists:
        warn("%s:%d %s references sub-spec %s which is not on disk"
             % (rel(tasks_file), lineno, task_id, sub_spec))

    tasks.append({
        "task_id": task_id,
        "title": title,
        "status": status,
        "domain": domain,
        "domain_source": domain_source,
        "slug": slug,
        "branch": branch,
        "sub_spec": sub_spec,
        "sub_spec_exists": sub_spec_exists,
        "jira_key": jira_key,
        "tags": tags,
        "line": lineno,
    })

# Format divergence — refuse to report "0 tasks".
if not tasks:
    details = [
        'expected checkbox lines: "- [ ] T001 Frontend <title>"    (pending)',
        '                         "- [~] T002 Backend <title>"     (in_progress)',
        '                         "- [x] T003 DataEng <title>"     (completed)',
    ]
    if table_task_rows or glyph_lines:
        details.append(
            "detected instead: markdown table with %d T00X row(s) and %d glyph status "
            "marker(s) (☐ / ☑ / ✅) — same shape as "
            "specs/010-databricks-usage-finops-curated/tasks.md"
            % (table_task_rows, glyph_lines))
    if bad_markers:
        details.append("%d line(s) had a T00X id but an unrecognised marker" % bad_markers)
    details.append("This is NOT an empty task list: refusing to exit 0 with zero tasks, "
                   "a caller would read that as \"nothing to dispatch\".")
    details.append("Fix: convert tasks.md to the checkbox format "
                   "(spec-kit-dcm-workflow/commands/tasks.md) or pass the right --spec.")
    die(2, "no conforming task line in %s" % rel(tasks_file), *details)

counts = {
    "total": len(tasks),
    "pending": sum(1 for t in tasks if t["status"] == "pending"),
    "in_progress": sum(1 for t in tasks if t["status"] == "in_progress"),
    "completed": sum(1 for t in tasks if t["status"] == "completed"),
}

if json_out:
    print(json.dumps({
        "spec": spec_name,
        "spec_num": spec_num,
        "spec_dir": rel(spec_dir),
        "tasks_file": rel(tasks_file),
        "config_file": rel(config_file),
        "branch_pattern": branch_pattern,
        "domains": domains,
        "slug_max_len": SLUG_MAX_LEN,
        "counts": counts,
        "warnings": warnings,
        "tasks": tasks,
    }, indent=2, ensure_ascii=False))
else:
    for t in tasks:
        print("\t".join([
            t["task_id"], t["status"], t["domain"], t["slug"], t["branch"],
            t["sub_spec"] or "-", t["title"],
        ]))

sys.stderr.write(
    "dcm-parse-tasks: %s — %d task(s) (pending=%d in_progress=%d completed=%d), "
    "pattern %s, %d warning(s)\n"
    % (rel(tasks_file), counts["total"], counts["pending"], counts["in_progress"],
       counts["completed"], branch_pattern, len(warnings)))
PY
