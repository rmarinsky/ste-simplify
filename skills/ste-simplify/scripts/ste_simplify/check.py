"""ste scan: find words and sentences that do not obey Simplified Technical English (STE).

Usage examples:
  ste scan README.md docs/
  ste scan --format sarif -o ste.sarif .
  echo "You should utilize the tool." | ste scan -

Exit codes: 0 no findings at the --fail-on level, 1 findings, 2 setup error.
"""
import argparse
import collections
import json
import os
import re
import sys

from . import __version__
from .dictionary import Dictionary, MissingDictionary, candidates, PARTICIPLES
from .textscan import CODE_CHAR, CELL_CHAR, iter_files, scan_text

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ALLOW = os.path.join(HERE, "data", "software.allow")

RULES = {
    "not-approved": ("error", "1.1", "The word is not approved. Use an approved alternative."),
    "wrong-pos": ("error", "1.2", "The word is approved only as a different part of speech."),
    "wrong-form": ("error", "1.4", "This form of an approved word is not approved."),
    "ing-form": ("error", "3.5", "Do not use the -ing form of a verb, except in a technical name."),
    "unknown-word": ("warning", "1.5", "The word is not in the dictionary. If it is not a technical "
                                       "name or a technical verb, use an approved word."),
    "sentence-length": ("error", "5.1", "The sentence is too long."),
    "paragraph-length": ("warning", "6.6", "The paragraph has more than the maximum number of sentences."),
    "passive-voice": ("warning", "3.6", "Possible passive voice. Use the active voice."),
    "one-instruction": ("warning", "5.2", "Possibly more than one instruction in the sentence."),
    "semicolon": ("error", "8.1", "Do not use a semicolon. Write two sentences."),
    "contraction": ("error", "4.2", "Do not use contractions."),
}
SEVERITY_ORDER = {"error": 2, "warning": 1, "never": 3}

WORD_RE = re.compile(r"[A-Za-z][A-Za-z]*(?:['’][A-Za-z]+)*(?:-[A-Za-z]+)*")
CONTRACTION_RE = re.compile(r"\b[A-Za-z]+(?:n['’]t|['’](?:re|ll|ve|d|m))\b|"
                            r"\b(?:it|that|there|here|what|let|he|she|who|where|how)['’]s\b", re.I)
ABBREV_RE = re.compile(r"\b(?:e\.g|i\.e|etc|vs|cf|approx|No|Fig|Ref|min|max|Inc|Ltd|Dr|Mr|Ms|St)\.", re.I)
UNITS = {"mm", "cm", "m", "km", "in", "ft", "kg", "g", "mg", "lb", "s", "ms", "min", "h", "hz", "khz",
         "mhz", "ghz", "px", "pt", "em", "rem", "vh", "vw", "dp", "sp", "kb", "mb", "gb", "tb", "%", "v",
         "a", "w", "kw", "fps", "°c", "°f", "x"}
VERB_PREV = {"to", "must", "can", "cannot", "will", "do", "does", "did", "not", "you", "we", "they",
             "please", "should", "may", "might", "could", "would", "then", "always", "never", "also"}
NOUN_PREV = {"the", "a", "an", "this", "that", "these", "those", "each", "all", "its", "your", "our",
             "their", "my", "his", "her", "of", "no", "any", "some", "every", "for", "with"}
OBJECT_START = {"the", "a", "an", "this", "these", "that", "those", "it", "them", "all", "each", "your",
                "its", "their", "one", "two", "three", "no", CODE_CHAR}
BE = {"is", "are", "was", "were", "be", "been", "being"}
QUOTED_RE = re.compile(r'"[^"\n]{1,300}?"|\u201c[^\u201d\n]{1,300}?\u201d')
CONDITION_START = {"if", "when", "before", "after", "until", "while", "for", "to", "in", "on", "at", "during"}
NOT_ING = {"thing", "something", "nothing", "anything", "everything", "string", "spring", "ring", "king",
           "during", "morning", "evening", "ceiling", "bring", "sing", "swing", "wing", "sling", "sting",
           "cling", "fling", "ping", "thing", "bling", "ding", "zing", "pudding", "wedding", "awning"}


class Finding:
    __slots__ = ("path", "line", "col", "rule", "severity", "message", "word", "key", "sentence", "data")

    def __init__(self, path, line, col, rule, message, word=None, key=None, sentence=None, data=None):
        self.path, self.line, self.col, self.rule = path, line, col, rule
        self.severity = RULES[rule][0]
        self.message, self.word, self.key, self.sentence, self.data = message, word, key, sentence, data

    def as_dict(self):
        d = {k: getattr(self, k) for k in self.__slots__ if getattr(self, k) is not None}
        d["ste_rule"] = RULES[self.rule][1]
        return d


# ---------- allow-list ----------

def load_allow(paths):
    words, phrases = set(), set()
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    t = line.split("#", 1)[0].strip().lower()
                    if not t:
                        continue
                    (phrases if " " in t else words).add(t)
        except OSError as e:
            raise SystemExit(f"Cannot read allow-list {p}: {e}")
    return words, {tuple(p.split()) for p in phrases}


def find_project_allow(start):
    d = os.path.abspath(start if os.path.isdir(start) else os.path.dirname(start) or ".")
    while True:
        for name in (".ste-allow.txt", ".ste-allow"):
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
        if os.path.isdir(os.path.join(d, ".git")) or os.path.dirname(d) == d:
            return None
        d = os.path.dirname(d)


# ---------- blocks and sentences ----------

class Block:
    """Consecutive prose lines joined into one string, with a map back to (line, column)."""

    def __init__(self, kind):
        self.kind = kind
        self.text = ""
        self.pos = []  # for each character: (line, col)

    def add(self, line_no, text, col0=0):
        if self.text:
            self.text += " "
            self.pos.append(self.pos[-1])
        self.text += text
        self.pos.extend((line_no, col0 + i) for i in range(len(text)))

    def at(self, i):
        return self.pos[min(i, len(self.pos) - 1)]


def build_blocks(lines):
    blocks, cur = [], None
    for ln in lines:
        if ln.kind == "break":
            cur = None
            continue
        if ln.kind in ("heading", "table"):
            cur = None
            if ln.kind == "table":
                start = 0
                for cell in ln.text.split(CELL_CHAR):
                    if cell.strip():
                        b = Block("table")
                        b.add(ln.no, cell, start)
                        blocks.append(b)
                    start += len(cell) + 1
            else:
                b = Block("heading")
                b.add(ln.no, ln.text)
                blocks.append(b)
            continue
        if ln.kind == "list" or cur is None:
            cur = Block(ln.kind)
            blocks.append(cur)
        cur.add(ln.no, ln.text)
    return [b for b in blocks if b.text.strip()]


def split_sentences(text):
    """Return (start, end) spans of sentences in text."""
    protected = ABBREV_RE.sub(lambda m: m.group(0).replace(".", "\x00"), text)
    spans, start = [], 0
    for m in re.finditer(r"[.!?]+[\"'”)\]]*(?=\s+[^a-z\s]|\s*$)|:(?=\s*$)", protected):
        end = m.end()
        if protected[start:end].strip():
            spans.append((start, end))
        start = end
    if protected[start:].strip():
        spans.append((start, len(text)))
    out = []
    for s, e in spans:
        while s < e and text[s].isspace():
            s += 1
        out.append((s, e))
    return out


def count_words(sentence, quotes_as_one=True):
    s = re.sub(r"\([^()]*\)", " \u2063 ", sentence)  # text in parentheses counts as one word (rule 8.5)
    if quotes_as_one:
        s = QUOTED_RE.sub(" \u2063 ", s)  # a quoted term, for example a trigger phrase, counts as one word
    toks = [t for t in s.split() if re.search(r"[\w\u2063" + CODE_CHAR + "]", t)]
    n, prev_num = 0, False
    for t in toks:
        tl = t.lower().strip(".,:!?\"'")
        if prev_num and tl in UNITS:  # a number with its unit counts as one word (rule 8.6)
            prev_num = False
            continue
        n += 1
        prev_num = bool(re.fullmatch(r"[\d.,]+", tl))
    return n


# ---------- the checker ----------

class Checker:
    def __init__(self, dic, allow_words=(), allow_phrases=(), opts=None):
        self.d = dic
        self.allow = set(allow_words)
        self.allow_phrases = set(allow_phrases)
        self.max_allow_phrase = max((len(p) for p in self.allow_phrases), default=1)
        o = opts or {}
        self.max_proc = o.get("max_procedure", 20)
        self.max_desc = o.get("max_descriptive", 25)
        self.max_par = o.get("max_paragraph", 6)
        self.words_on = o.get("words", True)
        self.rules_on = o.get("rules", True)
        self.unknown_on = o.get("unknown", True)

    # --- word level ---

    def allowed(self, w):
        if w in self.allow:
            return True
        return any(base in self.allow for base, _, _ in candidates(w))

    def is_verb(self, w):
        return w in self.d.verbs or w in ("do", "don't")

    def check_text(self, path, text, ext):
        text = apply_ignores(text)
        lines = scan_text(text, ext, self.comments, self.yaml_keys)
        out = []
        for b in build_blocks(lines):
            out.extend(self.check_block(path, b))
        return out

    comments = False
    skip_quotes = True
    yaml_keys = ("description",)

    def check_block(self, path, b):
        out = []
        sents = split_sentences(b.text)
        if self.rules_on and b.kind == "prose" and len(sents) > self.max_par:
            ln, col = b.at(sents[0][0])
            out.append(Finding(path, ln, col + 1, "paragraph-length",
                               f"The paragraph has {len(sents)} sentences. The maximum is {self.max_par}.",
                               sentence=b.text[sents[0][0]:sents[0][1]].strip()))
        if self.rules_on and b.kind != "heading":
            for m in re.finditer(";", b.text):
                ln, col = b.at(m.start())
                out.append(Finding(path, ln, col + 1, "semicolon", RULES["semicolon"][2]))
            for m in CONTRACTION_RE.finditer(b.text):
                ln, col = b.at(m.start())
                out.append(Finding(path, ln, col + 1, "contraction",
                                   f"\"{m.group(0)}\": do not use contractions. Write the full words.",
                                   word=m.group(0)))
        for s, e in sents:
            out.extend(self.check_sentence(path, b, s, e))
        return out

    def check_sentence(self, path, b, s, e):
        sent = b.text[s:e]
        out = []
        toks = [(m.start() + s, m.group(0)) for m in WORD_RE.finditer(sent)]
        if self.skip_quotes:  # STE: keep quoted text as it is
            spans = [(m.start() + s, m.end() + s) for m in QUOTED_RE.finditer(sent)]
            word_toks = [t for t in toks if not any(a <= t[0] < z for a, z in spans)]
        else:
            word_toks = toks
        low = [t.lower().replace("’", "'") for _, t in toks]
        proc = self.is_procedure(low, sent)
        clean = " ".join(sent.split()).replace(CODE_CHAR, "`...`")
        if self.words_on:
            wlow = [t.lower().replace("\u2019", "'") for _, t in word_toks]
            out.extend(self.check_words(path, b, word_toks, wlow, proc, s, clean))
        if not self.rules_on or b.kind == "heading":
            return out
        ln, col = b.at(s)
        n = count_words(sent, self.skip_quotes)
        limit = self.max_proc if proc else self.max_desc
        if n > limit:
            kind = "an instruction" if proc else "a descriptive sentence"
            out.append(Finding(path, ln, col + 1, "sentence-length",
                               f"{n} words. The maximum for {kind} is {limit}.",
                               sentence=clean, data={"words": n, "limit": limit, "procedure": proc}))
        for i in range(len(low) - 1):
            if low[i] in BE:
                j = i + 1
                if j < len(low) - 1 and low[j].endswith("ly") and low[j] not in ("only", "early"):
                    j += 1
                w = low[j]
                if (w.endswith("ed") and len(w) > 4 and w not in ("need", "used to", "red", "bed")) or w in PARTICIPLES:
                    by = j + 1 < len(low) and low[j + 1] == "by"
                    p, c = b.at(toks[i][0])
                    msg = (f"\"{toks[i][1]} {toks[j][1]}\" looks like passive voice. "
                           + ("The agent is known (\"by\"), so use the active voice." if by else
                              "Use the active voice. In descriptive text, the passive is permitted only "
                              "when the agent is unknown. A past participle as an adjective is permitted."))
                    out.append(Finding(path, p, c + 1, "passive-voice", msg, word=f"{toks[i][1]} {toks[j][1]}",
                                       sentence=clean))
                    break
        if proc:
            for i in range(2, len(low) - 1):  # "Then do X." at the start is one instruction
                if low[i - 1] in ("and", "then") and self.is_verb(low[i]) and \
                        (low[i + 1] in OBJECT_START or low[i + 1] in ("up", "down", "out", "on", "off")):
                    if low[i - 1] == "and" and i >= 2 and low[i - 2] in ("press", "push", "pull"):
                        continue  # "press and hold" is one action
                    p, c = b.at(toks[i - 1][0])
                    out.append(Finding(path, p, c + 1, "one-instruction",
                                       f"\"{toks[i - 1][1]} {toks[i][1]}\" starts a second instruction. "
                                       "Write one instruction in each sentence, unless the actions occur "
                                       "at the same time.", sentence=clean))
                    break
        return out

    def is_procedure(self, low, sent):
        if len(low) < 2:
            return False  # one word, for example a table header, is not an instruction
        i = 0
        if low[0] in CONDITION_START and "," in sent:
            # "If the test fails, do the steps again." -> look at the word after the comma
            after = sent.split(",", 1)[1]
            m = WORD_RE.search(after)
            if not m:
                return False
            first = m.group(0).lower()
        else:
            first = low[i]
        if first in ("never", "always", "only", "please", "first", "then", "next", "also", "now"):
            nxt = low[1] if len(low) > 1 and first == low[0] else None
            return nxt is None or self.is_verb(nxt) or nxt == "do"
        if first in ("do", "don't"):
            return True
        verb = first in self.d.heads and "v" in self.d.heads[first] or \
            (first in self.d.na_pos and "v" in self.d.na_pos[first])
        if not verb:
            return False
        if self.d.approved_pos(first) - {"v"}:
            # the word can also be a noun or an adjective: "Code blocks ..." is not a command
            nxt = low[1] if len(low) > 1 and low[0] == first else None
            return nxt is None or nxt in OBJECT_START or nxt in ("that", "if", "for", "to", "in", "on", "with",
                                                                 "up", "out", "down", "off", "back", "again")
        return True

    def check_words(self, path, b, toks, low, proc, s0, clean):
        out = []
        i = 0
        n = len(toks)
        while i < n:
            start, tok = toks[i]
            w = low[i]
            # multi-word technical names and dictionary phrases (longest first, no punctuation between)
            hit = None
            for L in range(min(max(self.max_allow_phrase, self.d.max_phrase), n - i), 1, -1):
                seg = b.text[toks[i][0]:toks[i + L - 1][0] + len(toks[i + L - 1][1])]
                if re.search(r"[^\w\s'’-]", seg):
                    continue
                key = tuple(low[i:i + L])
                if key in self.allow_phrases:
                    hit = ("ok", L, None)
                    break
                ph = self.d.phrases.get(key)
                if ph:
                    hit = (ph[0], L, ph[1])
                    break
            if hit:
                if hit[0] == "na":
                    ln, col = b.at(start)
                    out.append(self.na_finding(path, ln, col, " ".join(t for _, t in toks[i:i + hit[1]]),
                                               hit[2], self.d.not_approved[hit[2]], "word", clean))
                i += hit[1]
                continue
            parts = [(start, tok)]
            if w.startswith("re-") and self.d.prefix_re is not None and not self.allowed(w):
                ln, col = b.at(start)  # "re-run": the prefix re- is not approved
                out.append(Finding(path, ln, col + 1, "not-approved",
                                   f"\"{tok}\": do not use the prefix re-. Use the approved word with AGAIN or BACK.",
                                   word=tok, key="re-", sentence=clean,
                                   data={"help": self.d.prefix_re.get("help", []), "alternatives": []}))
                i += 1
                continue
            if "-" in tok and not (self.allowed(w) or self.d.is_approved_form(w) or w in self.d.not_approved):
                parts, off = [], start
                for p in tok.split("-"):
                    parts.append((off, p))
                    off += len(p) + 1
            for pstart, ptok in parts:
                f = self.check_word(path, b, pstart, ptok, i, low, proc, clean)
                if f:
                    if len(parts) > 1 and f.data is not None:
                        f.data["compound"] = True  # a part of a hyphenated word: never a safe replacement
                    out.append(f)
            i += 1
        return out

    def check_word(self, path, b, start, tok, i, low, proc, clean):
        if len(tok) < 2 and tok.lower() not in ("a", "i"):
            return None
        if tok.isupper() and len(tok) > 1:
            return None  # abbreviations and acronyms (rule 8.6 counts them as one word)
        if re.search(r"[a-z][A-Z]", tok):
            return None  # CamelCase names
        w = tok.lower().replace("’", "'")
        if w.endswith("'s"):
            w = w[:-2]
        elif w.endswith("s'"):
            w = w[:-1]
        if "'" in w:
            return None  # contractions have their own rule
        if self.allowed(w):
            return None
        ln, col = b.at(start)
        first = self.sentence_start(b, start)
        if tok[0].isupper() and not first:
            return None  # a name in the middle of a sentence, for example "GitHub Actions"
        if self.d.is_approved_form(w):
            if w in self.d.na_pos:
                guess = self.guess_pos(low, i, first, proc)
                ok = self.d.approved_pos(w)
                if guess and guess in self.d.na_pos[w] and guess not in ok:
                    names = {"v": "a verb", "n": "a noun", "adj": "an adjective", "adv": "an adverb"}
                    data = self.alt_data(self.d.not_approved[w])
                    return Finding(path, ln, col + 1, "wrong-pos",
                                   f"\"{tok}\" is approved only as {', '.join(sorted(names.get(p, p) for p in ok))}. "
                                   f"Here it looks like {names.get(guess, guess)}.",
                                   word=tok, key=w, sentence=clean, data=data)
            return None
        na = self.d.lookup_not_approved(w)
        if na:
            key, entries, kind = na
            f = self.na_finding(path, ln, col, tok, key, entries, kind, clean)
            f.data["pos_guess"] = self.guess_pos(low, i, first, proc)
            return f
        if self.d.prefix_re is not None and w.startswith("re") and len(w) > 4:
            rest = w[2:].lstrip("-")
            if self.d.is_approved_form(rest) or rest in self.d.heads:
                return Finding(path, ln, col + 1, "not-approved",
                               f"\"{tok}\": do not use the prefix re-. Use the approved word with AGAIN or BACK.",
                               word=tok, key="re-", sentence=clean,
                               data={"help": self.d.prefix_re.get("help", []), "alternatives": []})
        base = self.d.lookup_base(w)
        if base:
            bw, kind = base
            forms = sorted({f for e in self.d.forms.get(bw, []) for f in e.get("forms", [])} or {bw})
            if kind == "ing" and w not in NOT_ING:
                return Finding(path, ln, col + 1, "ing-form",
                               f"\"{tok}\" is the -ing form of {bw.upper()}. Use a different construction "
                               f"(for example \"to {bw}\", \"when you {bw}\", or a noun). Approved forms: "
                               f"{', '.join(forms)}.", word=tok, key=bw, sentence=clean, data={"forms": forms})
            if kind != "ing":
                return Finding(path, ln, col + 1, "wrong-form",
                               f"\"{tok}\" is not an approved form of {bw.upper()}. Approved forms: "
                               f"{', '.join(forms)}.", word=tok, key=bw, sentence=clean, data={"forms": forms})
        if not self.unknown_on:
            return None
        if w.endswith("ing") and w not in NOT_ING and len(w) > 5:
            return Finding(path, ln, col + 1, "ing-form",
                           f"\"{tok}\" looks like the -ing form of a verb. If it is not a technical name, "
                           "use a different construction.", word=tok, key=w, sentence=clean)
        return Finding(path, ln, col + 1, "unknown-word",
                       f"\"{tok}\" is not in the dictionary. Use an approved word, or add it to the "
                       "allow-list if it is a technical name or technical verb.", word=tok, key=w, sentence=clean)

    def sentence_start(self, b, start):
        before = re.split(r"[.!?:\u2063]\s", b.text[:start])[-1]
        return not re.search(r"[A-Za-z0-9" + CODE_CHAR + "]", before)

    def guess_pos(self, low, i, first, proc):
        """A guess from the word before: "to check" is a verb, "the check" is a noun. None if not known."""
        prev = low[i - 1] if i > 0 else None
        if first and proc:
            return "v"
        if first:
            return None
        if prev == "not" and i >= 2 and low[i - 2] in BE:
            return None  # "is not clear": an adjective, not a verb
        if prev in VERB_PREV:
            return "v"
        if prev in NOUN_PREV:
            return "n"
        return None

    def alt_data(self, entries):
        groups = []
        helps = []
        for e in entries:
            for h in e.get("help", []):
                if h not in helps:
                    helps.append(h)
            for g in e.get("alternatives", []):
                if g.get("other_meaning") and e["approved"]:
                    continue
                groups.append({
                    "for_pos": e["pos"],
                    "alternatives": [{"text": a["text"].upper(), "pos": a["pos"], **({"note": a["note"]} if a.get("note") else {})}
                                     for a in g["alternatives"]],
                    "ste_example": g.get("ste_example", ""),
                    "non_ste_example": g.get("non_ste_example", ""),
                })
            if not e.get("alternatives") and e.get("meanings"):
                for m in e["meanings"]:
                    groups.append({"for_pos": e["pos"], "alternatives": [], "ste_example": m.get("ste_example", ""),
                                   "non_ste_example": m.get("non_ste_example", "")})
        return {"alternatives": groups, "help": helps}

    def na_finding(self, path, ln, col, tok, key, entries, kind, clean):
        data = self.alt_data(entries)
        alts = []
        for g in data["alternatives"]:
            for a in g["alternatives"]:
                t = a["text"] + (f" ({a['pos']})" if a.get("pos") else "")
                if t not in alts:
                    alts.append(t)
        msg = f"\"{tok}\" is not approved."
        if kind not in ("word",):
            msg = f"\"{tok}\" is a form of \"{key}\", which is not approved."
        if alts:
            msg += " Use: " + ", ".join(alts) + "."
        elif data["help"]:
            msg += " " + " ".join(data["help"])
        return Finding(path, ln, col + 1, "not-approved", msg, word=tok, key=key, sentence=clean, data=data)


def apply_ignores(text):
    """Blank the lines between ste-disable and ste-enable, and the line after ste-ignore."""
    out, off, skip_next = [], False, False
    for line in text.split("\n"):
        if "ste-disable" in line:
            off = True
        if "ste-enable" in line:
            off = False
            out.append("")
            continue
        if off or skip_next:
            out.append("")
            skip_next = False
            continue
        if "ste-ignore" in line:
            skip_next = True
            out.append("")
            continue
        out.append(line)
    return "\n".join(out)


# ---------- reports ----------

def group_words(findings):
    groups = collections.OrderedDict()
    for f in findings:
        if f.rule in ("not-approved", "wrong-pos", "wrong-form", "ing-form", "unknown-word"):
            k = (f.rule, f.key or (f.word or "").lower())
            groups.setdefault(k, []).append(f)
    return groups


def fmt_alts(data, examples):
    lines = []
    for g in (data or {}).get("alternatives", [])[:4]:
        alt = ", ".join(a["text"] + (f" ({a['pos']})" if a.get("pos") else "") for a in g["alternatives"]) or "no direct alternative"
        ex = g.get("ste_example")
        lines.append(f"      {alt}" + (f": {ex}" if ex and examples else ""))
    for h in (data or {}).get("help", []):
        lines.append(f"      help: {h}")
    return lines


def lines_list(fs, n=10):
    ls = sorted({f.line for f in fs})
    s = ", ".join(map(str, ls[:n]))
    return s + (f" (+{len(ls) - n})" if len(ls) > n else "")


def report_text(results, out, examples=1, show_unknown=True, summary_only=False):
    total = collections.Counter()
    all_words = collections.Counter()
    for path, fs in results:
        if not fs:
            continue
        sev = collections.Counter(f.severity for f in fs)
        total.update(sev)
        groups = group_words(fs)
        for (rule, key), g in groups.items():
            if rule in ("not-approved", "wrong-pos"):
                all_words[key] += len(g)
        if summary_only:
            out.write(f"{path}: {sev['error']} errors, {sev['warning']} warnings\n")
            continue
        out.write(f"\n{path}  ({sev['error']} errors, {sev['warning']} warnings)\n")
        titles = [("not-approved", "Words that are not approved"), ("wrong-pos", "Approved words used as a different part of speech"),
                  ("wrong-form", "Forms that are not approved"), ("ing-form", "-ing forms (rule 3.5)")]
        for rule, title in titles:
            items = [(k, g) for k, g in groups.items() if k[0] == rule]
            if not items:
                continue
            items.sort(key=lambda x: -len(x[1]))
            out.write(f"  {title}:\n")
            for (r, key), g in items:
                out.write(f"    {g[0].word if len(g) == 1 else key:<18} x{len(g):<3} lines {lines_list(g)}\n")
                if rule in ("not-approved", "wrong-pos"):
                    for l in fmt_alts(g[0].data, examples):
                        out.write(l + "\n")
                elif g[0].data and g[0].data.get("forms"):
                    out.write(f"      approved forms: {', '.join(g[0].data['forms'])}\n")
        unk = [(k, g) for k, g in groups.items() if k[0] == "unknown-word"]
        if unk and show_unknown:
            unk.sort(key=lambda x: (-len(x[1]), x[0][1]))
            out.write("  Not in the dictionary (use an approved word, or allow-list a technical name):\n")
            row = "    " + ", ".join(f"{k[1]} x{len(g)}" if len(g) > 1 else k[1] for k, g in unk)
            out.write(wrap(row, 100, "    ") + "\n")
        other = [f for f in fs if f.rule not in ("not-approved", "wrong-pos", "wrong-form", "ing-form", "unknown-word")]
        if other:
            out.write("  Writing rules:\n")
            for f in sorted(other, key=lambda f: (f.line, f.col)):
                s = f" | {short(f.sentence)}" if f.sentence else ""
                out.write(f"    {f.line:>4}  {f.rule:<16} {f.message}{s}\n")
    n_files = sum(1 for _, fs in results if fs)
    out.write(f"\n{len(results)} files checked, {n_files} with findings: {total['error']} errors, "
              f"{total['warning']} warnings.\n")
    if all_words and len(results) > 1:
        top = ", ".join(f"{k} x{n}" for k, n in all_words.most_common(25))
        out.write(wrap("Most frequent words that are not approved: " + top, 100, "  ") + "\n")


def short(s, n=90):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[:n - 3] + "..."


def wrap(s, width, indent):
    words, lines, cur = s.split(" "), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur.strip():
            lines.append(cur)
            cur = indent + w
        else:
            cur = (cur + " " + w) if cur else w
    lines.append(cur)
    return "\n".join(lines)


def report_json(results, out):
    files = []
    for path, fs in results:
        sev = collections.Counter(f.severity for f in fs)
        files.append({"path": path, "errors": sev["error"], "warnings": sev["warning"],
                      "findings": [f.as_dict() for f in fs]})
    tot = collections.Counter(f.severity for _, fs in results for f in fs)
    json.dump({"tool": "ste", "version": __version__, "files": files,
               "summary": {"files": len(results), "errors": tot["error"], "warnings": tot["warning"]}},
              out, indent=1, ensure_ascii=False)
    out.write("\n")


def report_sarif(results, out):
    rules = [{"id": k, "name": k, "shortDescription": {"text": v[2]},
              "properties": {"ste_rule": v[1]}, "defaultConfiguration": {"level": v[0]}}
             for k, v in RULES.items()]
    index = {k: i for i, k in enumerate(RULES)}
    res = []
    for path, fs in results:
        uri = os.path.relpath(path).replace(os.sep, "/") if path != "-" else "stdin"
        for f in fs:
            res.append({"ruleId": f.rule, "ruleIndex": index[f.rule], "level": f.severity,
                        "message": {"text": f.message},
                        "locations": [{"physicalLocation": {"artifactLocation": {"uri": uri},
                                                            "region": {"startLine": f.line, "startColumn": max(f.col, 1)}}}]})
    json.dump({"$schema": "https://json.schemastore.org/sarif-2.1.0.json", "version": "2.1.0",
               "runs": [{"tool": {"driver": {"name": "ste", "version": __version__,
                                             "informationUri": "https://github.com/rmarinsky/ste-simplify",
                                             "rules": rules}},
                         "results": res}]}, out, indent=1)
    out.write("\n")


# ---------- CLI ----------

def add_common_args(ap):
    ap.add_argument("paths", nargs="*", default=["."], help="files or folders; '-' reads stdin")
    ap.add_argument("--dictionary", metavar="FILE", help="dictionary JSON (default: $STE_DICTIONARY or "
                                                         "~/.config/ste-simplify/dictionary.json.gz)")
    ap.add_argument("--allow", metavar="FILE", action="append", default=[],
                    help="allow-list of technical names, one for each line (you can use it more than one time)")
    ap.add_argument("--no-default-allow", action="store_true", help="do not load the built-in software allow-list")
    ap.add_argument("--comments", action="store_true", help="also check comments in source code")
    ap.add_argument("--exclude", metavar="GLOB", action="append", default=[], help="skip paths that match")
    ap.add_argument("--yaml-keys", default="description", help="YAML keys to check (comma list)")
    ap.add_argument("--ext", default=".md", help="file type for stdin (default .md)")
    ap.add_argument("--check-quotes", action="store_true", help="also check words in double quotes")
    ap.add_argument("--max-procedure", type=int, default=20)
    ap.add_argument("--max-descriptive", type=int, default=25)
    ap.add_argument("--max-paragraph", type=int, default=6)


def make_checker(a):
    dic = Dictionary.load(a.dictionary)
    allow_files = [] if a.no_default_allow else [DEFAULT_ALLOW]
    proj = find_project_allow(a.paths[0] if a.paths and a.paths[0] != "-" else ".")
    if proj:
        allow_files.append(proj)
    allow_files += a.allow
    words, phrases = load_allow(allow_files)
    c = Checker(dic, words, phrases, {
        "max_procedure": a.max_procedure, "max_descriptive": a.max_descriptive, "max_paragraph": a.max_paragraph,
        "words": not getattr(a, "rules_only", False), "rules": not getattr(a, "words_only", False),
        "unknown": not getattr(a, "no_unknown", False)})
    c.comments = a.comments
    c.skip_quotes = not a.check_quotes
    c.yaml_keys = tuple(k.strip() for k in a.yaml_keys.split(",") if k.strip())
    return c


def run(checker, a):
    results = []
    for p in a.paths:
        if p == "-":
            results.append(("-", checker.check_text("-", sys.stdin.read(), a.ext)))
            continue
        if not os.path.exists(p):
            raise SystemExit(f"Not found: {p}")
        for f in iter_files([p], a.comments, a.exclude):
            try:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError as e:
                print(f"Cannot read {f}: {e}", file=sys.stderr)
                continue
            results.append((f, checker.check_text(f, text, os.path.splitext(f)[1])))
    return results


def main(argv=None, prog="ste scan"):
    ap = argparse.ArgumentParser(prog=prog, description="Check text against Simplified Technical English.",
                                 epilog=__doc__.split("\n\n", 1)[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    ap.add_argument("--format", choices=("text", "json", "sarif"), default="text")
    ap.add_argument("-o", "--output", metavar="FILE", help="write the report to a file")
    ap.add_argument("--fail-on", choices=("error", "warning", "never"), default="error")
    ap.add_argument("--examples", type=int, default=1, help="1 shows the STE example for each alternative, 0 hides them")
    ap.add_argument("--no-unknown", action="store_true", help="do not report words that are not in the dictionary")
    ap.add_argument("--words-only", action="store_true", help="check only words, not the writing rules")
    ap.add_argument("--rules-only", action="store_true", help="check only the writing rules, not words")
    ap.add_argument("--summary", action="store_true", help="one line for each file")
    ap.add_argument("--version", action="version", version=f"ste {__version__}")
    from . import report
    report.add_args(ap)
    a = ap.parse_args(argv)
    try:
        checker = make_checker(a)
    except MissingDictionary as e:
        print(e, file=sys.stderr)
        return 2
    results = run(checker, a)
    if a.html:
        from . import fix, report
        from .dictionary import find_path
        plan = fix.plan_for(checker.d, results)
        report.emit(a, results, plan, fix.by_sentence(results, plan), find_path(a.dictionary))
    out = open(a.output, "w", encoding="utf-8") if a.output else (open(os.devnull, "w") if a.html else sys.stdout)
    try:
        if a.format == "json":
            report_json(results, out)
        elif a.format == "sarif":
            report_sarif(results, out)
        else:
            report_text(results, out, a.examples, not a.no_unknown, a.summary)
    finally:
        if out is not sys.stdout:
            out.close()
    if a.fail_on == "never":
        return 0
    lvl = SEVERITY_ORDER[a.fail_on]
    return 1 if any(SEVERITY_ORDER[f.severity] >= lvl for _, fs in results for f in fs) else 0


if __name__ == "__main__":
    sys.exit(main())
