"""Load the local dictionary and look up words.

The dictionary file is made by build.py from the user's own copy of the
standard. This module has no word lists from the standard. It has only
general English morphology (plural, past, -ing, -ly, -er and irregular verbs).
"""
import json
import os
import re

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "ste-simplify")
DEFAULT_PATH = os.path.join(CONFIG_DIR, "dictionary.json")

# Common irregular verbs: past or participle -> base form. General English, not from the standard.
IRREGULAR = {
    "arose": "arise", "arisen": "arise", "ate": "eat", "eaten": "eat", "awoke": "awake", "awoken": "awake",
    "bore": "bear", "borne": "bear", "beat": "beat", "beaten": "beat", "became": "become", "began": "begin",
    "begun": "begin", "bent": "bend", "bet": "bet", "bound": "bind", "bit": "bite", "bitten": "bite",
    "bled": "bleed", "blew": "blow", "blown": "blow", "broke": "break", "broken": "break", "bred": "breed",
    "brought": "bring", "built": "build", "burnt": "burn", "burst": "burst", "bought": "buy", "caught": "catch",
    "chose": "choose", "chosen": "choose", "clung": "cling", "came": "come", "cost": "cost", "crept": "creep",
    "dealt": "deal", "dug": "dig", "did": "do", "done": "do", "drew": "draw", "drawn": "draw",
    "dreamt": "dream", "drank": "drink", "drunk": "drink", "drove": "drive", "driven": "drive", "dwelt": "dwell",
    "fell": "fall", "fallen": "fall", "fed": "feed", "felt": "feel", "fought": "fight", "found": "find",
    "fled": "flee", "flung": "fling", "flew": "fly", "flown": "fly", "forbade": "forbid", "forbidden": "forbid",
    "forgot": "forget", "forgotten": "forget", "forgave": "forgive", "forgiven": "forgive", "froze": "freeze",
    "frozen": "freeze", "got": "get", "gotten": "get", "gave": "give", "given": "give", "went": "go",
    "gone": "go", "ground": "grind", "grew": "grow", "grown": "grow", "hung": "hang", "had": "have",
    "has": "have", "heard": "hear", "hid": "hide", "hidden": "hide", "hit": "hit", "held": "hold",
    "hurt": "hurt", "kept": "keep", "knelt": "kneel", "knew": "know", "known": "know", "laid": "lay",
    "led": "lead", "leant": "lean", "leapt": "leap", "learnt": "learn", "left": "leave", "lent": "lend",
    "lay": "lie", "lain": "lie", "lit": "light", "lost": "lose", "made": "make", "meant": "mean", "met": "meet",
    "mistook": "mistake", "mistaken": "mistake", "overcame": "overcome", "overrode": "override",
    "overridden": "override", "paid": "pay", "proved": "prove", "proven": "prove", "quit": "quit",
    "rode": "ride", "ridden": "ride", "rang": "ring", "rung": "ring", "rose": "rise", "risen": "rise",
    "ran": "run", "said": "say", "saw": "see", "seen": "see", "sought": "seek", "sold": "sell", "sent": "send",
    "set": "set", "sewn": "sew", "shook": "shake", "shaken": "shake", "shed": "shed", "shone": "shine",
    "shot": "shoot", "showed": "show", "shown": "show", "shrank": "shrink", "shrunk": "shrink", "shut": "shut",
    "sang": "sing", "sung": "sing", "sank": "sink", "sunk": "sink", "sat": "sit", "slept": "sleep",
    "slid": "slide", "slung": "sling", "slit": "slit", "smelt": "smell", "spoke": "speak", "spoken": "speak",
    "sped": "speed", "spelt": "spell", "spent": "spend", "spilt": "spill", "spun": "spin", "spat": "spit",
    "split": "split", "spoilt": "spoil", "spread": "spread", "sprang": "spring", "sprung": "spring",
    "stood": "stand", "stole": "steal", "stolen": "steal", "stuck": "stick", "stung": "sting", "stank": "stink",
    "strode": "stride", "struck": "strike", "strung": "string", "strove": "strive", "striven": "strive",
    "swore": "swear", "sworn": "swear", "swept": "sweep", "swelled": "swell", "swollen": "swell",
    "swam": "swim", "swum": "swim", "swung": "swing", "took": "take", "taken": "take", "taught": "teach",
    "tore": "tear", "torn": "tear", "told": "tell", "thought": "think", "threw": "throw", "thrown": "throw",
    "thrust": "thrust", "trod": "tread", "trodden": "tread", "understood": "understand", "undertook": "undertake",
    "undertaken": "undertake", "underwent": "undergo", "undergone": "undergo", "upset": "upset",
    "woke": "wake", "woken": "wake", "wore": "wear", "worn": "wear", "wove": "weave", "woven": "weave",
    "wept": "weep", "won": "win", "wound": "wind", "withdrew": "withdraw", "withdrawn": "withdraw",
    "withheld": "withhold", "wrung": "wring", "wrote": "write", "written": "write", "rewrote": "rewrite",
    "rewritten": "rewrite", "read": "read", "rebuilt": "rebuild", "reset": "reset", "put": "put", "cut": "cut",
    "let": "let", "shut down": "shut down", "fit": "fit", "fitted": "fit", "outdid": "outdo", "outdone": "outdo",
    "better": "good", "best": "good", "worse": "bad", "worst": "bad", "more": "many", "most": "many",
    "less": "little", "least": "little", "further": "far", "farther": "far", "furthest": "far",
    "children": "child", "men": "man", "women": "woman", "people": "person", "feet": "foot", "teeth": "tooth",
    "mice": "mouse", "data": "datum", "criteria": "criterion", "indices": "index", "analyses": "analysis",
}

# Numbers are not dictionary words, and STE permits them.
NUMBERS = set("""zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen
sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand
million billion""".split())

PARTICIPLES = {k for k, v in IRREGULAR.items() if k.endswith(("en", "n", "t", "d", "ne", "ng", "ck", "ht"))}

DOUBLE = re.compile(r"([bdfgklmnprtvz])\1$")

# suffix, replacement, kind, parts of speech the base must have for this form
SUFFIXES = [
    ("ies", "y", "plural", {"n", "v", "TN"}), ("es", "", "plural", {"n", "v", "TN"}),
    ("s", "", "plural", {"n", "v", "TN"}), ("ied", "y", "past", {"v"}), ("ed", "", "past", {"v"}),
    ("ed", "e", "past", {"v"}), ("d", "", "past", {"v"}), ("ying", "ie", "ing", {"v"}),
    ("ing", "", "ing", {"v"}), ("ing", "e", "ing", {"v"}), ("ily", "y", "ly", {"adj"}),
    ("ly", "", "ly", {"adj"}), ("ally", "", "ly", {"adj"}), ("ly", "le", "ly", {"adj"}),
    ("ier", "y", "comparative", {"adj", "adv"}), ("iest", "y", "comparative", {"adj", "adv"}),
    ("er", "", "comparative", {"adj", "adv"}), ("est", "", "comparative", {"adj", "adv"}),
    ("r", "", "comparative", {"adj", "adv"}), ("st", "", "comparative", {"adj", "adv"}),
]


def candidates(w):
    """Yield (base, kind, parts of speech) for each way to read w as an inflected form."""
    if w in IRREGULAR:
        base = IRREGULAR[w]
        kind = "plural" if base in ("child", "man", "woman", "person", "foot", "tooth", "mouse", "datum",
                                    "criterion", "index", "analysis") else \
            "comparative" if base in ("good", "bad", "many", "little", "far") else "past"
        yield base, kind, {"n"} if kind == "plural" else {"adj", "adv"} if kind == "comparative" else {"v"}
    for suf, rep, kind, pos in SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 2:
            stem = w[:-len(suf)]
            yield stem + rep, kind, pos
            if rep == "" and DOUBLE.search(stem):  # stopped -> stop, bigger -> big
                yield stem[:-1], kind, pos


def find_path(explicit=None):
    if explicit:  # a path that the user gives must exist
        p = os.path.expanduser(explicit)
        return p if os.path.isfile(p) else None
    for p in (os.environ.get("STE_DICTIONARY"), DEFAULT_PATH):
        if p and os.path.isfile(os.path.expanduser(p)):
            return os.path.expanduser(p)
    return None


class MissingDictionary(Exception):
    pass


class Dictionary:
    def __init__(self, data):
        self.entries = data["entries"]
        self.forms = {}         # approved form -> [entries]
        self.heads = {}         # approved headword -> set(pos)
        self.not_approved = {}  # not approved word or phrase -> [entries]
        self.na_pos = {}        # not approved word -> set(pos)
        self.phrases = {}       # tuple(tokens) -> ("ok" | "na", key)
        self.prefix_re = None
        for e in self.entries:
            if e["word"] == "re-" and not e["approved"]:
                self.prefix_re = e
            if e["approved"]:
                self.heads.setdefault(e["word"], set()).add(e["pos"])
                for f in e.get("forms", []):
                    self.forms.setdefault(f, []).append(e)
                    if " " in f:
                        self.phrases[tuple(f.split())] = ("ok", f)
            else:
                for k in e.get("keys", [e["word"]]):
                    self.not_approved.setdefault(k, []).append(e)
                    self.na_pos.setdefault(k, set()).add(e["pos"])
                    if " " in k:
                        self.phrases.setdefault(tuple(k.split()), ("na", k))
        self.max_phrase = max((len(k) for k in self.phrases), default=1)
        self.verbs = {w for w, p in self.heads.items() if "v" in p} | \
                     {w for w, p in self.na_pos.items() if "v" in p and " " not in w}

    @classmethod
    def load(cls, path=None):
        p = find_path(path)
        if not p:
            raise MissingDictionary(
                "No STE dictionary found. Make it one time (the command downloads the PDF from ASD):\n"
                "  ste prepare\n"
                f"It writes {DEFAULT_PATH}. Or pass --dictionary FILE, or set STE_DICTIONARY.\n"
                "Request the free PDF at https://www.asd-ste100.org")
        with open(p, encoding="utf-8") as f:
            return cls(json.load(f))

    def is_approved_form(self, w):
        if w in self.forms or w in NUMBERS:
            return True
        # Plurals of approved nouns are permitted
        for base, kind, _ in candidates(w):
            if kind == "plural" and "n" in self.heads.get(base, ()):
                return True
        return False

    def approved_pos(self, w):
        out = set()
        for e in self.forms.get(w, []):
            out.add(e["pos"])
        for base, kind, _ in candidates(w):
            if kind == "plural" and "n" in self.heads.get(base, ()):
                out.add("n")
        return out

    def lookup_not_approved(self, w):
        """Return (key, entries, kind) when w is a not approved word or an inflected form of one."""
        if w in self.not_approved:
            return w, self.not_approved[w], "word"
        for base, kind, pos in candidates(w):
            if base in self.not_approved and (self.na_pos[base] & pos):
                return base, self.not_approved[base], kind
        return None

    def lookup_base(self, w):
        """Return (base, kind) when w is an unlisted form of an approved word (for example "using")."""
        for base, kind, pos in candidates(w):
            if base in self.heads and (self.heads[base] & pos) and base != w:
                return base, kind
        return None
