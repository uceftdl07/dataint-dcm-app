#!/usr/bin/env python3
"""Refresh the managed DCM block in CLAUDE.md, keeping the rest of the file.

    update_claude_md.py <CLAUDE.md> <claude-code/CLAUDE.template.md> <version>

CLAUDE.md is gitignored in this repo (company policy on agent files), so it is
generated like the rest of the .claude layer. The BEGIN/END markers are what let
a contributor keep their own notes in the same file across re-runs.
"""
import sys
from pathlib import Path

BEGIN = "<!-- BEGIN dcm-workflow (généré par sync-dcm-extension.sh — ne pas éditer) -->"
END = "<!-- END dcm-workflow -->"


def main(dest, tpl, version):
    body = tpl.read_text(encoding="utf-8").replace("{DCM_VERSION}", version).rstrip()
    block = "%s\n%s\n%s\n" % (BEGIN, body, END)

    if not dest.exists():
        dest.write_text("# CLAUDE.md\n\n%s" % block, encoding="utf-8")
        print("    → CLAUDE.md created")
        return 0

    text = dest.read_text(encoding="utf-8")
    if BEGIN in text and END in text:
        head, rest = text.split(BEGIN, 1)
        _, tail = rest.split(END, 1)
        dest.write_text(head + block.rstrip() + tail, encoding="utf-8")
        print("    → CLAUDE.md DCM block updated (your own content preserved)")
    else:
        sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        dest.write_text(text + sep + block, encoding="utf-8")
        print("    → CLAUDE.md DCM block appended (your own content preserved)")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]))
