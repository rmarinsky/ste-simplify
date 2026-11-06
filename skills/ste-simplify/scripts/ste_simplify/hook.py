"""ste hook: a Claude Code hook that examines plans and instruction files.

Claude Code sends the event as JSON to stdin.

- PreToolUse on ExitPlanMode: the hook examines the plan. If the plan has STE
  errors, the hook exits with code 2. Claude Code then does not show the plan,
  and Claude must write the plan again.
- PostToolUse on Write, Edit and MultiEdit: the hook examines only instruction
  files (STE_HOOK_GLOBS) and only the lines that changed. If these lines have
  STE errors, the hook exits with code 2 and gives the report to Claude.

A plan with more than 20% Cyrillic letters is blocked: the plan must be in English.
The hook does not examine files with more than 20% Cyrillic letters. After three
reports for the same plan or file in one session, the hook stops and tells the user.
"""
import argparse
import fnmatch
import hashlib
import io
import json
import os
import sys

from . import check
from .dictionary import MissingDictionary
from .report import cache_dir

INSTRUCTION_FILES = "SKILL.md,AGENTS.md,CLAUDE.md,*.mdc,*/agents/*.md,*/commands/*.md"
MAX_REPORTS = 3


def is_instruction_file(path, globs):
    p = path.replace(os.sep, "/")
    return any(fnmatch.fnmatch(os.path.basename(p), g) or fnmatch.fnmatch(p, g) for g in globs)


def english(text):
    letters = [c for c in text if c.isalpha()]
    cyrillic = sum(1 for c in letters if "Ѐ" <= c <= "ӿ")
    return bool(letters) and cyrillic / len(letters) < 0.2


def changed_lines(event, text):
    """Line numbers that the edit wrote. None means all lines (Write)."""
    ti = event.get("tool_input") or {}
    if event.get("tool_name") == "Write":
        return None
    news = [ti.get("new_string")] if "new_string" in ti else [e.get("new_string") for e in ti.get("edits") or []]
    lines = set()
    for s in news:
        i = text.find(s) if s else -1
        if i >= 0:
            start = text.count("\n", 0, i) + 1
            lines.update(range(start, start + s.count("\n") + 1))
    return lines


def count_report(key, clean):
    """Count the reports for this key. The result is True at the limit."""
    d = os.path.join(cache_dir(), "hook")  # a folder of the user, not the shared /tmp
    f = os.path.join(d, hashlib.sha1(key.encode()).hexdigest())
    if clean:
        if os.path.exists(f):
            os.remove(f)
        return False
    os.makedirs(d, mode=0o700, exist_ok=True)
    try:
        with open(f) as fh:
            n = int(fh.read() or 0)
    except (OSError, ValueError):
        n = 0
    fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(str(n + 1))
    return n >= MAX_REPORTS


def main(argv=None, prog="ste hook"):
    ap = argparse.ArgumentParser(prog=prog, description=__doc__.split("\n")[0])
    ap.add_argument("--dictionary", metavar="FILE")
    a = ap.parse_args(argv)
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    tool, ti = event.get("tool_name"), event.get("tool_input") or {}
    if tool == "ExitPlanMode":
        name, text, ext, lines = "plan", ti.get("plan") or "", ".md", None
        where = event.get("cwd") or "."
        intro = ("ste: the plan has STE errors. Write these sentences of the plan again in STE, "
                 "then call ExitPlanMode again. Do not change code, commands, paths or names.\n")
    elif tool in ("Write", "Edit", "MultiEdit"):
        name = where = ti.get("file_path") or ""
        globs = [g.strip() for g in os.environ.get("STE_HOOK_GLOBS", INSTRUCTION_FILES).split(",") if g.strip()]
        if not name or not os.path.isfile(name) or not is_instruction_file(name, globs):
            return 0
        with open(name, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        ext, lines = os.path.splitext(name)[1], changed_lines(event, text)
        if lines is not None and not lines:
            return 0
        intro = "ste: the lines that you wrote have STE errors. Correct only these lines.\n"
    else:
        return 0
    if not english(text):
        if tool != "ExitPlanMode":
            return 0
        if count_report(f"{event.get('session_id', '')}:plan-language", clean=False):
            return 0
        sys.stderr.write("ste: write the plan in English, in STE. Then call ExitPlanMode again. "
                         "You can write the chat replies in the language of the user.\n")
        return 2
    p = argparse.ArgumentParser()
    check.add_common_args(p)
    opts = p.parse_args([where] + (["--dictionary", a.dictionary] if a.dictionary else []))
    opts.no_unknown = True
    try:
        checker = check.make_checker(opts)
    except MissingDictionary:
        return 0
    errors = [f for f in checker.check_text(name, text, ext)
              if f.severity == "error" and (lines is None or f.line in lines)]
    key = f"{event.get('session_id', '')}:{name}"
    if count_report(key, clean=not errors):
        json.dump({"systemMessage": f"ste: {len(errors)} STE errors stay in {name}. "
                                    f"The hook stopped after {MAX_REPORTS} reports."}, sys.stdout)
        return 0
    if not errors:
        return 0
    out = io.StringIO()
    check.report_text([(name, errors)], out, examples=1, show_unknown=False)
    sys.stderr.write(intro + out.getvalue())
    return 2


if __name__ == "__main__":
    sys.exit(main())
