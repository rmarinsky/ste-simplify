"""ste fix: a replacement plan, and the safe one-to-one replacements.

A replacement is safe when the dictionary gives exactly one alternative, with
the same part of speech, for a word in its base form. All other findings go
into a list of sentences that a person or a model must write again.

Usage examples:
  ste fix docs/                       show the numbered plan, change nothing
  ste fix --apply docs/               apply all safe replacements
  ste fix --apply --skip 2,5 docs/    keep items 2 and 5 of the plan as they are
  ste fix --format json SKILL.md      the plan for a model
  cat reply.md | ste fix --apply -    print the fixed text
"""
import argparse
import collections
import json
import os
import sys

from .check import add_common_args, make_checker, run, short
from . import report
from .dictionary import MissingDictionary, find_path

WORD_RULES = ("not-approved", "wrong-pos", "wrong-form", "ing-form", "unknown-word")


def same_pos(src, alt):
    return alt == src or (src == "n" and alt == "TN") or (src == "v" and alt == "TV")


def safe_replacement(dic, f):
    """Return (replacement, None) or (None, reason)."""
    if f.rule != "not-approved":
        return None, "rewrite"
    entries = dic.not_approved.get(f.key or "", [])
    if len(entries) != 1:
        return None, "the word has more than one part of speech"
    e = entries[0]
    groups = [g for g in e.get("alternatives", []) if not g.get("other_meaning")]
    if len(groups) != 1 or len(groups[0]["alternatives"]) != 1:
        return None, "more than one alternative"
    a = groups[0]["alternatives"][0]
    t = a["text"]
    if not t or any(c in t for c in "…()[]") or "..." in t:
        return None, "the alternative needs a different construction"
    if not same_pos(e["pos"], a.get("pos")):
        return None, "the alternative is a different part of speech"
    if (f.word or "").lower() != f.key:
        return None, "the word is an inflected form"
    if (f.data or {}).get("compound"):
        return None, "the word is a part of a hyphenated word"
    guess = (f.data or {}).get("pos_guess")
    pos = e["pos"]
    # The position of the word must agree with the part of speech of the entry.
    # "the house palette" uses "house" as a noun, but the entry is for the verb.
    if pos in ("v", "TV") and guess != "v":
        return None, "the word is possibly not a verb here"
    if pos in ("n", "TN") and guess != "n":
        return None, "the word is possibly not a noun here"
    if pos == "adj" and guess == "v":
        return None, "the word is possibly not an adjective here"
    return t, None


def match_case(src, rep):
    if src.isupper() and len(src) > 1:
        return rep.upper()
    if src[:1].isupper():
        return rep[:1].upper() + rep[1:]
    return rep


def plan_for(dic, results):
    plan = []
    for path, fs in results:
        for f in fs:
            if f.rule not in WORD_RULES or f.rule == "unknown-word":
                continue
            rep, why = safe_replacement(dic, f)
            plan.append({"path": path, "line": f.line, "col": f.col, "word": f.word, "key": f.key,
                         "rule": f.rule, "replacement": match_case(f.word, rep) if rep else None,
                         "reason": why, "sentence": f.sentence, "message": f.message, "data": f.data})
    n = 0
    for it in plan:
        if it["replacement"]:
            n += 1
            it["id"] = n
        else:
            it["id"] = None
    return plan


def apply_file(text, items):
    """Apply replacements to text. Return (new text, applied items)."""
    lines = text.split("\n")
    done = []
    for it in sorted(items, key=lambda x: (x["line"], x["col"]), reverse=True):
        i, c = it["line"] - 1, it["col"] - 1
        if i >= len(lines):
            continue
        ln = lines[i]
        w = it["word"]
        if ln[c:c + len(w)] != w:
            continue  # the phrase goes over two lines, or the text changed
        before = ln[:c].rstrip()
        rep = it["replacement"]
        if before.lower().endswith((" a", " an")) or before.lower() in ("a", "an"):
            art = "an" if rep[:1].lower() in "aeiou" else "a"  # keep "a" and "an" correct
            cur = before.split()[-1]
            if cur.lower() != art:
                new_art = match_case(cur, art)
                start = len(before) - len(cur)
                ln = ln[:start] + new_art + ln[len(before):]
                c += len(new_art) - len(cur)
        lines[i] = ln[:c] + rep + ln[c + len(w):]
        done.append(it)
    return "\n".join(lines), done


def by_sentence(results, plan):
    """Group all remaining findings by sentence, for the rewrite list."""
    groups = collections.OrderedDict()
    for path, fs in results:
        for f in fs:
            if f.rule == "unknown-word" and not f.sentence:
                continue
            key = (path, f.sentence or f"line {f.line}")
            g = groups.setdefault(key, {"path": path, "line": f.line, "sentence": f.sentence, "problems": []})
            g["line"] = min(g["line"], f.line)
            g["problems"].append(f)
    safe = {(p["path"], p["line"], p["col"]) for p in plan if p["replacement"]}
    out = []
    for g in groups.values():
        g["problems"] = [f for f in g["problems"] if (f.path, f.line, f.col) not in safe]
        if g["problems"]:
            out.append(g)
    return out


def alt_lines(data):
    lines = []
    for grp in (data or {}).get("alternatives", [])[:4]:
        alt = ", ".join(a["text"] + (f" ({a['pos']})" if a.get("pos") else "") for a in grp["alternatives"]) or "no direct alternative"
        ex = grp.get("ste_example")
        lines.append(f"        {alt}" + (f": {ex}" if ex else ""))
    for h in (data or {}).get("help", []):
        lines.append(f"        help: {h}")
    return lines


def ids(spec):
    out = set()
    for part in (spec or "").split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            out.update(range(int(lo), int(hi) + 1))
        elif part:
            out.add(int(part))
    return out


def main(argv=None, prog="ste fix"):
    ap = argparse.ArgumentParser(prog=prog, description=(
        "Show the plan: numbered safe replacements and sentences to write again. "
        "With --apply, write the safe replacements."),
        epilog=__doc__.split("\n\n", 2)[2], formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    ap.add_argument("--apply", action="store_true", help="write the safe replacements to the files")
    ap.add_argument("--skip", metavar="N,N", help="with --apply: numbers from the plan to leave as they are, "
                                                 "for example 2,5-7")
    ap.add_argument("--only", metavar="N,N", help="with --apply: apply only these numbers from the plan")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    ap.add_argument("--no-unknown", action="store_true", help="leave out words that are not in the dictionary")
    report.add_args(ap)
    a = ap.parse_args(argv)
    if (a.skip or a.only) and not a.apply:
        ap.error("--skip and --only need --apply")
    stdin_text = None
    if "-" in a.paths:
        stdin_text = sys.stdin.read()
        sys.stdin = _Reader(stdin_text)
    try:
        checker = make_checker(a)
    except MissingDictionary as e:
        print(e, file=sys.stderr)
        return 2
    results = run(checker, a)
    plan = plan_for(checker.d, results)
    applied = []
    fixed_stdin = None
    if a.apply:
        skip, only = ids(a.skip), ids(a.only)
        per_file = collections.defaultdict(list)
        for it in plan:
            if it["replacement"] and it["id"] not in skip and (not only or it["id"] in only):
                per_file[it["path"]].append(it)
        for path, items in per_file.items():
            if path == "-":
                text = stdin_text
            else:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            new, done = apply_file(text, items)
            applied += done
            if path == "-":
                fixed_stdin = new
            elif done:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(new)
        if stdin_text is not None and fixed_stdin is None:
            fixed_stdin = stdin_text
        # check again, so that the rewrite list shows the current lines
        if applied:
            if stdin_text is not None:
                sys.stdin = _Reader(fixed_stdin)
            results = run(checker, a)
            plan = plan_for(checker.d, results)
    rewrite = by_sentence(results, plan if not a.apply else [])
    if a.html and not a.apply:
        report.emit(a, results, plan, rewrite, find_path(a.dictionary), stdin_text)
        return 0
    if a.format == "json":
        json.dump({"applied": [_clean(p) for p in applied],
                   "safe": [] if a.apply else [_clean(p) for p in plan if p["replacement"]],
                   "rewrite": [{"path": g["path"], "line": g["line"], "sentence": g["sentence"],
                                "problems": [f.as_dict() for f in g["problems"]]} for g in rewrite],
                   **({"text": fixed_stdin} if fixed_stdin is not None else {})},
                  sys.stdout, indent=1, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    out = sys.stderr if fixed_stdin is not None else sys.stdout
    if fixed_stdin is not None:
        sys.stdout.write(fixed_stdin)
    safe = [p for p in plan if p["replacement"]] if not a.apply else []
    if applied:
        out.write(f"Applied {len(applied)} safe replacements:\n")
        for p in sorted(applied, key=lambda p: (p["path"], p["line"])):
            out.write(f"  {p['path']}:{p['line']}  {p['word']} -> {p['replacement']}\n")
    elif safe:
        out.write(f"Safe replacements ({len(safe)}). To write them, run `ste fix --apply` "
                  "(add --skip N,N for the ones to keep):\n")
        for p in safe:
            out.write(f"  [{p['id']}] {p['path']}:{p['line']}:{p['col']}  {p['word']} -> {p['replacement']}\n")
    else:
        out.write("No safe replacements.\n")
    if rewrite:
        out.write(f"\nSentences to rewrite ({len(rewrite)}). Use the alternatives and the STE rules:\n")
        for g in rewrite:
            out.write(f"\n  {g['path']}:{g['line']}\n    \"{short(g['sentence'], 200)}\"\n")
            for f in g["problems"]:
                out.write(f"      - [{f.rule}] {f.message}\n")
                if f.rule in ("not-approved", "wrong-pos"):
                    for l in alt_lines(f.data):
                        out.write(l + "\n")
    else:
        out.write("No sentences to rewrite.\n")
    return 0


def _clean(p):
    return {k: v for k, v in p.items() if k != "data" and v is not None}


class _Reader:
    def __init__(self, text):
        self.text = text

    def read(self):
        return self.text


if __name__ == "__main__":
    sys.exit(main())
