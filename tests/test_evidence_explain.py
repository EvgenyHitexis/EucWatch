"""The evidence explainer behind scripts/evidence-explain.py (#72).

Each test hands explain() the tracked evidence at a base ref and in the working
tree as path-to-bytes maps, and checks one group of the report.
"""
import json
import unittest

from support import load_script, sha256

evidence_explain = load_script("evidence-explain")


def encoded(value):
    return (json.dumps(value, indent=2) + "\n").encode()


def explain(base, tree, tracked=None):
    tracked = tracked or {}
    lines = evidence_explain.explain(base, tree, lambda content: sorted(
        path for path, value in tracked.items() if value == content))
    return "\n".join(lines)


class JsonDifferenceTests(unittest.TestCase):
    def test_a_change_repeated_across_list_items_prints_once_with_a_count(self):
        base = {"calls": [{"kind": "rect", "y1": 43}, {"kind": "text", "y1": 43}, {"kind": "rect", "y1": 124}],
                "outcome": "passed"}
        tree = {"calls": [{"kind": "rect", "y1": 36}, {"kind": "text", "y1": 36}, {"kind": "rect", "y1": 134}],
                "outcome": "passed"}
        report = explain({"watch/evidence/local-presets/defaults.json": encoded(base)},
                         {"watch/evidence/local-presets/defaults.json": encoded(tree)})
        self.assertIn("JSON differences\n  watch/evidence/local-presets/defaults.json\n"
                      "    $.calls[*].y1: 3 changes\n"
                      "      2× base 43, working tree 36\n"
                      "      1× base 124, working tree 134\n", report)

    def test_a_single_change_prints_on_one_line_and_provenance_is_left_out(self):
        base = {"label": "Save", "source_sha256": {"watch/app.js": "aa"}}
        tree = {"label": "Store", "source_sha256": {"watch/app.js": "bb"}}
        report = explain({"docs/acceptance/evidence/touch-layout/editor-laptop.json": encoded(base)},
                         {"docs/acceptance/evidence/touch-layout/editor-laptop.json": encoded(tree)})
        self.assertIn('    $.label: base "Save", working tree "Store"\n', report)
        self.assertNotIn("source_sha256", report.split("Provenance")[0])

    def test_many_distinct_changes_at_one_path_show_a_few_and_count_the_rest(self):
        base = {"rows": [{"x": index} for index in range(20)]}
        tree = {"rows": [{"x": index + .5} for index in range(20)]}
        report = explain({"watch/evidence/a.json": encoded(base)}, {"watch/evidence/a.json": encoded(tree)})
        self.assertIn("    $.rows[*].x: 20 changes\n", report)
        self.assertIn("      … and 17 more distinct changes\n", report)
        self.assertLess(len(report.splitlines()), 12)


class ProvenanceOnlyTests(unittest.TestCase):
    def test_files_whose_only_change_is_provenance_are_listed_by_name(self):
        base = {"outcome": "passed", "source_sha256": {"watch/app.js": "aa"}, "fingerprints": {"x": "1"}}
        tree = {"outcome": "passed", "source_sha256": {"watch/app.js": "bb"}, "fingerprints": {"x": "2"}}
        report = explain({"watch/evidence/local-presets/regression-alerts.json": encoded(base)},
                         {"watch/evidence/local-presets/regression-alerts.json": encoded(tree)})
        self.assertNotIn("JSON differences", report)
        self.assertIn("Provenance only", report)
        self.assertIn("  watch/evidence/local-presets/regression-alerts.json\n", report)

    def test_the_heading_names_the_fields_evidence_compare_ignores(self):
        report = explain({"watch/evidence/a.json": encoded({"trace_sha256": "a"})},
                         {"watch/evidence/a.json": encoded({"trace_sha256": "b"})})
        heading = next(line for line in report.splitlines() if line.startswith("Provenance only"))
        for field in ("fingerprints", "source_sha256", "trace_sha256", "bundle.json"):
            self.assertIn(field, heading)

    def test_a_bundle_whose_only_change_is_its_version_is_provenance_only(self):
        def bundle(version, crc):
            return {"manifest": {"version": version, "files": [{"name": f"sw-{version}-app", "crc32": crc}]}}
        report = explain({"watch/evidence/local-presets/bundle.json": encoded(bundle("68a2317f", 1))},
                         {"watch/evidence/local-presets/bundle.json": encoded(bundle("abdf3edb", 2))})
        self.assertIn("Provenance only", report)
        self.assertNotIn("JSON differences", report)


class PngTests(unittest.TestCase):
    def test_a_changed_png_shows_both_hashes_and_the_tracked_files_identical_to_the_new_one(self):
        path = "docs/acceptance/evidence/touch-layout/invalid-name-save.png"
        old, new = b"\x89PNG old frame", b"\x89PNG new frame"
        tracked = {path: new, "docs/acceptance/evidence/touch-layout/invalid-name.png": new,
                   "docs/acceptance/evidence/touch-layout/other.png": old}
        report = explain({path: old}, {path: new}, tracked)
        self.assertIn(f"PNG files\n  {path}\n"
                      f"    base         {sha256(old)}\n"
                      f"    working tree {sha256(new)}\n"
                      "    identical to docs/acceptance/evidence/touch-layout/invalid-name.png\n", report)

    def test_a_png_identical_to_no_other_file_says_so(self):
        path = "docs/acceptance/evidence/touch-layout/invalid-save.png"
        report = explain({path: b"old"}, {path: b"new"}, {path: b"new"})
        self.assertIn("    identical to no other tracked file\n", report)


class OtherChangeTests(unittest.TestCase):
    def test_unchanged_evidence_prints_nothing_but_the_summary(self):
        same = {"watch/evidence/a.json": encoded({"outcome": "passed"})}
        self.assertEqual(explain(same, dict(same)), "no tracked evidence differs")

    def test_added_removed_and_other_files_are_accounted_for(self):
        report = explain({"watch/evidence/gone.json": b"{}", "watch/evidence/frame.svg": b"<svg>\n<text>A</text>\n</svg>\n"},
                         {"watch/evidence/new.png": b"png", "watch/evidence/frame.svg": b"<svg>\n<text>B</text>\n</svg>\n"})
        self.assertIn("  watch/evidence/gone.json: only at base\n", report)
        self.assertIn("  watch/evidence/new.png\n    base         absent\n", report)
        self.assertIn("  watch/evidence/frame.svg: 1 changed line(s)\n", report)
        self.assertTrue(report.endswith("3 evidence file(s) differ"))


if __name__ == "__main__":
    unittest.main()
