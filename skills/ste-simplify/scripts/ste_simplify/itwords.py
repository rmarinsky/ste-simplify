"""Make data/it-words.json from the word list of the Google developer documentation style guide.

The word list is licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).
This script keeps the term names, the "Don't use" entries with their alternatives, and the
first sentence of the guidance. It changes nothing else. The output file names the source,
the license and the changes.

Usage (for maintainers):
  python3 -m ste_simplify.itwords [-o data/it-words.json]
"""
import argparse
import html
import json
import os
import re
import sys
import urllib.request

URL = "https://developers.google.com/style/word-list"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "data", "it-words.json")

AVOID = re.compile(r"^(Don't use(\s+the\s+term)?\.|Don't use\s*$|Avoid in general usage\b|Avoid\.)", re.I)
NOT_A_TERM = re.compile(r"^(Don't use|Avoid|Use with caution|Try |Where possible)", re.I)


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def terms_of(dt):
    t = re.sub(r"<a [^>]*>.*?</a>", "", dt, flags=re.S)
    t = text(re.sub(r"<span[^>]*></span>", "", t))
    t = re.sub(r"\s*\([^)]*\)", "", t)  # "& (ampersand)" -> "&"
    parts = [x.strip().lower() for x in t.split(",") if x.strip()]
    if len(parts) == 2 and parts[1].split()[-1] in ("the", "a", "an", "of", "to"):
        return [parts[1] + " " + parts[0]]  # "reservation, off the" -> "off the reservation"
    return parts


def first_sentence(s):
    m = re.match(r"(.+?[.!?])(\s|$)", s)
    return m.group(1) if m else s


def alternatives(dds, terms, noun_alts):
    """Italic words that the guidance gives as replacements."""
    alts = noun_alts
    for d in dds:  # "For the noun <i>whitelist</i>, consider ... <i>allowlist</i>, <i>trustlist</i>"
        for m in re.finditer(r"For the (?:noun|verb|adjective) <i>(.*?)</i>(.*?)(?=</li>|$)", d, re.S):
            alts.setdefault(text(m.group(1)).lower(), []).extend(text(i) for i in re.findall(r"<i>(.*?)</i>", m.group(2)))
    first = dds[0] if dds else ""
    m = re.search(r"(Instead|such as|synonym for|words like|replace)(.*)", first, re.S)
    common = [text(i) for i in re.findall(r"<i>(.*?)</i>", m.group(2))] if m else []
    if not common:
        m = re.search(r"use words like ([^.<]+)", text(first))
        if m:
            common = [x.strip() for x in re.split(r",\s*(?:or\s+)?|\s+or\s+", m.group(1)) if x.strip()]
    out = {}
    for t in terms:
        own = alts.get(t) or common
        out[t] = [x for x in dict.fromkeys(own) if x.lower() not in terms and x.lower() not in ("slave",)]
    return out


def unconditional(first, dt):
    """True for a ban that is always true: "Don't use.", "Avoid in general usage.", "Don't use X, Y and Z."."""
    sent = first_sentence(first)
    if re.match(r"^(Don't use|Avoid|Generally avoid)( in general usage| when possible)?\.$", sent):
        return True
    if sent.startswith("Use with caution") and "icon-dontuse" in dt:
        return True  # for example "master"
    m = re.match(r"^Don't use (.+?)\.$", sent)
    if m and not re.search(r"\b(as|to|for|in|when|if|with|outside|unless|except|after|before|on)\b", m.group(1)):
        return True  # "Don't use blacklist, whitelist, and graylist."
    return False


def parse(page):
    entries = re.findall(r'<dt id="([^"]*)">(.*?)</dt>(.*?)(?=<dt id=|</dl>)', page, re.S)
    avoid, known, noun_alts = {}, set(), {}
    for anchor, dt, body in entries:
        dds = re.findall(r'<dd(?: class="([^"]*)")?>(.*?)(?=<dd|$)', body, re.S)
        dds = [d for c, d in dds if "example" not in (c or "")]
        first = text(dds[0]) if dds else ""
        terms = [t for t in terms_of(dt) if re.fullmatch(r"[a-z][a-z0-9 .'/-]*", t)]
        if not terms:
            continue
        if "icon-dontuse" in dt or "icon-avoid" in dt or AVOID.match(first):
            if not unconditional(first, dt):
                continue  # "Don't use as a verb", "Avoid in timeless documentation": it depends on the context
            alts = alternatives(dds, terms, noun_alts)
            for t in terms:
                avoid[t] = {"alternatives": alts[t], "note": first_sentence(first), "anchor": anchor}
        elif not NOT_A_TERM.match(first) and not re.search(r" (versus|and|or) ", " ".join(terms)):
            known.update(terms)
    for t, e in avoid.items():  # "whitelist: Don't use. See blacklist." uses the advice in the other entry
        if not e["alternatives"] and noun_alts.get(t):
            e["alternatives"] = list(dict.fromkeys(noun_alts[t]))
    return {"avoid": avoid, "known": sorted(known - set(avoid))}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ste_simplify.itwords", description=__doc__.split("\n")[0])
    ap.add_argument("-o", "--out", default=DEFAULT_OUT)
    ap.add_argument("--html", metavar="FILE", help="use a saved copy of the page")
    a = ap.parse_args(argv)
    if a.html:
        with open(a.html, encoding="utf-8") as f:
            page = f.read()
    else:
        req = urllib.request.Request(URL, headers={"User-Agent": "ste-simplify"})
        with urllib.request.urlopen(req, timeout=60) as r:
            page = r.read().decode("utf-8")
    if "Creative Commons Attribution 4.0" not in page:
        sys.exit("The page does not show the CC BY 4.0 license. Stop: examine the license first.")
    data = parse(page)
    out = {
        "source": URL,
        "title": "Word list, Google developer documentation style guide",
        "license": "CC BY 4.0, https://creativecommons.org/licenses/by/4.0/",
        "changes": "Only the term names, the 'Don't use' entries with their alternatives, and the first "
                   "sentence of their guidance. Extracted by ste_simplify/itwords.py.",
        "avoid": data["avoid"],
        "known": data["known"],
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print(f"Wrote {a.out}: {len(out['avoid'])} terms to avoid, {len(out['known'])} known IT terms.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
