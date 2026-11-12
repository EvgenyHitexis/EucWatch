"""The browser flows write tracked acceptance evidence only on request (#65)."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from support import ROOT, evidence_directory


class BrowserEvidenceTests(unittest.TestCase):
    def test_flows_write_into_scratch_output_without_the_flag(self):
        for value in (None, '', '0', 'true'):
            environment = {} if value is None else {'EUCWATCH_WRITE_EVIDENCE': value}
            with self.subTest(flag=value), patch.dict(os.environ, environment, clear=True):
                self.assertEqual(evidence_directory('touch-layout'),
                                 Path('.test-output/evidence/touch-layout'))

    def test_flows_write_tracked_evidence_with_the_flag(self):
        with patch.dict(os.environ, {'EUCWATCH_WRITE_EVIDENCE': '1'}):
            self.assertEqual(evidence_directory('local-presets'),
                             Path('docs/acceptance/evidence/local-presets'))

    def test_no_flow_names_the_tracked_evidence_directory_itself(self):
        flows = [*sorted((ROOT / 'tests').glob('browser_*.py')), ROOT / 'tests/launch_smoke.py']
        self.assertGreater(len(flows), 1)
        for flow in flows:
            with self.subTest(flow=flow.name):
                self.assertNotIn('acceptance/evidence', flow.read_text())


if __name__ == '__main__':
    unittest.main()
