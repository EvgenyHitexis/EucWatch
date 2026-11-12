"""The evidence comparison behind scripts/evidence-compare.py.

Each test builds two regenerated evidence directories by hand, one for the base
ref and one for the working tree, and checks which differences are reported.
"""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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


if __name__ == "__main__":
    unittest.main()
