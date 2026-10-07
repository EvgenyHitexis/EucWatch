"""Watch interactions verified through application actions and elapsed time."""

import unittest

from eucwatch import Application, ManualClock


class NavigationTests(unittest.TestCase):
    def test_watch_gestures_open_menus_and_back_returns_without_side_effects(self):
        app = Application(clock=ManualClock())
        self.assertEqual(app.view()["screen"], "dashboard")
        self.assertEqual(app.action("swipe", direction="left")["screen"], "presets")
        self.assertEqual(app.action("swipe", direction="right")["screen"], "dashboard")
        self.assertEqual(
            app.action("swipe", direction="down", from_top=False)["screen"], "dashboard"
        )
        self.assertEqual(
            app.action("swipe", direction="down", from_top=True)["screen"], "settings"
        )
        state = app.action("swipe", direction="right")
        self.assertEqual(state["screen"], "dashboard")
        self.assertEqual(state["mode"], "idle")
        self.assertFalse(state["connected"])

    def test_explicit_sleep_requires_a_wake_only_whole_button_cycle(self):
        clock = ManualClock()
        app = Application(clock=clock)
        app.action("swipe", direction="down")
        self.assertFalse(app.action("sleep")["awake"])
        app.action("swipe", direction="left")
        self.assertFalse(app.view()["awake"])
        state = app.action("button_down")
        self.assertTrue(state["awake"])
        self.assertTrue(state["button"]["wake_cycle"])
        self.assertEqual(state["feedback"], "Wake only")
        clock.advance(1)
        self.assertEqual(app.action("button_hold")["feedback"], "Wake only")
        self.assertEqual(app.action("button_down")["feedback"], "Wake only")
        state = app.action("button_up")
        self.assertFalse(state["button"]["down"])
        self.assertFalse(state["button"]["wake_cycle"])
        self.assertEqual(state["feedback"], "Wake only")
        self.assertEqual(
            app.action("button_down")["feedback"], "Horn unavailable: connection unavailable"
        )

    def test_initial_idle_sleeps_at_thirty_seconds_and_watch_taps_reset_idle(self):
        clock = ManualClock()
        app = Application(clock=clock)
        clock.advance(29)
        self.assertTrue(app.view()["awake"])
        app.action("interact")
        clock.advance(29.999)
        self.assertTrue(app.view()["awake"])
        clock.advance(0.001)
        self.assertFalse(app.view()["awake"])

    def test_established_connection_keeps_warning_awake_through_disconnect(self):
        clock = ManualClock()
        app = Application(clock=clock)
        app.action("connect")
        state = app.action("disconnect")
        self.assertTrue(state["established_connection"])
        clock.advance(120)
        self.assertTrue(app.view()["awake"])
        app.action("swipe", direction="down")
        self.assertFalse(app.action("sleep")["awake"])

    def test_a_held_button_is_an_operation_and_prolonged_hold_enters_recovery(self):
        clock = ManualClock()
        app = Application(clock=clock)
        clock.advance(29)
        app.action("button_down")
        clock.advance(29.999)
        self.assertTrue(app.view()["awake"])
        self.assertFalse(app.view()["recovery"])
        clock.advance(0.001)
        state = app.action("button_hold")
        self.assertTrue(state["recovery"])
        self.assertTrue(state["awake"])
        self.assertEqual(state["feedback"], "Recovery mode")
        app.action("button_up")
        self.assertEqual(
            app.action("button_down")["feedback"], "Horn unavailable: recovery mode"
        )

    def test_resume_discards_retained_button_hold_without_entering_recovery(self):
        clock = ManualClock()
        app = Application(clock=clock)
        app.action("button_down")
        clock.advance(60, suspended=True)
        state = app.view()
        self.assertFalse(state["recovery"])
        self.assertFalse(state["button"]["down"])
        self.assertFalse(app.action("button_up")["recovery"])


if __name__ == "__main__":
    unittest.main()
