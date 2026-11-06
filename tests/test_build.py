import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr

import helpers  # noqa: F401  (sets sys.path)
from ste_simplify import build

COLS = (50.0, 158.0, 288.0, 418.0)


class Page:
    """Make a synthetic page in the `pdftotext -bbox` format, with the dictionary table layout."""

    def __init__(self):
        self.words = []
        self.y = 100.0

    def put(self, x, y, text):
        for w in text.split():
            self.words.append((x, y, w))
            x += len(w) * 5.5 + 3

    def row(self, *cells, indent=(0, 0, 0, 0)):
        for i, c in enumerate(cells):
            if c:
                self.put(COLS[i] + indent[i], self.y, c)
        self.y += 12

    def gap(self):
        self.y += 6

    def xhtml(self, page_id="2-1-A1"):
        self.put(180, 40, "ASD-STE100 Simplified Technical English")
        self.put(50, 60, "Word")
        self.put(158, 60, "Approved meaning/")
        self.put(288, 66, "STE EXAMPLE")
        self.put(418, 66, "Non-STE example")
        self.put(50, 72, "(part of speech)")
        self.put(158, 72, "ALTERNATIVES")
        self.put(50, 722, "Issue 9")
        self.put(250, 722, "Part 2 - Dictionary")
        self.put(480, 722, "Page " + page_id)
        out = ['<page width="612" height="792">']
        for x, y, t in self.words:
            out.append(f'<word xMin="{x:.2f}" yMin="{y:.2f}" xMax="{x + len(t) * 5.5:.2f}" yMax="{y + 12:.2f}">{t}</word>')
        out.append("</page>")
        return "<doc>" + "\n".join(out) + "</doc>"


def sample():
    p = Page()
    p.row("commence (v)", "START (v)", "START THE TEST.", "Commence the test.")
    p.row(None, "BEGIN (v)", "BEGIN THE", "Begin the test.")
    p.row(None, None, "TEST.")
    p.gap()
    p.row("SHORT (adj)", "Not long", "USE A SHORT CABLE.")
    p.row("(SHORTER,")
    p.row("SHORTEST)")
    p.gap()
    p.row("OPEN (v),", "1. To move a door", "OPEN THE DOOR.")
    p.row("OPENS,", None, None)
    p.row("OPENED,")
    p.row("OPENED")
    p.row(None, "2. To start a file", "OPEN THE FILE.")
    p.gap()
    p.row("ACCIDENTAL", "That does not occur on", "PREVENT ACCIDENTAL")
    p.row("(adj)", "purpose", "OPERATION.")
    p.gap()
    p.row("utilize (v)", "USE (v)", "USE THE TOOL.", "Utilize the tool.")
    p.row(None, "You can use a more", indent=(0, 40, 0, 0))
    p.row(None, "accurate verb.", indent=(0, 40, 0, 0))
    p.gap()
    p.row("ELECTROMAG-", "Related to magnets", "AN ELECTROMAGNETIC")
    p.row("NETIC (adj)", None, "FORCE.")
    p.gap()
    p.row("case (in case of)", "IF (conj)", "IF THERE IS A FIRE,", "In case of fire, stop.")
    p.row("(prep)", None, "STOP.")
    return p.xhtml()


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = {(e["word"], e["pos"]): e for e in build.parse(sample())}

    def test_not_approved_with_two_alternatives(self):
        e = self.entries[("commence", "v")]
        self.assertFalse(e["approved"])
        self.assertEqual([g["alternatives"][0]["text"] for g in e["alternatives"]], ["start", "begin"])
        self.assertEqual(e["alternatives"][1]["ste_example"], "BEGIN THE TEST.")
        self.assertEqual(e["alternatives"][0]["non_ste_example"], "Commence the test.")

    def test_adjective_forms_in_parentheses(self):
        self.assertEqual(self.entries[("short", "adj")]["forms"], ["short", "shorter", "shortest"])

    def test_verb_forms_and_numbered_meanings(self):
        e = self.entries[("open", "v")]
        self.assertEqual(e["forms"], ["open", "opened", "opens"])
        self.assertEqual([m["meaning"] for m in e["meanings"]], ["To move a door", "To start a file"])
        self.assertEqual(e["meanings"][1]["ste_example"], "OPEN THE FILE.")

    def test_headword_on_two_lines(self):
        e = self.entries[("accidental", "adj")]
        self.assertEqual(e["meanings"][0]["meaning"], "That does not occur on purpose")

    def test_help_text(self):
        self.assertEqual(self.entries[("utilize", "v")]["help"], ["You can use a more accurate verb."])

    def test_word_broken_at_line_end(self):
        self.assertIn(("electromagnetic", "adj"), self.entries)

    def test_phrase_keys(self):
        self.assertEqual(self.entries[("case (in case of)", "prep")]["keys"], ["in case of"])

    def test_intro_pages_are_skipped(self):
        p = Page()
        p.row("main (adj)", "PRIMARY (adj)", "THE PRIMARY CAUSE.", "The main cause.")
        self.assertEqual(build.parse(p.xhtml(page_id="2-0-3")), [])


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_download_checks_the_file_type(self):
        src = os.path.join(self.dir, "a.pdf")
        with open(src, "wb") as f:
            f.write(b"%PDF-1.7 test")
        dest = os.path.join(self.dir, "cache", "b.pdf")
        self.assertEqual(build.download("file://" + src, dest), dest)
        with open(src, "wb") as f:
            f.write(b"<html>not a pdf</html>")
        self.assertIsNone(build.download("file://" + src, dest + "2"))
        self.assertFalse(os.path.exists(dest + "2.part"))

    def test_no_pdf_shows_the_request_page(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = build.main(["--pdf", os.path.join(self.dir, "missing.pdf")])
        self.assertEqual(code, 2)
        with redirect_stderr(err):
            code = build.main(["--url", "file://" + os.path.join(self.dir, "none.pdf")])
        self.assertEqual(code, 2)
        self.assertIn("ste prepare --pdf", err.getvalue())

    def test_write_compact_and_gzip(self):
        import gzip
        import json
        data = {"entries": [{"word": "a", "approved": True}]}
        for name in ("d.json", "d.json.gz"):
            out = os.path.join(self.dir, name)
            build.write(data, out)
            opener = gzip.open if name.endswith(".gz") else open
            with opener(out, "rt", encoding="utf-8") as f:
                text = f.read()
            self.assertEqual(json.loads(text), data)
            self.assertNotIn("\n", text)


@unittest.skipUnless(os.environ.get("STE_PDF"), "set STE_PDF to the official PDF to run this test")
class RealPdfTest(unittest.TestCase):
    def test_counts(self):
        entries = build.parse(build.bbox_xhtml(os.environ["STE_PDF"]))
        approved = [e for e in entries if e["approved"]]
        self.assertGreater(len(approved), 850)
        self.assertGreater(len(entries) - len(approved), 1250)
        be = [e for e in entries if e["word"] == "be"][0]
        self.assertTrue({"is", "are", "was", "were"} <= set(be["forms"]))


if __name__ == "__main__":
    unittest.main()


class ItWordsParserTests(unittest.TestCase):
    PAGE = """<dl>
<dt id="foo"><span class="icon-dontuse"></span>foolist, foo list <a href="#foo">link</a></dt>
<dd>Don't use <i>foolist</i>. Instead, use <i>barlist</i>.</dd>
<dt id="zap"><span class="icon-dontuse"></span>zap <a href="#zap">link</a></dt>
<dd>Don't use as a verb.</dd>
<dt id="widget">widget <a href="#widget">link</a></dt>
<dd>Use widget for a small UI part.</dd>
<dt id="old"><span class="icon-avoid"></span>stale, the <a href="#old">link</a></dt>
<dd>Avoid in general usage. Instead, use words like <i>fresh</i> or <i>new</i>.</dd>
</dl>"""

    def test_parse(self):
        from ste_simplify import itwords
        d = itwords.parse(self.PAGE)
        self.assertEqual(d["avoid"]["foolist"]["alternatives"], ["barlist"])
        self.assertIn("foo list", d["avoid"])
        self.assertNotIn("zap", d["avoid"])  # it depends on the context
        self.assertEqual(d["avoid"]["the stale"]["alternatives"], ["fresh", "new"])
        self.assertEqual(d["known"], ["widget"])
