#!/usr/bin/env python3
"""Claude Code PostToolUse hook: run ste scan on a Markdown file after Write or Edit.

When the file has STE errors, the hook writes the report to stderr and exits
with code 2. Claude Code then shows the report to the model, and the model
corrects the file. Set STE_HOOK_GLOBS to change the files that the hook checks
(default: "*.md,*.mdx").
"""
import fnmatch
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ste_simplify import check  # noqa: E402


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    path = (event.get("tool_input") or {}).get("file_path") or ""
    globs = [g.strip() for g in os.environ.get("STE_HOOK_GLOBS", "*.md,*.mdx").split(",") if g.strip()]
    if not path or not os.path.isfile(path) or not any(fnmatch.fnmatch(os.path.basename(path), g) for g in globs):
        return 0
    out = io.StringIO()
    old, sys.stdout = sys.stdout, out
    try:
        code = check.main(["--no-unknown", "--examples", "1", path])
    finally:
        sys.stdout = old
    if code == 1:
        sys.stderr.write("ste scan found STE errors. Correct them, then run ste scan again.\n")
        sys.stderr.write(out.getvalue())
        return 2
    if code == 2:
        sys.stderr.write(out.getvalue())
    return 0


if __name__ == "__main__":
    sys.exit(main())
