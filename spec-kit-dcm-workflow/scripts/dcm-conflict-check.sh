#!/usr/bin/env bash
# Cross-epic conflict check — compare active specs by domain/package overlap.
# Usage: dcm-conflict-check.sh --spec 009-widget-inactive-cluster [--json] [--repo-root /path]
#
# Fails CLOSED: if the candidate spec's scope (domains/packages) cannot be
# determined, the script errors out instead of pretending there is no overlap.
#
# Exit codes:
#   0  no overlap detected with other active epics (clean)
#   1  usage error: unknown arg, missing --spec, spec dir not found
#   2  overlap detected and acknowledgement required — in --json mode too, where the
#      report still reaches stdout. A gate that passes in one of its modes is not a
#      gate; a caller that only wants the data appends `|| true`.
#   3  scope UNDETERMINED — no domains resolvable from intake.json,
#      domain-scope.json or the registry entry. Never a pass.
#   4  registry present but unreadable, so active epics cannot be known. Never a pass.
#
# Registry path: multi_epic.registry_path in dcm-config.yml (lib-dcm-registry.sh).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SPEC=""
JSON_OUT=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --spec) SPEC="$2"; shift 2 ;;
    --json) JSON_OUT=true; shift ;;
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 --spec <spec-folder-name> [--json] [--repo-root PATH]"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$SPEC" ]]; then
  echo "ERROR: --spec required" >&2
  exit 1
fi

# shellcheck source=lib-dcm-registry.sh
. "$(dirname "$0")/lib-dcm-registry.sh"
REGISTRY="$(dcm_resolve_registry "$REPO_ROOT")"
SPEC_DIR="${REPO_ROOT}/specs/${SPEC}"

if [[ ! -d "$SPEC_DIR" ]]; then
  echo "ERROR: spec dir not found: $SPEC_DIR" >&2
  exit 1
fi

python3 - "$REGISTRY" "$SPEC_DIR" "$SPEC" "$JSON_OUT" <<'PY'
import json, re, sys
from pathlib import Path

registry_path = Path(sys.argv[1])
spec_dir = Path(sys.argv[2])
spec_name = sys.argv[3]
json_out = sys.argv[4].lower() == "true"

def load_json(path, default):
    """Best-effort load for optional scope files (missing/corrupt -> default)."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default


def load_registry_strict(path):
    """The registry is authoritative: a corrupt one is an error, never an empty set."""
    if not path.exists():
        return {"epics": []}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        die(
            4,
            "registry is not valid JSON: %s (%s)" % (path, exc),
            "Cannot determine which epics are active, so no overlap verdict is possible.",
        )
    if not isinstance(data, dict) or not isinstance(data.get("epics", []), list):
        die(
            4,
            "registry has an unexpected shape (expected an object with an "
            '"epics" list): %s' % path,
        )
    return data


def die(code, message, *details):
    """Report an error on stderr (plus a JSON error object in --json mode) and exit."""
    sys.stderr.write("ERROR: %s\n" % message)
    for d in details:
        sys.stderr.write("       %s\n" % d)
    if json_out:
        print(json.dumps({
            "spec": spec_name,
            "error": message,
            "details": list(details),
            "exit_code": code,
        }, indent=2))
    sys.exit(code)

def spec_num(name):
    m = re.match(r"^(\d{3})-", name)
    return m.group(1) if m else "000"

def load_domains_packages(base):
    intake = load_json(base / "intake.json", {})
    domain_scope = load_json(base / "domain-scope.json", {})
    domains = set()
    packages = set()

    tp = intake.get("ticket_plan") or {}
    for d in tp.get("ticket_domains") or []:
        domains.add(str(d).lower())

    for d in intake.get("domains") or []:
        domains.add(str(d).lower())

    ds = (
        domain_scope.get("domains")
        or domain_scope.get("active_domains")
        or domain_scope.get("in_scope_domains")
        or domain_scope.get("ticket_domains")
        or {}
    )
    if isinstance(ds, dict):
        for k, v in ds.items():
            if v is True or v == "active":
                domains.add(str(k).lower())
    elif isinstance(ds, list):
        domains.update(str(x).lower() for x in ds)

    pbd = domain_scope.get("packages_by_domain") or {}
    if isinstance(pbd, dict):
        for d, pkgs in pbd.items():
            domains.add(str(d).lower())
            for p in pkgs or []:
                packages.add(str(p).rstrip("/"))

    for p in intake.get("packages") or []:
        packages.add(str(p).rstrip("/"))

    spec_md = base / "spec.md"
    if spec_md.exists():
        for line in spec_md.read_text().splitlines():
            if "packages/" in line:
                for m in re.findall(r"packages/[a-zA-Z0-9_./-]+", line):
                    packages.add(m.rstrip("/"))

    return sorted(domains), sorted(packages)

def infer_domains_from_packages(packages):
    inferred = set()
    for p in packages:
        if "dcm-frontend" in p:
            inferred.add("frontend")
        if "dcm-backend" in p or "dcm-commons" in p:
            inferred.add("backend")
        if any(x in p for x in ("collector", "pipeline", "lambda-ingestion")):
            inferred.add("dataeng")
    return sorted(inferred)

def parse_merge_shared(base):
    ms = base / "merge-strategy.md"
    if not ms.exists():
        return []
    files = []
    in_table = False
    for line in ms.read_text().splitlines():
        if line.strip().startswith("| File"):
            in_table = True
            continue
        if in_table:
            if not line.strip().startswith("|"):
                in_table = False
                continue
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) >= 1 and cols[0] and cols[0] not in ("---", "File"):
                if not cols[0].startswith("-"):
                    files.append(cols[0])
    return files

def package_overlap(a, b):
    overlaps = []
    for pa in a:
        for pb in b:
            if pa == pb or pa.startswith(pb + "/") or pb.startswith(pa + "/"):
                overlaps.append(pa if len(pa) >= len(pb) else pb)
    return sorted(set(overlaps))

registry = load_registry_strict(registry_path)

current_domains, current_packages = load_domains_packages(spec_dir)
scope_sources = []
if current_domains or current_packages:
    scope_sources.append("specs/%s (intake.json/domain-scope.json/spec.md)" % spec_name)

# The registry may already record the scope (dispatched before intake.json landed).
own_entry = None
for e in registry.get("epics", []):
    if e.get("spec") == spec_name:
        own_entry = e
        break
if own_entry is not None:
    reg_domains = [str(d).lower() for d in own_entry.get("domains") or []]
    reg_packages = [str(p).rstrip("/") for p in own_entry.get("packages") or []]
    used_registry = False
    if not current_domains and reg_domains:
        current_domains = sorted(set(reg_domains))
        used_registry = True
    if not current_packages and reg_packages:
        current_packages = sorted(set(reg_packages))
        used_registry = True
    if used_registry:
        scope_sources.append(
            "%s entry for %s" % (registry_path.name, spec_name)
        )

# Last resort: infer domains from the package paths we do know about.
if not current_domains and current_packages:
    current_domains = infer_domains_from_packages(current_packages)
    if current_domains:
        scope_sources.append("inferred from package paths")

# Fail CLOSED: an undetermined scope is an error, never a "no overlap" pass.
if not current_domains:
    missing = []
    for fname in ("intake.json", "domain-scope.json"):
        if not (spec_dir / fname).exists():
            missing.append("missing %s" % (spec_dir / fname))
        else:
            missing.append("%s present but declares no domains" % (spec_dir / fname))
    if own_entry is None:
        missing.append("no entry for '%s' in %s" % (spec_name, registry_path))
    else:
        missing.append(
            "entry for '%s' in %s declares no domains" % (spec_name, registry_path)
        )
    die(
        3,
        "cannot determine domains/packages for spec '%s' — conflict check is "
        "INCONCLUSIVE (not clean)." % spec_name,
        *(missing + [
            "Create specs/%s/intake.json (domains + packages) or record the scope "
            "in the registry, then re-run." % spec_name,
        ])
    )

current_num = spec_num(spec_name)
current_shared = parse_merge_shared(spec_dir)

active = [
    e for e in registry.get("epics", [])
    if e.get("spec") != spec_name
    and e.get("status", "in_progress") in ("in_progress", "dispatched", "active")
]

conflicts = []
domain_overlaps = []
package_overlaps = []

for other in active:
    other_spec = other.get("spec", "?")
    other_domains = set(str(d).lower() for d in other.get("domains", []))
    other_packages = set(str(p).rstrip("/") for p in other.get("packages", []))

    shared_domains = sorted(set(current_domains) & other_domains)
    shared_packages = package_overlap(current_packages, list(other_packages))

    if shared_domains:
        domain_overlaps.append({
            "other_spec": other_spec,
            "other_epic_key": other.get("epic_key"),
            "shared_domains": shared_domains,
            "other_branches": other.get("branches", []),
        })

    if shared_packages:
        package_overlaps.append({
            "other_spec": other_spec,
            "other_epic_key": other.get("epic_key"),
            "shared_packages": shared_packages,
        })

    if shared_domains or shared_packages:
        severity = "high" if shared_packages else "medium"
        conflicts.append({
            "severity": severity,
            "other_spec": other_spec,
            "other_epic_key": other.get("epic_key"),
            "shared_domains": shared_domains,
            "shared_packages": shared_packages,
            "recommendation": (
                f"Coordinate merge order with {other_spec}; "
                f"update merge-strategy.md Shared files table"
            ),
        })

active_same_domain = len(domain_overlaps)
package_conflict = len(package_overlaps) > 0
requires_ack = (active_same_domain >= 1 or package_conflict) and len(active) >= 1

result = {
    "spec": spec_name,
    "spec_num": current_num,
    "domains": current_domains,
    "packages": current_packages,
    "scope_sources": scope_sources,
    "active_epic_count": len(active),
    "domain_overlap_count": active_same_domain,
    "requires_acknowledgement": requires_ack,
    "conflicts": conflicts,
    "domain_overlaps": domain_overlaps,
    "package_overlaps": package_overlaps,
    "merge_strategy_shared_files": current_shared,
}

if json_out:
    print(json.dumps(result, indent=2))
else:
    print("═══════════════════════════════════════════════════════════════")
    print("DCM Conflict Check — Multi-Epic")
    print("═══════════════════════════════════════════════════════════════")
    print(f"Spec: {spec_name} (#{current_num})")
    print(f"Domains: {', '.join(current_domains) or '(none)'}")
    print(f"Packages: {', '.join(current_packages) or '(none)'}")
    print(f"Scope source: {'; '.join(scope_sources)}")
    print(f"Other active epics: {len(active)}")
    print()

    if not conflicts:
        print("✅ No domain/package overlap with other active epics.")
    else:
        print("⚠️  Potential conflicts detected:")
        for c in conflicts:
            print(f"\n  vs {c['other_spec']} ({c.get('other_epic_key') or 'no jira key'})")
            if c["shared_domains"]:
                print(f"    Shared domains: {', '.join(c['shared_domains'])}")
            if c["shared_packages"]:
                print(f"    Shared packages: {', '.join(c['shared_packages'])}")
            print(f"    → {c['recommendation']}")

    if requires_ack:
        print()
        print("⚠️  MANDATORY: confirm merge-strategy.md cross-epic section before dispatch.")
        print("    Run with --dry-run first if 2+ epics share a domain.")

    print("═══════════════════════════════════════════════════════════════")

sys.exit(2 if requires_ack else 0)
PY
