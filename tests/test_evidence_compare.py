"""The evidence comparison behind scripts/evidence-compare.py.

The comparison tests build two regenerated evidence directories by hand, one for
the base ref and one for the working tree, and check which differences are
reported. The others pin the exit-2 failures and the lists read from check.sh.
"""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from support import ROOT

spec = importlib.util.spec_from_file_location("evidence_compare", ROOT / "scripts" / "evidence-compare.py")
evidence_compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence_compare)


class EvidenceCompareTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name) / "base"
        self.tree = Path(temporary.name) / "tree"

    def write(self, side, relative, value):
        path = side / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, bytes):
            path.write_bytes(value)
        elif isinstance(value, str):
            path.write_text(value)
        else:
            path.write_text(json.dumps(value, indent=2) + "\n")

    def both(self, relative, value):
        self.write(self.base, relative, value)
        self.write(self.tree, relative, value)

    def differences(self):
        return evidence_compare.differences(self.base, self.tree)

    def test_identical_evidence_has_no_differences(self):
        self.both("touch-layout/editor.json", {"states": [{"screen": "preset_editor"}]})
        self.both("touch-layout/slot-1-name.svg", "<svg>\n<text>Jump</text>\n</svg>\n")
        self.both("touch-layout/invalid-save.png", b"\x89PNG\r\n\x1a\n")
        self.assertEqual(self.differences(), [])

    def test_changed_json_value_names_the_file_and_field(self):
        self.write(self.base, "touch-layout/editor.json", {"states": [{"screen": "preset_editor", "label": "Save"}]})
        self.write(self.tree, "touch-layout/editor.json", {"states": [{"screen": "preset_editor", "label": "Store"}]})
        self.assertEqual(self.differences(),
                         ['touch-layout/editor.json: $.states[0].label: base "Save", working tree "Store"'])

    def test_provenance_hashes_are_ignored_wherever_they_appear(self):
        self.write(self.base, "local-presets/regression-alerts.json",
                   {"fingerprints": {"watch/app.js": "aa"}, "trace": {"trace_sha256": "bb", "source_sha256": {"watch/app.js": "cc"}}})
        self.write(self.tree, "local-presets/regression-alerts.json",
                   {"fingerprints": {"watch/app.js": "dd", "watch/new.js": "ee"}, "trace": {"trace_sha256": "ff"}})
        self.assertEqual(self.differences(), [])

    def test_a_field_present_on_one_side_only_is_a_difference(self):
        self.write(self.base, "touch-layout/editor.json", {"outcome": "passed", "saved": None})
        self.write(self.tree, "touch-layout/editor.json", {"outcome": "passed"})
        self.assertEqual(self.differences(), ['touch-layout/editor.json: $.saved: base null, working tree absent'])

    def test_a_longer_list_reports_each_extra_item(self):
        self.write(self.base, "touch-layout/navigation.json", {"packets": []})
        self.write(self.tree, "touch-layout/navigation.json", {"packets": ["5aa5"]})
        self.assertEqual(self.differences(),
                         ['touch-layout/navigation.json: $.packets[0]: base absent, working tree "5aa5"'])

    def test_a_file_written_on_one_side_only_is_a_difference(self):
        self.write(self.base, "touch-layout/failed-save.svg", "<svg/>\n")
        self.write(self.tree, "touch-layout/new-screen.svg", "<svg/>\n")
        self.assertEqual(self.differences(), ["touch-layout/failed-save.svg: written only at base",
                                              "touch-layout/new-screen.svg: written only in the working tree"])

    def test_changed_svg_names_the_line(self):
        self.write(self.base, "touch-layout/slot-1-name.svg", "<svg>\n<text>Name</text>\n</svg>\n")
        self.write(self.tree, "touch-layout/slot-1-name.svg", "<svg>\n<text>Title</text>\n</svg>\n")
        self.assertEqual(self.differences(), [
            'touch-layout/slot-1-name.svg: line 2: base "<text>Name</text>", working tree "<text>Title</text>"'])

    def bundle(self, version, bytes, sha256, revision):
        name = f"sw-{version}-app"
        return {"manifest": {"version": version, "main": f"sw-{version}-main",
                             "files": [{"name": name, "bytes": bytes, "sha256": sha256, "crc32": sha256[:8]}]},
                "rehearsal": {"version": version, "bytes": bytes + 10,
                              "plan": {"required_bytes": bytes + 20, "available_bytes": 1000000, "writes": [name]}},
                "configurations": [{"saved": {"revision": revision}}],
                "native_imports": [f"sw-{version}-main"],
                "artifact": f".test-output/watch-preset-editor/{version}"}

    def test_bundle_version_names_sizes_and_checksums_are_ignored(self):
        self.write(self.base, "local-presets/bundle.json", self.bundle("72615351", 4696, "37e778e8" * 8, 1))
        self.write(self.tree, "local-presets/bundle.json", self.bundle("fb665b8a", 4710, "9150e3c8" * 8, 1))
        self.assertEqual(self.differences(), [])

    def test_bundle_behavior_still_differs(self):
        self.write(self.base, "local-presets/bundle.json", self.bundle("72615351", 4696, "37e778e8" * 8, 1))
        self.write(self.tree, "local-presets/bundle.json", self.bundle("fb665b8a", 4710, "9150e3c8" * 8, 2))
        self.assertEqual(self.differences(),
                         ["local-presets/bundle.json: $.configurations[0].saved.revision: base 1, working tree 2"])

    def test_changed_png_is_a_difference(self):
        self.write(self.base, "touch-layout/invalid-save.png", b"\x89PNG\r\n\x1a\n\x00")
        self.write(self.tree, "touch-layout/invalid-save.png", b"\x89PNG\r\n\x1a\n\x01")
        self.assertEqual(self.differences(), ["touch-layout/invalid-save.png: bytes differ"])

    def test_evidence_that_is_not_json_fails_the_run(self):
        self.write(self.base, "touch-layout/editor.json", {"outcome": "passed"})
        self.write(self.tree, "touch-layout/editor.json", '{"outcome": ')
        with self.assertRaisesRegex(evidence_compare.Failed,
                                    r"^touch-layout/editor\.json: the working tree copy is not valid JSON \("):
            self.differences()

    def test_bundle_without_a_manifest_version_fails_the_run(self):
        valid = self.bundle("72615351", 4696, "37e778e8" * 8, 1)
        for broken in ({**valid, "manifest": {"files": []}}, {"rehearsal": {}}):
            with self.subTest(broken=broken):
                self.write(self.base, "local-presets/bundle.json", broken)
                self.write(self.tree, "local-presets/bundle.json", valid)
                with self.assertRaisesRegex(evidence_compare.Failed,
                                            r"^local-presets/bundle\.json: the base copy has no manifest\.version$"):
                    self.differences()


class RunFailureTests(unittest.TestCase):
    """Exit 1 means differences only: every way the run itself fails exits 2 with one line."""

    def main(self, *args):
        stderr = io.StringIO()
        with patch.object(sys, "argv", ["evidence-compare.py", *args]), contextlib.redirect_stderr(stderr), \
                contextlib.redirect_stdout(io.StringIO()):
            code = evidence_compare.main()
        return code, stderr.getvalue().strip().splitlines()

    def test_a_missing_command_fails_the_run(self):
        with tempfile.TemporaryDirectory() as copy:
            with self.assertRaisesRegex(evidence_compare.Failed, "cannot run eucwatch-no-such-command"):
                evidence_compare.run(Path(copy), ["eucwatch-no-such-command"])

    def test_missing_dependencies_fail_before_anything_is_exported(self):
        with tempfile.TemporaryDirectory() as root, patch.object(evidence_compare, "ROOT", Path(root)):
            with self.assertRaisesRegex(evidence_compare.Failed, r"^experiments/laptop-feasibility/\.venv is missing"):
                evidence_compare.require_dependencies(browser=False)
            (Path(root) / evidence_compare.VENV).mkdir(parents=True)
            evidence_compare.require_dependencies(browser=False)
            with self.assertRaisesRegex(evidence_compare.Failed, r"^frontend/node_modules is missing"):
                evidence_compare.require_dependencies(browser=True)

    def test_missing_node_exits_2(self):
        with tempfile.TemporaryDirectory() as empty, patch.dict(os.environ, {"PATH": empty}):
            self.assertEqual(self.main("HEAD"), (2, ["evidence-compare: node is not on PATH"]))

    def test_an_unknown_ref_exits_2(self):
        self.assertEqual(self.main("eucwatch-no-such-ref"), (2, ["evidence-compare: eucwatch-no-such-ref is not a commit"]))

    def test_an_unforeseen_error_exits_2_not_1(self):
        with patch.object(evidence_compare, "export_base", side_effect=KeyError("version")):
            self.assertEqual(self.main("HEAD"), (2, ["evidence-compare: the run failed: KeyError: 'version'"]))

    def test_git_failures_raise_unless_allowed(self):
        self.assertEqual(evidence_compare.git("rev-parse", "--verify", "--quiet", "eucwatch-no-such-ref",
                                              allow_failure=True), "")
        with self.assertRaisesRegex(evidence_compare.Failed, "^git rev-parse --verify eucwatch-no-such-ref: "):
            evidence_compare.git("rev-parse", "--verify", "eucwatch-no-such-ref")


class CheckScriptTests(unittest.TestCase):
    """evidence-compare reads its suite and flow lists out of scripts/check.sh and the check-watch.sh it calls."""

    def test_listed_names_exactly_what_check_sh_runs(self):
        # Run the real check.sh with node, npm and uv replaced by loggers, and
        # compare what it ran with what listed() parses out of it.
        with tempfile.TemporaryDirectory() as temporary:
            bin_directory, log = Path(temporary) / "bin", Path(temporary) / "commands.log"
            bin_directory.mkdir()
            for command in ("node", "npm", "uv"):
                fake = bin_directory / command
                fake.write_text(f'#!/bin/sh\necho "{command} $*" >> "$CHECK_SH_LOG"\n')
                fake.chmod(0o755)
            env = {**os.environ, "PATH": f"{bin_directory}:/usr/bin:/bin", "CHECK_SH_LOG": str(log),
                   "EUCWATCH_BROWSER_CHECKS": "1"}
            subprocess.run(["bash", str(ROOT / "scripts/check.sh")], env=env, check=True, timeout=60)
            commands = [line.split() for line in log.read_text().splitlines()]
        suites = [words[1].removeprefix("watch/tests/").removesuffix(".cjs")
                  for words in commands if words[0] == "node"]
        flows = [words[-1].removeprefix("tests/").removesuffix(".py") for words in commands
                 if words[0] == "uv" and words[-1].startswith("tests/") and words[-1] != "tests/launch_smoke.py"]
        self.assertGreater(len(suites), 1)
        self.assertEqual(evidence_compare.listed(ROOT, "suite"), suites)
        self.assertGreater(len(flows), 1)
        self.assertEqual(evidence_compare.listed(ROOT, "flow"), flows)

    def test_a_base_without_check_watch_sh_lists_the_suites_in_check_sh(self):
        # Before #70 the watch suite loop was in check.sh itself, and a base ref may predate check-watch.sh.
        with tempfile.TemporaryDirectory() as copy:
            (Path(copy) / "scripts").mkdir()
            (Path(copy) / "scripts/check.sh").write_text(
                'for suite in offline runtime; do\n  node "watch/tests/$suite.cjs"\ndone\n')
            self.assertEqual(evidence_compare.listed(Path(copy), "suite"), ["offline", "runtime"])
            with self.assertRaisesRegex(evidence_compare.Failed, r"no `for flow in \.\.\.` loop"):
                evidence_compare.listed(Path(copy), "flow")


if __name__ == "__main__":
    unittest.main()
