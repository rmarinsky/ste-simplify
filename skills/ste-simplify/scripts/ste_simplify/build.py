#!/usr/bin/env python3
"""Build a local STE dictionary (JSON) from your own copy of the official PDF.

Usage:
  ste-build-dictionary PDF [-o OUT.json] [--lite]

The script reads word positions with `pdftotext -bbox` (poppler) and splits
each dictionary page into its four columns. It writes one JSON file with all
approved words (with their forms and meanings) and all words that are not
approved (with their approved alternatives and the example sentences).

The dictionary is copyrighted by ASD. Keep the output file local.
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys

POS = r"n|v|adj|adv|prep|pron|conj|art|prefix|TN|TV"
POS_RE = re.compile(r"\((%s)\)" % POS)
WORD_RE = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>')
HELP_INDENT = 22.0  # help text ("For other meanings, use:") is indented this much or more
LINE_TOL = 5.0
GAP = 6.0


def default_out():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "ste-simplify", "dictionary.json")


def bbox_xhtml(pdf):
    """Run pdftotext (poppler) and return its word-position XHTML."""
    try:
        return subprocess.run(["pdftotext", "-bbox", pdf, "-"], check=True,
                              capture_output=True, text=True).stdout
    except FileNotFoundError:
        sys.exit("pdftotext not found. Install poppler: `brew install poppler` or `apt install poppler-utils`.")
    except subprocess.CalledProcessError as e:
        sys.exit(f"pdftotext failed: {e.stderr.strip()}")


def read_pages(xhtml):
    """Yield the words of each page as (x0, y0, y1, text, x1)."""
    for chunk in xhtml.split("<page ")[1:]:
        yield [(float(a), float(b), float(d), html.unescape(t), float(c)) for a, b, c, d, t in WORD_RE.findall(chunk)]


def lines_of(words):
    """Group words into lines by their top y position."""
    lines = []
    for w in sorted(words, key=lambda w: (w[1], w[0])):
        if lines and abs(lines[-1][0] - w[1]) < LINE_TOL:
            lines[-1][1].append(w)
        else:
            lines.append([w[1], [w]])
    return [(y, sorted(ws)) for y, ws in lines]


def page_layout(words):
    """Return (column x starts, body top, body bottom) for a dictionary page, else None."""
    alt = [w for w in words if w[3] == "ALTERNATIVES"]
    if not alt:
        return None
    a = alt[0]
    near = [w for w in words if abs(w[1] - a[1]) < 30]
    word = [w for w in near if w[3] == "Word" and w[0] < a[0]]
    ste = [w for w in near if w[3] == "STE" and w[0] > a[0]]
    non = [w for w in near if w[3] == "Non-STE"]
    if not (word and ste and non):
        return None
    footer = [w for w in words if re.match(r"^2-1-[A-Z]\d+$", w[3])]
    if not footer:
        return None  # introduction pages (2-0-x) show examples, not entries
    bottom = min(w[1] for w in words if w[3] in ("Issue", "Page") and w[1] > 600) - 1
    top = max(w[2] for w in near if w[3] in ("ALTERNATIVES", "speech)", "example", "EXAMPLE")) + 1
    return (word[0][0], a[0], ste[0][0], non[0][0]), top, bottom


def split_columns(ws, cols):
    cells = {1: [], 2: [], 3: [], 4: []}
    segs = []
    for w in ws:  # words with a large gap between them are in different cells
        if segs and w[0] - segs[-1][-1][4] < GAP:
            segs[-1].append(w)
        else:
            segs.append([w])
    last = 1
    for seg in segs:
        x = seg[0][0]
        c = min(range(4), key=lambda i: abs(cols[i] - x)) + 1
        c = max(c, last)  # cells are in column order
        last = c
        cells[c].extend(seg)
    # A long alternative can push the example to the left: "APPROXIMATELY (adv) DRAIN".
    c2 = cells[2]
    for i, w in enumerate(c2):
        if POS_RE.fullmatch(w[3].rstrip(",")) and i + 1 < len(c2) and c2[i + 1][0] - w[0] > 0:
            rest = c2[i + 1:]
            if rest and not cells[3] and all(t[3].isupper() or not t[3].isalpha() for t in rest):
                cells[2], cells[3] = c2[:i + 1], rest + cells[3]
            break
    # A Non-STE example can start a little left of its column.
    c3 = cells[3]
    for i in range(1, len(c3)):
        if c3[i][3][:1].isupper() and not c3[i][3].isupper() and c3[i][0] > cols[3] - 40 \
                and c3[i - 1][3].isupper():
            cells[3], cells[4] = c3[:i], c3[i:] + cells[4]
            break
    return cells


def text(ws):
    return " ".join(w[3] for w in ws).strip()


def is_alt_text(s):
    """Alternatives are in uppercase letters; approved meanings are not."""
    letters = re.sub(r"\((%s)\)" % POS, "", s)
    letters = re.sub(r"[^A-Za-z]", "", letters)
    return bool(letters) and letters.isupper() and len(letters) > 1 or s.strip() in ("A", "AN")


class Entry:
    def __init__(self):
        self.head = []        # column 1 text lines
        self.help = []
        self.rows = []        # dicts: col2, col3, col4 lists of strings
        self.page = None
        self._help_at = {}    # column -> (index in self.help, y of last line)

    def add_help(self, col, y, t):
        last = self._help_at.get(col)
        if last and y - last[1] < 18:
            self.help[last[0]] += " " + t
            self._help_at[col] = (last[0], y)
        else:
            self.help.append(t)
            self._help_at[col] = (len(self.help) - 1, y)

    def complete(self):
        h = " ".join(self.head)
        return bool(POS_RE.search(h)) and not h.rstrip().endswith(",") and h.count("(") <= h.count(")")


def parse(xhtml):
    entries = []
    cur = None
    for pno, words in enumerate(read_pages(xhtml), 1):
        lay = page_layout(words)
        if not lay:
            continue
        cols, top, bottom = lay
        body = [w for w in words if top < w[1] < bottom]
        prev_c3_done = True
        for y, ws in lines_of(body):
            cells = split_columns(ws, cols)
            c1, c2, c3, c4 = (cells[i] for i in (1, 2, 3, 4))
            # help text is indented in column 1 or column 2
            h1 = c1 if c1 and c1[0][0] > cols[0] + HELP_INDENT else []
            h2 = c2 if c2 and c2[0][0] > cols[1] + HELP_INDENT else []
            c1 = [] if h1 else c1
            c2 = [] if h2 else c2
            if c1:
                t1 = text(c1)
                if cur is None:
                    cont = False
                elif cur.head[-1].endswith("-"):
                    cont = True  # "ELECTROMAG-" then "NETIC (adj)"
                elif not POS_RE.search(" ".join(cur.head)):
                    h = " ".join(cur.head)
                    cont = t1.startswith("(") or h.count("(") > h.count(")")  # "ACCIDENTAL" then "(adj)"
                elif POS_RE.search(t1) and not t1.startswith("("):
                    cont = False  # a new headword
                else:
                    cont = (not cur.complete() or t1.startswith("(")
                            or t1.endswith(",") or cur.head[-1].endswith(","))
                if cont:
                    cur.head.append(t1)
                else:
                    cur = Entry()
                    cur.page = pno
                    cur.head.append(t1)
                    entries.append(cur)
                    prev_c3_done = True
            if not cur:
                continue
            for col, hl in ((1, h1), (2, h2)):
                if hl:
                    cur.add_help(col, y, text(hl))
            t2, t3, t4 = text(c2), text(c3), text(c4)
            new_row = not cur.rows and bool(t2 or t3 or t4)
            prev2 = " ".join(cur.rows[-1]["c2"]) if cur.rows else ""
            if t2 and cur.rows and c2[0][0] < cols[1] + 6 and not t2.startswith("(") \
                    and prev2.count("(") <= prev2.count(")"):
                if re.match(r"^\d+\.", t2):
                    new_row = True
                elif prev_c3_done and (t3 or is_alt_text(t2)):
                    new_row = True
            if new_row:
                cur.rows.append({"c2": [], "c3": [], "c4": [], "after_help": len(cur.help)})
            if cur.rows:
                r = cur.rows[-1]
                if t2:
                    r["c2"].append(t2)
                if t3:
                    r["c3"].append(t3)
                    prev_c3_done = bool(re.search(r"[.?!:]\W*$", t3))
                if t4:
                    r["c4"].append(t4)
    return [finish(e) for e in entries]


def norm_space(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"([A-Za-z]{4,})- ([A-Za-z])", r"\1\2", s)  # a word broken at the end of a line
    return re.sub(r"(\w)- (\w)", r"\1-\2", s)


def parse_head(h):
    h = norm_space(h)
    m = POS_RE.search(h)
    pos = m.group(1) if m else None
    word = h[:m.start()].strip() if m else h
    rest = h[m.end():] if m else ""
    forms = []
    for t in re.split(r"[,()]", rest):
        t = t.strip()
        t = re.sub(r"^also\s+", "", t)
        for part in re.split(r"\s+(?:and|or)\s+|\s*,\s*", t):
            part = part.strip()
            if part and re.fullmatch(r"[A-Za-z' -]+", part):
                forms.append(part)
    return word, pos, forms


def parse_alt(s):
    s = norm_space(s)
    out, start = [], 0
    for m in POS_RE.finditer(s):
        t = s[start:m.start()].strip(" ,")
        if t:
            out.append({"text": t.lower(), "pos": m.group(1)})
        start = m.end()
    tail = s[start:].strip(" ,")
    if tail:
        out.append({"text": tail.lower(), "pos": None})
    merged = []
    for a in out:  # "(with a file (TN))" is a note for the alternative before it
        if a["text"].startswith("(") and merged:
            note = a["text"] + (f" ({a['pos']})" if a["pos"] else "")
            merged[-1]["note"] = (merged[-1].get("note", "") + " " + note).strip()
        else:
            merged.append(a)
    return merged


def match_keys(word):
    """Text forms to look for in a document: "case (in case of)" -> ["in case of"]."""
    if "..." in word or "…" in word or word.endswith("-"):
        return []
    m = re.match(r"^(.*?)\s*\((.*?)\s*\)$", word)
    if not m:
        return [word]
    base, inner = m.group(1).strip(), m.group(2).strip()
    if inner.startswith("or "):
        return [base, inner[3:].strip()]
    if re.search(r"\b" + re.escape(base), inner):
        return [inner]
    return [base + " " + inner]


def finish(e):
    word, pos, forms = parse_head(" ".join(e.head))
    approved = word == word.upper() and any(c.isalpha() for c in word)
    word = word.lower()
    entry = {"word": word, "pos": pos, "approved": approved, "page": e.page, "keys": match_keys(word)}
    if approved:
        entry["forms"] = sorted({*entry["keys"], *[f.lower() for f in forms]})
    meanings, alts = [], []
    other = False
    for r in e.rows:
        c2 = norm_space(" ".join(r["c2"]))
        ex = norm_space(" ".join(r["c3"]))
        non = norm_space(" ".join(r["c4"]))
        if "other meaning" in " ".join(e.help[:r["after_help"]]).lower():
            other = True
        if c2.startswith("(") and alts:  # "(with a bolt [TN] or bolts [TN])" belongs to the alternative above
            alts[-1]["note"] = c2
            continue
        if is_alt_text(c2) or (not approved and c2):
            parsed = parse_alt(c2) if is_alt_text(c2) else [{"text": c2, "pos": None}]
            kept = []
            for p in parsed:
                m = re.search(r"\s*(\(.*\[tn\].*)$", p["text"])
                if m:
                    p["note"], p["text"] = m.group(1), p["text"][:m.start()].strip()
                if p["text"]:
                    kept.append(p)
                elif kept and p.get("note"):
                    kept[-1]["note"] = p["note"]
            alts.append({"alternatives": kept, "ste_example": ex,
                         "non_ste_example": non, "other_meaning": approved or other})
        else:
            meanings.append({"meaning": re.sub(r"^\d+\.\s*", "", c2), "ste_example": ex,
                             "non_ste_example": non})
    if meanings:
        entry["meanings"] = meanings
    if alts:
        entry["alternatives"] = alts
    if e.help:
        entry["help"] = [norm_space(h) for h in e.help]
    return entry


def lite(entry):
    """Keep only what the checker needs: no meanings and no example sentences."""
    out = {k: entry[k] for k in ("word", "pos", "approved", "keys", "forms") if k in entry}
    if entry.get("alternatives"):
        out["alternatives"] = [{"alternatives": g["alternatives"], "other_meaning": g["other_meaning"]}
                               for g in entry["alternatives"]]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", default=default_out())
    ap.add_argument("--lite", action="store_true",
                    help="omit meanings and example sentences (a small file, for CI secrets)")
    a = ap.parse_args(argv)
    if not os.path.isfile(a.pdf):
        sys.exit(f"PDF not found: {a.pdf}")
    entries = parse(bbox_xhtml(a.pdf))
    if a.lite:
        entries = [lite(e) for e in entries]
    approved = [e for e in entries if e["approved"]]
    data = {
        "schema": 1,
        "source": os.path.basename(a.pdf),
        "note": "Extracted from your own copy of the ASD-STE100 standard. Copyrighted by ASD. Do not publish.",
        "counts": {"approved": len(approved), "not_approved": len(entries) - len(approved)},
        "entries": entries,
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=None if a.lite else 1,
                  separators=(",", ":") if a.lite else None)
    if len(approved) < 500 or len(entries) - len(approved) < 800:
        print("Warning: fewer entries than expected. Is this the ASD-STE100 Issue 9 PDF?", file=sys.stderr)
    print(f"Wrote {a.out}: {data['counts']['approved']} approved entries, "
          f"{data['counts']['not_approved']} not approved entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
