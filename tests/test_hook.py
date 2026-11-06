import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from contextlib import redirect_stderr, redirect_stdout

from helpers import MINI
from ste_simplify import hook


def run_hook(event):
    event.setdefault("session_id", uuid.uuid4().hex)
    err, out, old = io.StringIO(), io.StringIO(), sys.stdin
    sys.stdin = io.StringIO(json.dumps(event))
    try:
        with redirect_stderr(err), redirect_stdout(out):
            code = hook.main(["--dictionary", MINI])
    finally:
        sys.stdin = old
    return code, err.getvalue(), out.getvalue()


class PlanTests(unittest.TestCase):
    def test_plan_with_errors_is_blocked(self):
        code, err, _ = run_hook({"tool_name": "ExitPlanMode", "tool_input": {"plan": "You should stop the tool."}})
        self.assertEqual(code, 2)
        self.assertIn("should", err)
        self.assertIn("ExitPlanMode", err)

    def test_clean_plan_and_cyrillic_plan_pass(self):
        self.assertEqual(run_hook({"tool_name": "ExitPlanMode", "tool_input": {"plan": "Stop the tool."}})[0], 0)
        plan = "Зупини інструмент. You should stop."
        self.assertEqual(run_hook({"tool_name": "ExitPlanMode", "tool_input": {"plan": plan}})[0], 0)

    def test_hook_stops_after_the_limit(self):
        event = {"tool_name": "ExitPlanMode", "tool_input": {"plan": "You should stop the tool."},
                 "session_id": uuid.uuid4().hex}
        codes = [run_hook(dict(event))[0] for _ in range(hook.MAX_REPORTS + 1)]
        self.assertEqual(codes, [2] * hook.MAX_REPORTS + [0])
        self.assertIn("stopped", run_hook(dict(event))[2])


class FileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.skill = os.path.join(self.dir, "SKILL.md")
        with open(self.skill, "w") as f:
            f.write("You should stop the tool.\n\nStop the tool.\n")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def edit(self, path, new):
        return run_hook({"tool_name": "Edit", "tool_input": {"file_path": path, "new_string": new}})[0]

    def test_only_the_changed_lines(self):
        self.assertEqual(self.edit(self.skill, "Stop the tool."), 0)  # line 3 is clean, line 1 is old text
        self.assertEqual(self.edit(self.skill, "You should stop the tool."), 2)

    def test_write_checks_all_lines(self):
        code = run_hook({"tool_name": "Write", "tool_input": {"file_path": self.skill}})[0]
        self.assertEqual(code, 2)

    def test_other_files_are_not_checked(self):
        readme = os.path.join(self.dir, "README.md")
        shutil.copy(self.skill, readme)
        self.assertEqual(self.edit(readme, "You should stop the tool."), 0)
        self.assertTrue(hook.is_instruction_file("/x/.claude/agents/review.md", hook.INSTRUCTION_FILES.split(",")))


if __name__ == "__main__":
    unittest.main()
