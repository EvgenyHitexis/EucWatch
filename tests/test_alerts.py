"""Alert acceptance at the application boundary; all output is simulated."""

import json
import tempfile
import unittest
from pathlib import Path

from eucwatch import Application, ManualClock
from eucwatch.persistence import FileStore, MemoryStore
from eucwatch.recording import Replay


class AlertTests(unittest.TestCase):
    def enable(self, app, alert, threshold):
        app.action("alerts_begin")
        app.action("alerts_update", alert=alert, enabled=True, threshold=threshold)
        return app.action("alerts_save")

    def test_defaults_and_invalid_enable_do_not_invent_or_save_thresholds(self):
        app = Application(clock=ManualClock())
        state = app.view()
        self.assertEqual(state["config"]["alerts"]["lost"], {"enabled": True})
        self.assertEqual(
            state["config"]["alerts"]["pwm"], {"enabled": False, "threshold": None}
        )
        app.action("alerts_begin")
        app.action("alerts_update", alert="pwm", enabled=True)
        with self.assertRaises(ValueError):
            app.action("alerts_save")
        self.assertFalse(app.view()["config"]["alerts"]["pwm"]["enabled"])
        self.assertIsNotNone(app.view()["alerts_draft"])

    def test_saving_high_pwm_starts_three_short_pulses_and_repeats_at_two_seconds(self):
        clock = ManualClock()
        app = Application(clock=clock)
        app.action("simulator_configure", pwm_percent=90)
        app.action("simulator_start")
        state = self.enable(app, "pwm", 80)
        self.assertEqual(state["vibration"]["current"]["alert"], "pwm")
        self.assertEqual(state["vibration"]["current"]["duration_s"], 0.15)
        for _ in range(5):
            clock.advance(0.15)
            app.tick()
        events = app.view()["vibration"]["events"]
        self.assertEqual(
            [row["phase"] for row in events],
            ["start", "stop", "start", "stop", "start", "stop"],
        )
        for row, expected in zip(events, (0, 0.15, 0.3, 0.45, 0.6, 0.75), strict=True):
            self.assertAlmostEqual(row["at_s"], expected)
        for _ in range(5):
            clock.advance(0.25)
            app.tick()
        starts = [
            row for row in app.view()["vibration"]["events"] if row["phase"] == "start"
        ]
        self.assertEqual(len(starts), 4)
        self.assertAlmostEqual(starts[-1]["at_s"], 2)

    def test_speed_pattern_repeats_at_five_seconds_and_respects_two_kmh_hysteresis(
        self,
    ):
        clock = ManualClock()
        app = Application(clock=clock)
        app.action("simulator_configure", speed_kmh=50)
        app.action("simulator_start")
        self.enable(app, "speed", 40)
        for _ in range(25):
            clock.advance(0.2)
            app.tick()
        starts = [
            row for row in app.view()["vibration"]["events"] if row["phase"] == "start"
        ]
        self.assertEqual(len(starts), 3)
        for row, expected in zip(starts, (0, 0.3, 5), strict=True):
            self.assertAlmostEqual(row["at_s"], expected)
        app.action("simulator_configure", speed_kmh=39)
        app.action("simulator_emit")
        self.assertEqual(app.view()["vibration"]["current"]["alert"], "speed")
        app.action("simulator_configure", speed_kmh=38)
        self.assertIsNone(app.action("simulator_emit")["vibration"]["current"])
        app.action("simulator_configure", speed_kmh=39)
        self.assertIsNone(app.action("simulator_emit")["vibration"]["current"])
        app.action("simulator_configure", speed_kmh=40)
        self.assertEqual(
            app.action("simulator_emit")["vibration"]["current"]["alert"], "speed"
        )

    def test_low_battery_rearms_only_after_five_continuous_fresh_seconds_three_points_higher(
        self,
    ):
        clock = ManualClock()
        app = Application(clock=clock)
        app.action("simulator_start")  # 135 V -> independently specified 55%.
        state = self.enable(app, "battery", 55)
        self.assertEqual(state["vibration"]["current"]["duration_s"], 0.5)
        app.action("simulator_configure", voltage_V=136)  # 58%, exactly +3.
        app.action("simulator_emit")
        for _ in range(24):
            clock.advance(0.2)
            app.tick()
        app.action("simulator_configure", voltage_V=135)
        app.action("simulator_emit")
        self.assertEqual(
            len(
                [e for e in app.view()["vibration"]["events"] if e["phase"] == "start"]
            ),
            1,
        )
        app.action("simulator_configure", voltage_V=136)
        app.action("simulator_emit")
        for _ in range(25):
            clock.advance(0.2)
            app.tick()
        app.action("simulator_configure", voltage_V=135)
        state = app.action("simulator_emit")
        starts = [e for e in state["vibration"]["events"] if e["phase"] == "start"]
        self.assertEqual(len(starts), 2)
        self.assertEqual(starts[-1]["alert"], "battery")
        self.assertEqual(starts[-1]["duration_s"], 0.5)

    def test_initial_connection_has_no_lost_pulse_and_fresh_data_rearms_each_interruption(
        self,
    ):
        clock = ManualClock()
        app = Application(clock=clock)
        app.action("connect")
        clock.advance(5)
        self.assertEqual(app.view()["vibration"]["events"], [])
        app.action("simulator_emit")
        clock.advance(1)
        state = app.view()
        starts = [e for e in state["vibration"]["events"] if e["phase"] == "start"]
        self.assertEqual(
            [(e["alert"], e["at_s"], e["duration_s"]) for e in starts],
            [("lost", 6, 0.15)],
        )
        clock.advance(5)
        self.assertEqual(
            len(
                [e for e in app.view()["vibration"]["events"] if e["phase"] == "start"]
            ),
            1,
        )
        app.action("simulator_emit")
        state = app.action("disconnect")
        starts = [e for e in state["vibration"]["events"] if e["phase"] == "start"]
        self.assertEqual(len(starts), 2)
        self.assertEqual(starts[-1]["at_s"], 11)

    def test_queued_patterns_use_loss_pwm_speed_battery_priority_without_overlap(self):
        clock = ManualClock()
        app = Application(clock=clock)
        app.action("alert_test", alert="battery")
        app.action("alert_test", alert="speed")
        app.action("alert_test", alert="pwm")
        app.action("alert_test", alert="lost")
        for _ in range(40):
            clock.advance(0.05)
            app.tick()
        events = app.view()["vibration"]["events"]
        starts = [row for row in events if row["phase"] == "start"]
        self.assertEqual(
            [row["alert"] for row in starts],
            ["battery", "lost", "pwm", "pwm", "pwm", "speed", "speed"],
        )
        self.assertTrue(all(row["test"] for row in starts))
        for start, stop in zip(events[::2], events[1::2], strict=True):
            self.assertEqual(start["phase"], "start")
            self.assertEqual(stop["phase"], "stop")
            self.assertAlmostEqual(stop["at_s"] - start["at_s"], start["duration_s"])
        for stop, following in zip(events[1:-1:2], events[2::2], strict=True):
            self.assertLessEqual(stop["at_s"], following["at_s"])

    def test_disconnect_cancels_measurement_pulses_and_starts_one_weak_loss_pulse(self):
        clock = ManualClock()
        app = Application(clock=clock)
        app.action("simulator_configure", pwm_percent=90, speed_kmh=50)
        app.action("simulator_start")
        app.action("alerts_begin")
        app.action("alerts_update", alert="pwm", enabled=True, threshold=80)
        app.action("alerts_update", alert="speed", enabled=True, threshold=40)
        app.action("alerts_save")
        clock.advance(0.1)
        state = app.action("disconnect")
        self.assertEqual(state["vibration"]["current"]["alert"], "lost")
        self.assertEqual(state["vibration"]["queued"], [])
        clock.advance(10)
        starts = [
            row for row in app.view()["vibration"]["events"] if row["phase"] == "start"
        ]
        self.assertEqual(
            [(e["alert"], e["at_s"]) for e in starts], [("pwm", 0), ("lost", 0.1)]
        )

    def test_cancel_and_watch_back_discard_drafts_and_saved_alerts_survive_restart(
        self,
    ):
        store = MemoryStore()
        app = Application(clock=ManualClock(), store=store)
        app.action("alerts_begin")
        app.action("alerts_update", alert="speed", enabled=True, threshold=40)
        app.action("alerts_cancel")
        self.assertFalse(app.view()["config"]["alerts"]["speed"]["enabled"])
        app.action("swipe", direction="down")
        app.action("alerts_begin")
        app.action("alerts_update", alert="pwm", enabled=True, threshold=80)
        state = app.action("swipe", direction="right")
        self.assertIsNone(state["alerts_draft"])
        self.assertFalse(state["config"]["alerts"]["pwm"]["enabled"])
        self.enable(app, "speed", 40)
        restarted = Application(clock=ManualClock(), store=store)
        self.assertEqual(
            restarted.view()["config"]["alerts"]["speed"],
            {"enabled": True, "threshold": 40},
        )
        self.assertEqual(restarted.view()["vibration"]["events"], [])
        self.assertEqual(restarted.view()["mode"], "idle")

    def test_file_restart_and_corrupt_active_copy_recover_last_known_good(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "configuration.json"
            app = Application(clock=ManualClock(), store=FileStore(path))
            self.enable(app, "pwm", 80)
            restarted = Application(clock=ManualClock(), store=FileStore(path))
            self.assertEqual(
                restarted.view()["config"]["alerts"]["pwm"]["threshold"], 80
            )
            self.enable(restarted, "speed", 40)
            path.write_text("incomplete interrupted content")
            recovered = Application(clock=ManualClock(), store=FileStore(path))
            self.assertTrue(recovered.view()["config"]["alerts"]["pwm"]["enabled"])
            self.assertFalse(recovered.view()["config"]["alerts"]["speed"]["enabled"])
            self.assertIn("last-known-good", recovered.view()["persistence_error"])

    def test_persistence_failure_remains_visible_and_keeps_saved_configuration(self):
        class FailingStore(MemoryStore):
            def save(self, config):
                raise OSError("No space left")

        app = Application(clock=ManualClock(), store=FailingStore())
        state = self.enable(app, "pwm", 80)
        self.assertFalse(state["config"]["alerts"]["pwm"]["enabled"])
        self.assertIsNotNone(state["alerts_draft"])
        self.assertIn("No space left", state["persistence_error"])

    def test_resume_cancels_measurement_work_without_replaying_missed_pulses(self):
        clock = ManualClock()
        app = Application(clock=clock)
        app.action("simulator_configure", pwm_percent=90)
        app.action("simulator_start")
        self.enable(app, "pwm", 80)
        clock.advance(60, suspended=True)
        state = app.view()
        self.assertFalse(state["fresh"])
        starts = [e for e in state["vibration"]["events"] if e["phase"] == "start"]
        self.assertEqual([e["alert"] for e in starts], ["pwm", "lost"])
        self.assertEqual(starts[-1]["at_s"], 60)
        self.assertFalse(any(0 < e["at_s"] < 60 for e in starts))

    def test_alert_editing_is_an_ongoing_operation_and_all_thresholds_are_validated(
        self,
    ):
        clock = ManualClock()
        app = Application(clock=clock)
        app.action("swipe", direction="down")
        app.action("alerts_begin")
        clock.advance(60)
        self.assertTrue(app.view()["awake"])
        for alert, value in (
            ("pwm", True),
            ("pwm", 101),
            ("battery", -1),
            ("speed", float("nan")),
            ("speed", 3276.8),
        ):
            app.action("alerts_cancel")
            app.action("alerts_begin")
            app.action("alerts_update", alert=alert, enabled=True, threshold=value)
            with self.assertRaises(ValueError):
                app.action("alerts_save")
            self.assertEqual(app.view()["config"]["revision"], 0)

    def test_pwm_clears_at_three_points_below_and_new_crossing_restarts_promptly(self):
        app = Application(clock=ManualClock())
        app.action("simulator_configure", pwm_percent=90)
        app.action("simulator_start")
        self.enable(app, "pwm", 80)
        app.action("simulator_configure", pwm_percent=78)
        self.assertIsNotNone(app.action("simulator_emit")["vibration"]["current"])
        app.action("simulator_configure", pwm_percent=77)
        self.assertIsNone(app.action("simulator_emit")["vibration"]["current"])
        app.action("simulator_configure", pwm_percent=79)
        self.assertIsNone(app.action("simulator_emit")["vibration"]["current"])
        app.action("simulator_configure", pwm_percent=80)
        self.assertEqual(
            app.action("simulator_emit")["vibration"]["current"]["alert"], "pwm"
        )

    def test_simultaneous_measurements_follow_priority_and_evaluate_every_reading(self):
        clock = ManualClock()
        app = Application(clock=clock)
        app.action("simulator_configure", pwm_percent=90, speed_kmh=50)
        app.action("simulator_start")
        app.action("alerts_begin")
        for alert, threshold in (("pwm", 80), ("speed", 40), ("battery", 60)):
            app.action("alerts_update", alert=alert, enabled=True, threshold=threshold)
        app.action("alerts_save")
        for _ in range(34):
            clock.advance(0.05)
            app.tick()
        starts = [e for e in app.view()["vibration"]["events"] if e["phase"] == "start"]
        self.assertEqual(
            [e["alert"] for e in starts],
            ["pwm", "pwm", "pwm", "speed", "speed", "battery"],
        )
        self.assertTrue(all(not e["test"] for e in starts))

    def test_low_battery_rearm_time_resets_on_stale_gap(self):
        clock = ManualClock()
        app = Application(clock=clock)
        app.action("simulator_start")
        self.enable(app, "battery", 55)
        app.action("simulator_configure", voltage_V=136)
        app.action("simulator_emit")
        for _ in range(20):
            clock.advance(0.2)
            app.tick()
        app.action("simulator_configure", traffic="paused")
        clock.advance(2)
        app.tick()
        app.action("simulator_emit")
        for _ in range(4):
            clock.advance(0.2)
            app.action("simulator_emit")
        app.action("simulator_configure", voltage_V=135)
        state = app.action("simulator_emit")
        starts = [
            e
            for e in state["vibration"]["events"]
            if e["phase"] == "start" and e["alert"] == "battery"
        ]
        self.assertEqual(len(starts), 1)

    def test_recorded_raw_notifications_replay_identical_alert_timing(self):
        clock = ManualClock()
        store = MemoryStore()
        rows = []

        def capture(row):
            rows.append({"schema": 1, "sequence": len(rows), **row})

        source = Application(clock=clock, store=store, event_sink=capture)
        self.enable(source, "pwm", 80)
        source.action("simulator_configure", pwm_percent=90)
        source.action("simulator_start")
        for _ in range(5):
            clock.advance(0.15)
            source.tick()
        source.action("simulator_configure", traffic="paused")
        clock.advance(0.85)
        expected = source.action("interact")["vibration"]["events"]
        recording = Replay.from_text("\n".join(json.dumps(row) for row in rows))
        replay = Application(clock=ManualClock(), store=store)
        replay.action("replay_start", recording=recording)
        for _ in rows:
            replay.action("replay_step")
        actual = replay.view()["vibration"]["events"]
        self.assertEqual(actual, expected)

    def test_new_mode_cancels_old_pattern_before_switching_virtual_clock(self):
        output = []
        clock = ManualClock(10)
        app = Application(clock=clock, vibration_output=output.append)
        app.action("alert_test", alert="pwm")
        state = app.action("simulator_start", controlled=True)
        self.assertEqual(state["vibration"]["events"], [])
        self.assertEqual(
            [(e["phase"], e["at_s"]) for e in output], [("start", 10), ("stop", 10)]
        )


    def test_a_measurement_repeat_at_freshness_expiry_never_starts(self):
        clock = ManualClock()
        app = Application(clock=clock)
        app.action("connect")
        app.action("simulator_configure", pwm_percent=90)
        app.action("simulator_emit")
        self.enable(app, "pwm", 80)
        for _ in range(2):
            clock.advance(0.5)
            app.action("simulator_emit")
        clock.advance(1)
        events = app.view()["vibration"]["events"]
        starts = [e for e in events if e["phase"] == "start"]
        self.assertFalse(any(e["alert"] == "pwm" and e["at_s"] >= 2 for e in starts))
        self.assertEqual(starts[-1]["alert"], "lost")
        self.assertEqual(starts[-1]["at_s"], 2)


if __name__ == "__main__":
    unittest.main()
