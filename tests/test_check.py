import json
import os
import shutil
import tempfile
import unittest

from helpers import FIXTURES, check, checker, read, rules, run_cli
from ste_simplify import check as check_mod
from ste_simplify.check import count_words, split_sentences


class WordTests(unittest.TestCase):
    def test_not_approved_word_has_alternatives_and_example(self):
        fs = check("You should stop the tool.")
        f = [f for f in fs if f.rule == "not-approved"][0]
        self.assertEqual(f.word, "should")
        alts = [a["text"] for g in f.data["alternatives"] for a in g["alternatives"]]
        self.assertEqual(alts, ["MUST", "IF"])
        self.assertEqual(f.data["alternatives"][0]["ste_example"], "YOU MUST STOP THE TOOL.")
        self.assertEqual((f.line, f.col), (1, 5))

    def test_inflected_form_of_a_not_approved_word(self):
        f = [f for f in check("You utilized the tool.") if f.rule == "not-approved"][0]
        self.assertEqual(f.key, "utilize")

    def test_phrase(self):
        f = [f for f in check("Stop the tool in case of a fault.") if f.rule == "not-approved"][0]
        self.assertEqual(f.key, "in case of")

    def test_wrong_part_of_speech(self):
        self.assertIn("wrong-pos", rules(check("Check the file.")))
        self.assertNotIn("wrong-pos", rules(check("Do a check of the file.")))

    def test_unlisted_form_and_ing(self):
        f = [f for f in check("Stop the tool shortly.") if f.rule == "wrong-form"]
        self.assertEqual(f[0].key, "short")
        f = [f for f in check("Start the tool before using the file.") if f.rule == "ing-form"]
        self.assertEqual(f[0].key, "use")

    def test_approved_noun_plural(self):
        self.assertEqual(rules(check("Use the tools.")), [])

    def test_unknown_word_and_allow_list(self):
        self.assertIn("unknown-word", rules(check("Use the gizmo.")))
        self.assertEqual(rules(check("Use the linter.")), [])
        self.assertEqual(rules(check("Use the linters.")), [])
        self.assertEqual(rules(check("Open the pull request.")), [])

    def test_names_acronyms_and_quotes_are_skipped(self):
        self.assertEqual(rules(check("Use the Frobnicator tool and the API.")), [])
        self.assertEqual(rules(check('If the text is "should utilize", use the tool.')), [])

    def test_code_urls_paths_are_skipped(self):
        fs = check(read(os.path.join(FIXTURES, "before.md")))
        lines = sorted({f.line for f in fs if f.rule in ("not-approved", "wrong-pos")})
        self.assertEqual(lines, [3, 8])  # front matter description and the prose line; not code, URL or path

    def test_ignore_comments(self):
        text = "<!-- ste-ignore -->\nYou should stop.\nYou should stop.\n"
        self.assertEqual([f.line for f in check(text) if f.word == "should"], [3])
        text = "<!-- ste-disable -->\nYou should stop.\n<!-- ste-enable -->\nYou should stop.\n"
        self.assertEqual([f.line for f in check(text) if f.word == "should"], [4])


class RuleTests(unittest.TestCase):
    def test_sentence_length_procedure_and_description(self):
        proc = "Use the tool " + "and the tool " * 6 + "to start the file."
        self.assertIn("sentence-length", rules(check(proc)))
        desc = "The tool " + "and the tool " * 7 + "is short."
        self.assertEqual(count_words(desc), 25)
        self.assertNotIn("sentence-length", rules(check(desc)))
        self.assertIn("sentence-length", rules(check(desc.replace("is short", "is very short"))))

    def test_word_count_rules(self):
        self.assertEqual(count_words("Use the tool (the one in the file) now."), 5)
        self.assertEqual(count_words("Set it to 20 mm."), 4)
        self.assertEqual(count_words("Use a step-by-step file."), 4)

    def test_split_sentences(self):
        self.assertEqual(len(split_sentences("Use the tool, e.g. this one. Then stop.")), 2)
        self.assertEqual(len(split_sentences("Version 1.5 is short. It is.")), 2)

    def test_paragraph_length(self):
        self.assertIn("paragraph-length", rules(check(" ".join(["Use the tool."] * 7))))
        self.assertNotIn("paragraph-length", rules(check(" ".join(["Use the tool."] * 6))))

    def test_passive_voice(self):
        f = [f for f in check("The file is written by the tool.") if f.rule == "passive-voice"]
        self.assertTrue(f and "agent is known" in f[0].message)

    def test_one_instruction(self):
        self.assertIn("one-instruction", rules(check("Open the file and close the tool.")))
        self.assertNotIn("one-instruction", rules(check("Then close the tool.")))

    def test_semicolon_and_contraction(self):
        r = rules(check("Use the tool; it's short."))
        self.assertIn("semicolon", r)
        self.assertIn("contraction", r)

    def test_heading_has_no_sentence_rules(self):
        self.assertEqual(rules(check("# Use the tool and close the file and open the file and do " * 3)), [])


class FormatTests(unittest.TestCase):
    def test_yaml_description_only(self):
        text = "name: should-tool\ndescription: >\n  You should utilize it.\nother: should\n"
        fs = check(text, ".yaml")
        self.assertEqual(sorted({f.line for f in fs if f.word}), [3])

    def test_rst_literal_block(self):
        text = "Use the tool::\n\n    utilize should\n\nYou should stop.\n"
        self.assertEqual([f.line for f in check(text, ".rst") if f.word == "should"], [5])

    def test_code_comments_only_with_option(self):
        text = "x = 1  # You should stop.\ns = 'should'\n"
        self.assertEqual(check(text, ".py"), [])
        ch = checker()
        ch.comments = True
        self.assertEqual([f.line for f in ch.check_text("t.py", text, ".py") if f.word == "should"], [1])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        shutil.copy(os.path.join(FIXTURES, "before.md"), self.dir)
        self.path = os.path.join(self.dir, "before.md")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_text_report_and_exit_code(self):
        code, out = run_cli(check_mod.main, [self.path])
        self.assertEqual(code, 1)
        self.assertIn("Words that are not approved", out)
        self.assertIn("MUST (v): YOU MUST STOP THE TOOL.", out)
        code, _ = run_cli(check_mod.main, ["--fail-on", "never", self.path])
        self.assertEqual(code, 0)

    def test_clean_text_exit_zero(self):
        code, out = run_cli(check_mod.main, ["-"], stdin="Use the tool.\n")
        self.assertEqual(code, 0)

    def test_json_and_sarif(self):
        code, out = run_cli(check_mod.main, ["--format", "json", self.path])
        data = json.loads(out)
        self.assertGreater(data["summary"]["errors"], 0)
        self.assertTrue(all("ste_rule" in f for f in data["files"][0]["findings"]))
        code, out = run_cli(check_mod.main, ["--format", "sarif", self.path])
        sarif = json.loads(out)
        self.assertEqual(sarif["version"], "2.1.0")
        res = sarif["runs"][0]["results"]
        self.assertTrue(res and res[0]["locations"][0]["physicalLocation"]["region"]["startLine"] > 0)

    def test_missing_dictionary(self):
        code = check_mod.main(["--dictionary", os.path.join(self.dir, "none.json"), self.path])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
