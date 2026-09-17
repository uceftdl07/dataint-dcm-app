#!/usr/bin/env python3
"""Merge the DCM hook + permission fragment into .claude/settings.json.

    merge_claude_settings.py <.claude/settings.json> <claude-code/settings.json>

Merge, never overwrite: settings.json is shared with the contributor's own
permissions and hooks. DCM hook entries are matched by the script name and
replaced, so re-running cannot stack duplicates.

Exit 1 = settings.json is unreadable and was left untouched (the Claude gate is
not active; the git pre-commit hook still is).
"""
import json
import sys
from pathlib import Path

MARK = "dcm-before-commit-review.sh"


def is_dcm(entry):
    return any(MARK in (h.get("command") or "") for h in entry.get("hooks", []))


def main(dest_path, frag_path):
    frag = json.loads(frag_path.read_text(encoding="utf-8"))

    dest = {}
    if dest_path.exists():
        try:
            dest = json.loads(dest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print("    ✗ .claude/settings.json is not valid JSON (%s) — not touched." % exc,
                  file=sys.stderr)
            print("      Fix it or move it aside, then re-run.", file=sys.stderr)
            return 1

    hooks = dest.setdefault("hooks", {})
    for event, entries in frag.get("hooks", {}).items():
        hooks[event] = [e for e in hooks.get(event, []) if not is_dcm(e)] + entries

    allow = dest.setdefault("permissions", {}).setdefault("allow", [])
    added = [rule for rule in frag.get("permissions", {}).get("allow", []) if rule not in allow]
    allow.extend(added)

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(json.dumps(dest, indent=2) + "\n", encoding="utf-8")
    print("    → .claude/settings.json merged (PreToolUse gate + %d new permission rule(s))"
          % len(added))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
