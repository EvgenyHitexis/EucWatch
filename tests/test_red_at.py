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
        self.write(".gitignore", "**/.venv\n")
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
        lines = (stdout.getvalue() + stderr.getvalue()).strip().splitlines()
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
