import io
import json
import os
import sys
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skills", "ste-simplify", "scripts"))

from ste_simplify.check import Checker, load_allow  # noqa: E402
from ste_simplify.dictionary import Dictionary  # noqa: E402

FIXTURES = os.path.join(ROOT, "tests", "fixtures")
MINI = os.path.join(FIXTURES, "mini-dictionary.json")


def mini_dictionary():
    with open(MINI, encoding="utf-8") as f:
        return Dictionary(json.load(f))


def checker(allow=(), **opts):
    words, phrases = load_allow([os.path.join(FIXTURES, "allow.txt"), *allow])
    return Checker(mini_dictionary(), words, phrases, opts)


def check(text, ext=".md", **opts):
    return checker(**opts).check_text("t" + ext, text, ext)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def rules(findings):
    return [f.rule for f in findings]


def run_cli(main, args, stdin=None):
    out = io.StringIO()
    old_in = sys.stdin
    if stdin is not None:
        sys.stdin = io.StringIO(stdin)
    try:
        with redirect_stdout(out):
            code = main(["--dictionary", MINI, "--no-default-allow", *args])
    finally:
        sys.stdin = old_in
    return code, out.getvalue()
