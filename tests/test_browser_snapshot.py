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

    def test_label_text_does_not_match_the_start_of_a_longer_word(self):
        # The Preset editor types "Ab 3y" and deletes the y: that frame does not show 'Input Ab 3'.
        browser = FakeBrowser(frame('preset_editor', 'Name: Road. name keypad. Input Ab 3y. OK or Cancel'),
                              frame('preset_editor', 'Name: Road. name keypad. Input Ab 3. OK or Cancel'))
        self.assertIn('Input Ab 3.', self.snapshot(browser, shows='Input Ab 3'))
        self.assertEqual(browser.evaluations, 2)

    def test_label_text_does_not_match_the_end_of_a_longer_word(self):
        browser = FakeBrowser(frame('preset_editor', 'Input 26.'), frame('preset_editor', 'Input 6.'))
        self.assertEqual(self.snapshot(browser, shows='6.'), 'Input 6.')

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


class LabelWaitTests(unittest.TestCase):
    """Page.label waits for label text the same way snapshot matches it."""

    def wait(self, text, *labels):
        browser = FakeBrowser(*labels)
        asyncio.run(Page(browser, 'session', 'target').label(text))
        return browser.evaluations

    def test_it_waits_past_a_frame_whose_word_only_starts_with_the_text(self):
        self.assertEqual(self.wait('Input Ab 3', 'Input Ab 3y. OK', 'Input Ab 3. OK'), 2)

    def test_a_label_that_never_shows_the_text_fails_naming_it_and_what_was_shown(self):
        page = Page(FakeBrowser('Settings.'), 'session', 'target')
        with self.assertRaises(TimeoutError) as raised:
            asyncio.run(page.label('Settings Presets.', timeout=.2))
        self.assertIn("'Settings Presets.'", str(raised.exception))
        self.assertIn("'Settings.'", str(raised.exception))

    def test_text_followed_by_punctuation_or_the_end_of_the_label_matches(self):
        self.assertEqual(self.wait('Settings', 'Settings Presets.'), 1)
        self.assertEqual(self.wait('Controlled disk full', 'Error: Controlled disk full'), 1)


if __name__ == '__main__':
    unittest.main()
