"""Find the prose in a file.

Each function returns a list of Line objects. A Line keeps its number and a
masked copy of the text: code, URLs, paths, markup and other non-prose parts
become spaces, so columns stay the same as in the file. Inline code becomes
a run of CODE_CHAR, which counts as one word and is never checked.
"""
import os
import re

CODE_CHAR = "\u00a7"  # the section sign
CELL_CHAR = "\u00a6"  # broken bar: a table cell border, read as a sentence boundary

PROSE_EXT = {".md", ".markdown", ".mdx", ".mdc", ".txt", ".text", ".rst", ".yaml", ".yml"}
HASH_COMMENT_EXT = {".py", ".sh", ".bash", ".zsh", ".rb", ".pl", ".r", ".toml", ".ex", ".exs", ".nim"}
SLASH_COMMENT_EXT = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".swift", ".go", ".java", ".kt", ".kts",
                     ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".rs", ".scala", ".dart", ".php", ".css",
                     ".scss", ".less", ".m", ".mm", ".zig"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", ".turbo",
             "vendor", ".idea", ".vscode", "coverage", ".mypy_cache", ".pytest_cache", ".tox"}


class Line:
    __slots__ = ("no", "text", "kind", "indent")

    def __init__(self, no, text, kind="prose", indent=0):
        self.no, self.text, self.kind, self.indent = no, text, kind, indent

    def __repr__(self):
        return f"Line({self.no}, {self.kind}, {self.text!r})"


def blank(m):
    return " " * (m.end() - m.start())


def blank_keep_end(m):
    """Blank a match, but keep the punctuation at its end: it can end a sentence."""
    t = m.group(0)
    core = t.rstrip(".,;:!?'\"")
    return " " * len(core) + t[len(core):]


def code_mark(m):
    n = m.end() - m.start()
    return CODE_CHAR + " " * (n - 1)


URL = re.compile(r"\b(?:https?|ftp|file|mailto|ssh|git)://[^\s)>\]]+|\bwww\.[^\s)>\]]+|<[^>\s]+@[^>\s]+>|\b[\w.+-]+@[\w-]+\.[\w.]+\b")
PATHISH = re.compile(r"(?<![\w§])(?:~|\.{1,2})?(?:[\w.@%+-]*[/\\][\w.@%+*{}$<>-]*)+|"
                     r"(?<![\w§])[\w-]+\.(?:md|mdx|py|js|ts|tsx|jsx|json|ya?ml|toml|txt|sh|css|html?|swift|go|rs|"
                     r"rb|java|kt|lock|cfg|ini|env|sql|csv|pdf|png|jpe?g|svg|gif|mp4|mdc|xml|log|zip)\b|"
                     r"(?<![\w-])--?[a-zA-Z][\w-]*|\$\{?[A-Za-z_]\w*\}?|\b\w+\(\)|\b[A-Za-z_]\w*_\w+\b|"
                     r"\b[a-z]+[A-Z]\w*\b|\b\w+(?:\.\w+){2,}\b")


def mask_inline(s, markdown=True):
    """Mask the non-prose parts of one line of text. The length stays the same."""
    if markdown:
        s = re.sub(r"<!--.*?-->", blank, s)
        s = re.sub(r"(`+)(.+?)\1", code_mark, s)
        s = re.sub(r"!\[[^\]]*\]\([^)]*\)", blank, s)                 # images
        s = re.sub(r"(\[[^\]]*\])(\([^)]*\)|\[[^\]]*\])",               # links: keep the text
                   lambda m: " " + m.group(1)[1:-1] + " " + " " * len(m.group(2)), s)
        s = re.sub(r"</?[A-Za-z][^>]*>", blank, s)                      # HTML and JSX tags
        s = re.sub(r"\{[^{}]*\}", blank, s)                              # MDX expressions, placeholders
        s = re.sub(r"(\*\*|__|\*|~~)(?=\S)|(?<=\S)(\*\*|__|\*|~~)", blank, s)  # emphasis markers
        s = re.sub(r"(?<![\w])_(?=\w)|(?<=\w)_(?![\w])", " ", s)
    s = URL.sub(blank_keep_end, s)
    s = PATHISH.sub(blank_keep_end, s)
    return s


LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(\[[ xX]\]\s+)?")


def markdown_lines(text, mdx=False):
    out = []
    lines = text.split("\n")
    i = 0
    fence = None
    in_comment = False
    # front matter: check only the description value
    if lines and lines[0].strip() == "---":
        j = 1
        while j < len(lines) and lines[j].strip() != "---":
            j += 1
        if j < len(lines):
            out.extend(yaml_lines("\n".join(lines[1:j]), offset=1))
            i = j + 1
    while i < len(lines):
        raw = lines[i]
        no = i + 1
        i += 1
        st = raw.strip()
        if fence:
            if st.startswith(fence):
                fence = None
            continue
        m = re.match(r"^\s*(`{3,}|~{3,})", raw)
        if m:
            fence = m.group(1)
            out.append(Line(no, "", "break"))
            continue
        if in_comment:
            if "-->" in raw:
                in_comment = False
            continue
        if "<!--" in raw and "-->" not in raw.split("<!--", 1)[1]:
            in_comment = True
            raw = raw.split("<!--", 1)[0]
        if not st:
            out.append(Line(no, "", "break"))
            continue
        if mdx and re.match(r"^\s*(import|export)\s", raw):
            out.append(Line(no, "", "break"))
            continue
        if re.match(r"^\s*\[[^\]]+\]:\s*\S+", raw):  # link reference definitions
            continue
        if re.match(r"^\s*\|?\s*:?-{3,}", raw) and set(st) <= set("|:- "):  # table separator
            continue
        if re.match(r"^\s*([-*_])(\s*\1){2,}\s*$", raw):  # horizontal rule
            out.append(Line(no, "", "break"))
            continue
        kind = "prose"
        s = raw
        h = re.match(r"^(\s*#{1,6}\s+)", s)
        if h:
            kind = "heading"
            s = " " * len(h.group(1)) + s[len(h.group(1)):]
        q = re.match(r"^(\s*(?:>\s*)+)", s)
        if q:
            s = " " * len(q.group(1)) + s[len(q.group(1)):]
        lm = LIST_RE.match(s)
        indent = len(s) - len(s.lstrip())
        if lm:
            kind = "list"
            s = " " * lm.end() + s[lm.end():]
        if st.startswith("|"):
            kind = "table"
            s = s.replace("|", CELL_CHAR)
        out.append(Line(no, mask_inline(s), kind, indent))
    return out


def rst_lines(text):
    out = []
    skip_deeper = None    # skip indented lines deeper than this (literal blocks, directives)
    literal_next = None   # indent of a paragraph that ended with "::"
    for idx, raw in enumerate(text.split("\n")):
        no = idx + 1
        st = raw.strip()
        ind = len(raw) - len(raw.lstrip())
        if not st:
            out.append(Line(no, "", "break"))
            if literal_next is not None:
                skip_deeper, literal_next = literal_next, None
            continue
        if skip_deeper is not None:
            if ind > skip_deeper:
                continue
            skip_deeper = None
        m = re.match(r"^\.\.\s+([\w:-]+)::", st)
        if m:
            if m.group(1) in ("note", "warning", "caution", "tip", "important", "attention", "hint"):
                s = re.sub(r"^\s*\.\.\s+[\w-]+::", blank, raw)
                out.append(Line(no, mask_inline(s, markdown=False), "prose", ind))
            else:
                skip_deeper = ind
            continue
        if st.startswith(".. ") or st == "..":  # comments and link targets
            skip_deeper = ind
            continue
        if re.fullmatch(r"([=\-~^\"'`#*+])\1{2,}", st):  # section title underline or overline
            if out and out[-1].no == no - 1 and out[-1].kind != "break":
                out[-1].kind = "heading"
            continue
        s = raw
        if st.endswith("::"):
            literal_next = ind
            s = re.sub(r"::\s*$", lambda m: ":" + " " * (len(m.group(0)) - 1), s)
        s = re.sub(r"``.+?``", code_mark, s)
        s = re.sub(r":[\w:-]+:`[^`]*`", code_mark, s)
        s = re.sub(r"`([^`<]*?)\s*<[^>]*>`_{1,2}",
                   lambda m: " " + m.group(1) + " " * (len(m.group(0)) - len(m.group(1)) - 1), s)
        s = re.sub(r"`[^`]*`_{0,2}", code_mark, s)
        s = re.sub(r"\*\*|\*", lambda m: " " * len(m.group(0)), s)
        lm = LIST_RE.match(s)
        kind = "prose"
        if lm:
            kind = "list"
            s = " " * lm.end() + s[lm.end():]
        out.append(Line(no, mask_inline(s, markdown=False), kind, ind))
    return out


def yaml_lines(text, keys=("description",), offset=0):
    """Return the lines of the values of the given keys (also block scalars)."""
    out = []
    lines = text.split("\n")
    key_re = re.compile(r"^(\s*-?\s*)(%s)\s*:\s?(.*)$" % "|".join(map(re.escape, keys)))
    i = 0
    while i < len(lines):
        m = key_re.match(lines[i])
        if not m:
            i += 1
            continue
        base = len(m.group(1))
        val = m.group(3)
        start = len(lines[i]) - len(val)
        if val.strip() in ("|", ">", "|-", ">-", "|+", ">+") or val.strip() == "":
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > base):
                if lines[j].strip():
                    out.append(Line(j + 1 + offset, mask_inline(lines[j]), "prose"))
                j += 1
            out.append(Line(j + offset, "", "break"))
            i = j
            continue
        quoted = val.lstrip()[:1] in ("'", '"')
        s = " " * start + val
        if quoted:
            q = val.lstrip()[0]
            s = s.replace(q, " ", 1)
            if s.rstrip().endswith(q):
                s = s.rstrip()[:-1]
        out.append(Line(i + 1 + offset, mask_inline(s), "prose"))
        j = i + 1  # plain or quoted value that goes on over more lines
        while j < len(lines) and lines[j].strip() and len(lines[j]) - len(lines[j].lstrip()) > base \
                and not re.match(r"^\s*[\w-]+\s*:", lines[j]):
            t = lines[j]
            if quoted and t.rstrip().endswith(q):
                t = t.rstrip()[:-1]
            out.append(Line(j + 1 + offset, mask_inline(t), "prose"))
            j += 1
        out.append(Line(j + offset, "", "break"))
        i = j
    return out


def comment_lines(text, ext):
    out = []
    in_block = False
    in_doc = None
    for idx, raw in enumerate(text.split("\n")):
        no = idx + 1
        s = None
        if ext in SLASH_COMMENT_EXT:
            if in_block:
                end = raw.find("*/")
                s = raw if end < 0 else raw[:end] + " " * (len(raw) - end)
                in_block = end < 0
                s = re.sub(r"^(\s*)\*(?!/)", lambda m: m.group(1) + " ", s)
            else:
                m = re.search(r"(?<!:)//+\s?|/\*+", raw)
                if m and not _in_string(raw, m.start()):
                    s = " " * m.end() + raw[m.end():]
                    if m.group(0).startswith("/*"):
                        end = s.find("*/")
                        in_block = end < 0
                        if end >= 0:
                            s = s[:end] + " " * (len(s) - end)
        else:
            if ext == ".py":
                if in_doc:
                    end = raw.find(in_doc)
                    s = raw if end < 0 else raw[:end]
                    if end >= 0:
                        in_doc = None
                else:
                    m = re.match(r'^(\s*)(?:[rRbBuU]?)("""|\'\'\')', raw)
                    if m:
                        rest = raw[m.end():]
                        end = rest.find(m.group(2))
                        s = " " * m.end() + (rest if end < 0 else rest[:end])
                        if end < 0:
                            in_doc = m.group(2)
            if s is None:
                m = re.search(r"#+\s?", raw)
                if m and not _in_string(raw, m.start()) and not raw.startswith("#!"):
                    s = " " * m.end() + raw[m.end():]
        if s is None or not s.strip():
            out.append(Line(no, "", "break"))
            continue
        out.append(Line(no, mask_inline(s, markdown=True), "prose"))
    return out


def _in_string(s, pos):
    return s[:pos].count('"') % 2 == 1 or s[:pos].count("'") % 2 == 1


def scan_text(text, ext, comments=False, yaml_keys=("description",)):
    ext = ext.lower()
    if ext in (".md", ".markdown", ".mdc"):
        return markdown_lines(text)
    if ext == ".mdx":
        return markdown_lines(text, mdx=True)
    if ext == ".rst":
        return rst_lines(text)
    if ext in (".yaml", ".yml"):
        return yaml_lines(text, yaml_keys)
    if ext in (".txt", ".text", ""):
        return [Line(i + 1, mask_inline(l, markdown=False), "prose" if l.strip() else "break")
                for i, l in enumerate(text.split("\n"))]
    if comments and (ext in HASH_COMMENT_EXT or ext in SLASH_COMMENT_EXT):
        return comment_lines(text, ext)
    return []


def wanted(path, comments=False):
    ext = os.path.splitext(path)[1].lower()
    return ext in PROSE_EXT or (comments and (ext in HASH_COMMENT_EXT or ext in SLASH_COMMENT_EXT))


def iter_files(targets, comments=False, exclude=()):
    import fnmatch
    for t in targets:
        if os.path.isdir(t):
            for root, dirs, files in os.walk(t):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")
                                 and not any(fnmatch.fnmatch(os.path.join(root, d), x) for x in exclude))
                for f in sorted(files):
                    p = os.path.join(root, f)
                    if f.startswith(".ste-allow"):
                        continue
                    if wanted(p, comments) and not any(fnmatch.fnmatch(p, x) or fnmatch.fnmatch(f, x) for x in exclude):
                        yield p
        elif os.path.isfile(t):
            yield t
