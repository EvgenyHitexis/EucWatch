"""The ES5 parse check over the watch modules a bundle ships (Espruino 2v14)."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from eucwatch.installation import build_bundle
from support import ROOT

WATCH = ROOT / "watch"
CHECK = ROOT / "scripts" / "check-es5.py"


def run_check(source=None, env=None):
    command = [sys.executable, str(CHECK)] + ([] if source is None else ["--source", str(source)])
    return subprocess.run(command, capture_output=True, text=True, timeout=60, env=env)


class Es5CheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        # check-es5.py prints resolved paths, so compare against the resolved copy
        # (a symlinked TMPDIR would otherwise differ).
        self.copy = Path(temporary.name).resolve() / "watch"
        shutil.copytree(WATCH, self.copy, ignore=shutil.ignore_patterns("tests", "evidence"))

    def inject(self, module, line):
        """Put `line` at line 5 of the scratch module, as a developer edit would."""
        path = self.copy / module
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        lines.insert(4, line + "\n")
        path.write_text("".join(lines), encoding="utf-8")

    def test_current_watch_modules_parse_as_es5(self):
        result = run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_newer_constructs_fail_with_file_and_line(self):
        for construct in ("let speed = 1;", "var double = (x) => x * 2;", "var label = `speed`;"):
            with self.subTest(construct=construct):
                shutil.copy2(WATCH / "main.js", self.copy / "main.js")
                self.inject("main.js", construct)
                result = run_check(self.copy)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(f"{self.copy / 'main.js'}:5:", result.stderr)

    def test_every_shipped_module_is_checked(self):
        shipped = [name.split("-", 2)[2] for name, _content in build_bundle(self.copy, "es5").files
                   if not name.endswith("-notice")]
        self.assertIn("boot", shipped)
        for stem in shipped:
            with self.subTest(module=stem):
                module = self.copy / f"{stem}.js"
                original = module.read_bytes()
                try:
                    self.inject(f"{stem}.js", "const limit = 1;")
                    result = run_check(self.copy)
                finally:
                    module.write_bytes(original)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(f"{module}:5:", result.stderr)

    def test_node_test_files_are_out_of_scope(self):
        (self.copy / "tests").mkdir()
        (self.copy / "tests" / "suite.cjs").write_text("const assert = require('assert');\n")
        (self.copy / "tests" / "helper.js").write_text("let node = () => `ok`;\n")
        result = run_check(self.copy)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_node_is_a_setup_failure(self):
        empty = self.copy.parent / "empty-path"
        empty.mkdir()
        result = run_check(env={**os.environ, "PATH": str(empty)})
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stderr.strip().splitlines(),
                         ["ES5 check: node is not on PATH; install Node.js, then run ./scripts/setup.sh"])


if __name__ == "__main__":
    unittest.main()
