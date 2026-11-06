import os
import shutil
import tempfile
import unittest

from helpers import check, mini_dictionary, read, run_cli
from ste_simplify import fix


class PlanTests(unittest.TestCase):
    def plan(self, text):
        fs = check(text)
        return fix.plan_for(mini_dictionary(), [("t.md", fs)])

    def test_safe_and_ambiguous(self):
        p = {i["word"]: i for i in self.plan("You should utilize the main tool.")}
        self.assertEqual(p["utilize"]["replacement"], "use")
        self.assertEqual(p["main"]["replacement"], "primary")
        self.assertIsNone(p["should"]["replacement"])
        self.assertEqual(p["should"]["reason"], "more than one alternative")

    def test_part_of_speech_change_is_not_safe(self):
        p = self.plan("Stop the tool according to the file.")[0]
        self.assertIsNone(p["replacement"])
        self.assertEqual(p["reason"], "the alternative is a different part of speech")

    def test_word_in_a_different_position_is_not_safe(self):
        # "utilize" is a verb entry. After "the", the word is possibly a noun: no safe replacement.
        p = self.plan("Open the utilize file.")[0]
        self.assertIsNone(p["replacement"])
        self.assertEqual(p["reason"], "the word is possibly not a verb here")

    def test_part_of_hyphenated_word_is_not_safe(self):
        p = self.plan("Use the main-tool file.")[0]
        self.assertIsNone(p["replacement"])

    def test_inflected_form_is_not_safe(self):
        p = self.plan("You utilized the tool.")[0]
        self.assertIsNone(p["replacement"])

    def test_apply_keeps_case_and_article(self):
        text = "Utilize the tool. It is an issue.\n"
        items = [i for i in self.plan(text) if i["replacement"]]
        new, done = fix.apply_file(text, items)
        self.assertEqual(new, "Use the tool. It is a problem.\n")
        self.assertEqual(len(done), 2)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "a.md")
        with open(self.path, "w") as f:
            f.write("You should utilize the tool.\n\n```\nutilize\n```\n")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_plan_does_not_change_the_file(self):
        code, out = run_cli(fix.main, [self.path])
        self.assertIn("[1] ", out)
        self.assertIn("utilize -> use", out)
        self.assertIn("Sentences to rewrite", out)
        self.assertIn("You should utilize the tool.", read(self.path))

    def test_apply_changes_prose_only(self):
        run_cli(apply_main, [self.path])
        self.assertEqual(read(self.path), "You should use the tool.\n\n```\nutilize\n```\n")

    def test_stdin_apply_prints_text(self):
        code, out = run_cli(apply_main, ["--format", "json", "-"], stdin="Utilize the tool.\n")
        import json
        self.assertEqual(json.loads(out)["text"], "Use the tool.\n")


class PushbackTests(unittest.TestCase):
    TEXT = "Utilize the tool. It is an issue. Utilize the file.\n"

    def run_apply(self, *args):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "a.md")
            with open(p, "w") as f:
                f.write(self.TEXT)
            run_cli(apply_main, [*args, p])
            return read(p)
        finally:
            shutil.rmtree(d)

    def test_skip(self):
        self.assertEqual(self.run_apply("--skip", "2"), "Use the tool. It is an issue. Use the file.\n")

    def test_only(self):
        self.assertEqual(self.run_apply("--only", "2-3"), "Utilize the tool. It is a problem. Use the file.\n")

    def test_ids(self):
        self.assertEqual(fix.ids("1, 3-5"), {1, 3, 4, 5})


def apply_main(argv):
    return fix.main(["--apply", *argv])


if __name__ == "__main__":
    unittest.main()
