"""scripts/red-at.py: does the working tree's version of a test fail on a base ref's code and pass on the working tree?

Each test builds a small git repository with a buggy commit and a fixed one, points red-at at it, and reads the exit
code and the last line it prints.
"""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from support import ROOT, load_script

red_at = load_script("red-at")

BUGGY = "def double(value):\n    return value * 3\n"
FIXED = "def double(value):\n    return value * 2\n"
UNIT_TEST = ("import unittest\nfrom arithmetic import double\n\n\n"
             "class DoubleTests(unittest.TestCase):\n"
             "    def test_double(self):\n        self.assertEqual(double(4), 8)\n")
WATCH_SUITE = ("const assert = require('assert');\nconst fs = require('fs');\n"
               "assert.strictEqual(fs.readFileSync('watch/arithmetic.js', 'utf8').includes('* 2'), true);\n")


class RedAtTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repository = Path(temporary.name) / "repository"
        self.repository.mkdir()
        self.git("init", "-q", "-b", "main")
        # The fixture's .venv is a link to this tree's, and a trailing slash would not ignore a link.
        self.write(".gitignore", "**/.venv\nfrontend/node_modules/\nfrontend/dist/\n")
        # A frontend whose build makes the dist a browser flow serves.
        self.write("frontend/package.json", '{"scripts": {"build": "node -e \\"require(\'fs\').mkdirSync(\'dist\')\\""}}\n')
        venv = self.repository / red_at.compare.VENV
        venv.parent.mkdir(parents=True)
        venv.symlink_to(ROOT / red_at.compare.VENV, target_is_directory=True)
        self.write("laptop/arithmetic.py", BUGGY)
        self.write("watch/arithmetic.js", "exports.double = v => v * 3;\n")
        self.commit("buggy")
        self.buggy = self.git("rev-parse", "HEAD").strip()
        self.write("laptop/arithmetic.py", FIXED)
        self.write("watch/arithmetic.js", "exports.double = v => v * 2;\n")
        self.write("tests/test_arithmetic.py", UNIT_TEST)
        self.write("watch/tests/arithmetic.cjs", WATCH_SUITE)
        self.commit("fixed")
        patcher = patch.object(red_at.compare, "ROOT", self.repository)
        patcher.start()
        self.addCleanup(patcher.stop)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repository), *args], check=True, capture_output=True,
                              text=True, env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                                              "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}).stdout

    def write(self, relative, text):
        path = self.repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def main(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["red-at.py", *args]), contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            code = red_at.main()
        self.output = stdout.getvalue() + stderr.getvalue()
        lines = self.output.strip().splitlines()
        return code, lines[-1] if lines else ""

    def test_a_unit_test_that_fails_at_the_base_and_passes_in_the_working_tree_is_red(self):
        # The buggy commit has no tests/test_arithmetic.py: the working tree's test runs on the base's code.
        code, last = self.main(self.buggy[:7], "tests/test_arithmetic.py")
        self.assertEqual(code, 0, last)
        self.assertEqual(last, f"red at {self.buggy[:7]}: 1 of 1 runs failed there and 1 of 1 passed in the working tree")

    def test_a_test_that_passes_without_the_fix_is_not_red(self):
        self.assertEqual(self.main("HEAD", "tests/test_arithmetic.py"),
                         (1, "not red at HEAD: 0 of 1 runs failed there and 1 of 1 passed in the working tree"))

    def test_a_test_that_fails_in_the_working_tree_is_not_red(self):
        self.write("laptop/arithmetic.py", BUGGY)
        self.assertEqual(self.main(self.buggy, "tests/test_arithmetic.py"),
                         (1, f"not red at {self.buggy}: 1 of 1 runs failed there and 0 of 1 passed in the working tree"))

    def test_a_watch_suite_runs_with_node(self):
        self.assertEqual(self.main(self.buggy, "watch/tests/arithmetic.cjs", "--runs", "3"),
                         (0, f"red at {self.buggy}: 3 of 3 runs failed there and 3 of 3 passed in the working tree"))

    def test_a_named_test_in_a_module_runs_alone(self):
        self.assertEqual(self.main(self.buggy, "tests/test_arithmetic.py", "DoubleTests.test_double")[0], 0)
        self.assertEqual(self.main(self.buggy, "tests/test_arithmetic.py", "DoubleTests.test_missing")[1],
                         f"not red at {self.buggy}: 1 of 1 runs failed there and 0 of 1 passed in the working tree")

    def test_a_browser_flow_runs_as_a_script_after_the_frontend_is_built(self):
        (self.repository / red_at.compare.NODE_MODULES).mkdir(parents=True)
        self.write("tests/flow_arithmetic.py", "import sys\nfrom pathlib import Path\nfrom arithmetic import double\n\n"
                                               "sys.exit(0 if Path('frontend/dist').is_dir() and double(4) == 8 else 1)\n")
        self.assertEqual(self.main(self.buggy, "tests/flow_arithmetic.py"),
                         (0, f"red at {self.buggy}: 1 of 1 runs failed there and 1 of 1 passed in the working tree"))

    def write_hanging_suite(self):
        """A watch suite that starts a child and hangs; the child's pid is appended to the returned file."""
        pids = self.repository.parent / "pids"
        self.write("watch/tests/hang.cjs", "const fs = require('fs');\n"
                                           "const child = require('child_process').spawn('sleep', ['60'], {stdio: 'ignore'});\n"
                                           f"fs.appendFileSync({str(pids)!r}, child.pid + '\\n');\n"
                                           "setTimeout(() => {}, 60000);\n")
        return pids

    def assert_children_killed(self, pids):
        for pid in pids.read_text().split():
            stat = Path(f"/proc/{pid}/stat")
            for _ in range(50):  # Killed, the sleep is reaped by whichever process adopted it.
                if not stat.exists() or stat.read_text().rsplit(")", 1)[1].split()[0] == "Z":
                    break
                time.sleep(0.05)
            else:
                self.fail(f"the test's child {pid} outlived red-at's run")

    def test_a_timeout_kills_the_whole_test_and_counts_as_a_failure(self):
        pids = self.write_hanging_suite()
        with patch.object(red_at, "TIMEOUT_SECONDS", 0.5):
            self.assertEqual(self.main(self.buggy, "watch/tests/hang.cjs"),
                             (1, f"not red at {self.buggy}: 1 of 1 runs failed there and 0 of 1 passed in the working tree"))
        self.assertIn("timed out after 0.5 s", self.output)
        self.assert_children_killed(pids)

    def test_an_interrupt_kills_the_whole_test_and_is_raised(self):
        pids = self.write_hanging_suite()
        communicate = subprocess.Popen.communicate

        def interrupted(process, input=None, timeout=None):
            if timeout is None:
                return communicate(process, input)
            while not pids.exists():  # Ctrl-C once the test has started its child.
                time.sleep(0.05)
            raise KeyboardInterrupt

        with patch.object(subprocess.Popen, "communicate", interrupted), self.assertRaises(KeyboardInterrupt):
            self.main(self.buggy, "watch/tests/hang.cjs")
        self.assert_children_killed(pids)

    def test_the_first_failing_base_run_is_printed_even_when_it_is_not_the_first_run(self):
        counter = self.repository.parent / "counter"
        self.write("watch/tests/second.cjs", "const fs = require('fs');\n"
                                             f"const path = {str(counter)!r};\n"
                                             "const run = (fs.existsSync(path) ? Number(fs.readFileSync(path, 'utf8')) : 0) + 1;\n"
                                             "fs.writeFileSync(path, String(run));\n"
                                             "if (run === 2) throw new Error('the second run fails');\n")
        self.assertEqual(self.main(self.buggy, "watch/tests/second.cjs", "--runs", "2"),
                         (1, f"not red at {self.buggy}: 1 of 2 runs failed there and 2 of 2 passed in the working tree"))
        self.assertIn("Error: the second run fails", self.output)

    def test_a_base_that_cannot_load_the_test_is_not_red(self):
        # The working tree adds halve, which the test imports: at the base the test never runs.
        self.write("laptop/arithmetic.py", FIXED + "\n\ndef halve(value):\n    return value / 2\n")
        self.write("watch/halve.js", "exports.halve = v => v / 2;\n")
        self.write("tests/test_halve.py", "import unittest\nfrom arithmetic import halve\n\n\n"
                                          "class HalveTests(unittest.TestCase):\n"
                                          "    def test_halve(self):\n        self.assertEqual(halve(4), 2)\n")
        self.write("watch/tests/halve.cjs", "require('assert').strictEqual(require('../halve.js').halve(4), 2);\n")
        # harness.cjs reads a watch module with readFileSync, so a missing one throws ENOENT.
        self.write("watch/tests/halve_harness.cjs", "const fs = require('fs');\nconst path = require('path');\n"
                                                    "fs.readFileSync(path.join(__dirname, '..', 'halve.js'), 'utf8');\n")
        for test in ["tests/test_halve.py", "watch/tests/halve.cjs", "watch/tests/halve_harness.cjs"]:
            with self.subTest(test=test):
                self.assertEqual(self.main(self.buggy, test),
                                 (1, f"not red at {self.buggy}: 0 of 1 runs failed there (1 could not load the test) "
                                     "and 1 of 1 passed in the working tree"))
                self.assertIn("base run 1: could not load the test", self.output)

    def test_the_repository_is_left_as_it_was(self):
        self.write("laptop/arithmetic.py", FIXED + "\n")
        before = self.git("status", "--porcelain"), self.git("worktree", "list")
        self.main(self.buggy, "tests/test_arithmetic.py")
        self.assertEqual((self.git("status", "--porcelain"), self.git("worktree", "list")), before)

    def test_a_failed_run_exits_2(self):
        for args, message in [
                (["eucwatch-no-such-ref", "tests/test_arithmetic.py"], "red-at: eucwatch-no-such-ref is not a commit"),
                (["HEAD", "tests/test_missing.py"], "red-at: tests/test_missing.py does not exist in the working tree"),
                (["HEAD", "laptop/arithmetic.py"],
                 "red-at: laptop/arithmetic.py: not a test check.sh runs (tests/*.py or watch/tests/*.cjs)"),
                (["HEAD", "tests/test_arithmetic.py", "--runs", "0"], "red-at: --runs must be at least 1")]:
            with self.subTest(args=args):
                self.assertEqual(self.main(*args), (2, message))


if __name__ == "__main__":
    unittest.main()
