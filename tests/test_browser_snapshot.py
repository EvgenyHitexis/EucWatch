"""Page.snapshot waits until the watch shows the expected frame (#72).

A fake DevTools browser stands in for Chrome: it answers each page evaluation
with the next frame the watch Canvas would report.
"""
import asyncio
import base64
import tempfile
import time
import unittest
from pathlib import Path

from support import Page

PNG = b'\x89PNG\r\n\x1a\nframe'


def frame(screen, label):
    """What the Canvas reports: its screen id, its accessible label, and its pixels."""
    return {'screen': screen, 'label': label, 'png': base64.b64encode(PNG).decode()}


class FakeBrowser:
    """Answers each Runtime.evaluate with the next frame, then keeps the last."""

    def __init__(self, *frames):
        self.frames, self.evaluations = list(frames), 0

    async def call(self, method, params=None, session=None):
        assert method == 'Runtime.evaluate', method
        self.evaluations += 1
        shown = self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]
        return {'result': {'value': shown}}


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'navigation-dashboard.png'

    def snapshot(self, browser, **options):
        return asyncio.run(Page(browser, 'session', 'target').snapshot(self.path, **options))

    def test_a_snapshot_must_say_what_the_watch_shows(self):
        page = Page(FakeBrowser(frame('dashboard', 'Speed 0 km/h')), 'session', 'target')
        with self.assertRaises(TypeError):
            page.snapshot(self.path)

    def test_it_waits_for_the_screen_then_writes_that_frame(self):
        browser = FakeBrowser(frame('settings', 'Settings.'), frame('settings', 'Settings.'),
                              frame('dashboard', 'Speed 0 km/h'))
        label = self.snapshot(browser, shows='dashboard')
        self.assertEqual(self.path.read_bytes(), PNG)
        self.assertEqual(label, 'Speed 0 km/h')
        self.assertEqual(browser.evaluations, 3)

    def test_label_text_is_matched_anywhere_in_the_accessible_label(self):
        browser = FakeBrowser(frame('preset_editor', 'Preset editor slot 1. Name: Ab 1. Input A.'),
                              frame('preset_editor', 'Preset editor slot 1. Name: Ab 1. Input Ab 1.'))
        self.snapshot(browser, shows='Input Ab 1')
        self.assertEqual(browser.evaluations, 2)

    def test_a_frame_that_never_appears_fails_naming_what_was_expected_and_the_path(self):
        browser = FakeBrowser(frame('settings', 'Settings.'))
        started = time.monotonic()
        with self.assertRaises(TimeoutError) as raised:
            self.snapshot(browser, shows='dashboard', timeout=.3)
        self.assertLess(time.monotonic() - started, 2)
        message = str(raised.exception)
        self.assertIn("'dashboard'", message)
        self.assertIn(str(self.path), message)
        self.assertIn('Settings.', message)
        self.assertFalse(self.path.exists())


if __name__ == '__main__':
    unittest.main()
