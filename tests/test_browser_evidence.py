"""The browser flows write tracked acceptance evidence only on request (#65),
and what they write does not depend on where the checkout is (#68)."""
import asyncio
import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from support import ROOT, evidence_directory, record_flow


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


async def empty_exercise(page, app, output):
    return {}


@contextlib.asynccontextmanager
async def no_browser(app):
    yield None


class RecordFlowSourceTests(unittest.TestCase):
    """record_flow names every source by its path from the repository root."""

    def recorded_sources(self, working_directory):
        with tempfile.TemporaryDirectory() as directory, \
                patch('support.watch_page', no_browser), \
                patch('support.evidence_directory', lambda name: Path(directory)), \
                contextlib.chdir(working_directory), \
                contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(record_flow(empty_exercise, 'flow', 'touch-layout'))
            return json.loads((Path(directory) / 'flow.json').read_text())['source_sha256']

    def test_every_source_key_is_repository_relative(self):
        sources = self.recorded_sources(ROOT)
        self.assertIn('tests/support.py', sources)
        self.assertIn('tests/test_browser_evidence.py', sources)
        self.assertIn('laptop/eucwatch/application.py', sources)
        self.assertIn('frontend/src/main.ts', sources)
        for key in sources:
            with self.subTest(key=key):
                self.assertFalse(Path(key).is_absolute())
                self.assertTrue((ROOT / key).is_file())

    def test_sources_are_in_one_order_whatever_the_working_directory(self):
        sources = self.recorded_sources(ROOT)
        self.assertEqual(list(sources), sorted(sources))
        with tempfile.TemporaryDirectory() as elsewhere:
            self.assertEqual(self.recorded_sources(elsewhere), sources)


class WatchParityTraceTests(unittest.TestCase):
    """The watch parity suites replay the laptop traces where the flows wrote them."""

    def laptop_trace(self, environment):
        script = "process.stdout.write(require('./watch/tests/harness.cjs').laptopTrace('touch-layout/navigation-laptop.json'))"
        variables = {key: value for key, value in os.environ.items() if not key.startswith('EUCWATCH_')}
        return subprocess.run(['node', '-e', script], cwd=ROOT, env={**variables, **environment},
                              capture_output=True, text=True, check=True, timeout=30).stdout

    def test_after_the_browser_flows_the_suites_replay_what_they_wrote(self):
        for write in (None, '1'):
            environment = {'EUCWATCH_BROWSER_CHECKS': '1', **({} if write is None else {'EUCWATCH_WRITE_EVIDENCE': write})}
            with self.subTest(write=write):
                replayed = self.laptop_trace(environment)
                with patch.dict(os.environ, environment, clear=True):
                    written = evidence_directory('touch-layout') / 'navigation-laptop.json'
                self.assertEqual(replayed, str(written))

    def test_without_the_browser_flows_the_suites_replay_the_committed_traces(self):
        for environment in ({}, {'EUCWATCH_WRITE_EVIDENCE': '1'}, {'EUCWATCH_BROWSER_CHECKS': '0'}):
            with self.subTest(environment=json.dumps(environment)):
                self.assertEqual(self.laptop_trace(environment),
                                 'docs/acceptance/evidence/touch-layout/navigation-laptop.json')

    def test_no_watch_suite_names_the_tracked_trace_directory_itself(self):
        suites = sorted((ROOT / 'watch/tests').glob('*.cjs'))
        self.assertGreater(len(suites), 1)
        for suite in suites:
            if suite.name != 'harness.cjs':
                with self.subTest(suite=suite.name):
                    self.assertNotIn('acceptance/evidence', suite.read_text())


if __name__ == '__main__':
    unittest.main()
