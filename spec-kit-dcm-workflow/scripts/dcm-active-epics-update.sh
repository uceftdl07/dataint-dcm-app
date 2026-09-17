#!/usr/bin/env bash
# Update the multi-epic team registry after dispatch (idempotent merge).
# Path comes from multi_epic.registry_path in dcm-config.yml (see lib-dcm-registry.sh).
# Usage: dcm-active-epics-update.sh --spec NAME --title "..." --domains d1,d2 \
#        --packages pkg1,pkg2 --branches b1,b2 [--epic-key DCINT-200] [--status in_progress]
#
# Read-modify-write under flock(<registry>.lock) + atomic replace, so a crash or two
# concurrent updates cannot truncate the file or drop an epic.
#
# Exit codes:
#   0  registry updated
#   1  usage error (unknown arg, missing --spec)
#   3  registry present but not valid JSON — copied aside as <registry>.corrupt-<n>,
#      nothing written. Fix or restore the file, then re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=lib-dcm-registry.sh
. "$(dirname "$0")/lib-dcm-registry.sh"
REGISTRY="$(dcm_resolve_registry "$REPO_ROOT")"
SPEC=""
TITLE=""
DOMAINS=""
PACKAGES=""
BRANCHES=""
EPIC_KEY=""
STATUS="in_progress"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --spec) SPEC="$2"; shift 2 ;;
    --title) TITLE="$2"; shift 2 ;;
    --domains) DOMAINS="$2"; shift 2 ;;
    --packages) PACKAGES="$2"; shift 2 ;;
    --branches) BRANCHES="$2"; shift 2 ;;
    --epic-key) EPIC_KEY="$2"; shift 2 ;;
    --status) STATUS="$2"; shift 2 ;;
    --repo-root) REPO_ROOT="$2"; REGISTRY="$(dcm_resolve_registry "$REPO_ROOT")"; shift 2 ;;
    --complete) STATUS="completed"; shift ;;
    -h|--help)
      echo "Usage: $0 --spec NAME [--title T] [--domains a,b] [--packages p1,p2] [--branches b1,b2] [--epic-key KEY] [--status S|--complete]"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$SPEC" ]]; then
  echo "ERROR: --spec required" >&2
  exit 1
fi

mkdir -p "$(dirname "$REGISTRY")"

python3 - "$REGISTRY" "$SPEC" "$TITLE" "$DOMAINS" "$PACKAGES" "$BRANCHES" "$EPIC_KEY" "$STATUS" <<'PY'
import fcntl, json, os, re, shutil, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

registry_path = Path(sys.argv[1])
spec = sys.argv[2]
title = sys.argv[3]
domains_raw = sys.argv[4]
packages_raw = sys.argv[5]
branches_raw = sys.argv[6]
epic_key = sys.argv[7]
status = sys.argv[8]

def split_csv(s):
    return [x.strip() for x in s.split(",") if x.strip()] if s else []

m = re.match(r"^(\d{3})-", spec)
spec_num = m.group(1) if m else "000"

def preserve_corrupt(path):
    """Copy a corrupt registry aside so nothing is lost. Returns the backup path."""
    n = 1
    while True:
        candidate = Path(str(path) + ".corrupt-%d" % n)
        if not candidate.exists():
            break
        n += 1
    shutil.copy2(str(path), str(candidate))
    return candidate


def atomic_write_json(path, payload):
    """Write JSON to a temp file in the same dir, fsync, then os.replace() it."""
    directory = path.parent
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(directory)
    )
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(payload, indent=2) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, str(path))
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# Lock held for the whole read-modify-write, so updates serialise.
lock_path = Path(str(registry_path) + ".lock")
lock_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
fcntl.flock(lock_fd, fcntl.LOCK_EX)

if registry_path.exists():
    raw = registry_path.read_text()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        backup = preserve_corrupt(registry_path)
        sys.stderr.write(
            "ERROR: registry is not valid JSON: %s\n"
            "       %s\n"
            "       The file was NOT modified; a copy was preserved at:\n"
            "         %s\n"
            "       Refusing to reset the registry (that would drop every "
            "recorded epic).\n"
            "       Fix the JSON (or restore from git / the copy above), then "
            "re-run this command.\n" % (registry_path, exc, backup)
        )
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        sys.exit(3)
    if not isinstance(data, dict) or not isinstance(data.get("epics", []), list):
        backup = preserve_corrupt(registry_path)
        sys.stderr.write(
            "ERROR: registry has an unexpected shape (expected an object with an "
            "\"epics\" list): %s\n"
            "       The file was NOT modified; a copy was preserved at:\n"
            "         %s\n" % (registry_path, backup)
        )
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        sys.exit(3)
else:
    # Only a genuinely absent registry may be initialised from scratch.
    data = {"epics": []}

now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
entry = {
    "spec": spec,
    "spec_num": spec_num,
    "title": title or spec,
    "domains": split_csv(domains_raw),
    "packages": split_csv(packages_raw),
    "branches": split_csv(branches_raw),
    "status": status,
    "updated_at": now,
}
if epic_key:
    entry["epic_key"] = epic_key
    entry["dispatched_at"] = now

epics = data.get("epics", [])
found = False
for i, e in enumerate(epics):
    if e.get("spec") == spec:
        merged = {**e, **entry}
        if not epic_key and e.get("epic_key"):
            merged["epic_key"] = e["epic_key"]
        if not title and e.get("title"):
            merged["title"] = e["title"]
        if not split_csv(branches_raw) and e.get("branches"):
            merged["branches"] = e["branches"]
        if not split_csv(domains_raw) and e.get("domains"):
            merged["domains"] = e["domains"]
        if not split_csv(packages_raw) and e.get("packages"):
            merged["packages"] = e["packages"]
        epics[i] = merged
        found = True
        break

if not found:
    entry.setdefault("dispatched_at", now)
    epics.append(entry)

data["epics"] = epics
data["updated_at"] = now

try:
    atomic_write_json(registry_path, data)
finally:
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    os.close(lock_fd)

print(f"Updated {registry_path} — spec={spec} status={status} ({len(epics)} epics)")
PY
