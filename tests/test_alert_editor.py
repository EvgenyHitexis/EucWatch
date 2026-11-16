"""The alert editor through public actions and views; no browser is involved."""
import unittest
from pathlib import Path

from eucwatch import Application, ManualClock
from eucwatch.lease import ControllerLease
from eucwatch.recording import Replay
from eucwatch.scenarios import ScenarioLibrary

FIXTURE = Path("experiments/laptop-feasibility/evidence/fixture-recording.jsonl")
EDITING = (("alerts_page", {"page": 1}), ("alerts_adjust", {"alert": "speed", "delta": 1}),
           ("threshold_begin", {"alert": "speed"}), ("threshold_key", {"key": "5"}),
           ("threshold_done", {}), ("threshold_begin", {"alert": "speed"}),
           ("threshold_cancel", {}))


def settings(app=None):
    app = app or Application(clock=ManualClock())
    app.action("swipe", direction="down")
    return app


class AlertEditorTests(unittest.TestCase):
    def test_pages_cycle_through_the_four_alerts(self):
        app = settings()
        editor = app.action("alerts_begin")["alert_editor"]
        self.assertEqual(
            (editor["page"], editor["alert"], editor["label"], editor["unit"]),
            (0, "pwm", "High PWM", "%"),
        )
        self.assertEqual((editor["previous_page"], editor["next_page"]), (3, 1))
        self.assertEqual(editor["toggle_label"], "Disabled")
        self.assertEqual(editor["threshold_label"], "Not set")
        seen = []
        for page in (1, 2, 3, 0):
            editor = app.action("alerts_page", page=page)["alert_editor"]
            seen.append((editor["page"], editor["alert"], editor["label"], editor["unit"]))
        self.assertEqual(seen, [
            (1, "speed", "High speed", "km/h"),
            (2, "battery", "Low wheel battery", "%"),
            (3, "lost", "Lost telemetry", ""),
            (0, "pwm", "High PWM", "%"),
        ])
        lost = app.action("alerts_page", page=3)["alert_editor"]
        self.assertEqual((lost["previous_page"], lost["next_page"]), (2, 0))
        self.assertIsNone(lost["threshold_label"])
        self.assertEqual(lost["note"], "1 short pulse")
        for page in (-1, 4, 1.0, True, None):
            with self.subTest(page=page), self.assertRaisesRegex(ValueError, "alert page"):
                app.action("alerts_page", page=page)
        self.assertEqual(app.view()["alert_editor"]["page"], 3)

    def test_keypad_entry_sets_the_draft_threshold_only_on_set_value(self):
        app = settings()
        saved = app.action("alerts_begin")["config"]
        entry = app.action("threshold_begin", alert="pwm")["alert_editor"]["entry"]
        self.assertEqual(entry, {"alert": "pwm", "label": "High PWM", "unit": "%",
                                 "text": "", "display": "— %"})
        for key in ("7", "0"):
            state = app.action("threshold_key", key=key)
        self.assertEqual(state["alert_editor"]["entry"]["display"], "70 %")
        self.assertEqual(state["alerts_draft"]["pwm"]["threshold"], None)
        state = app.action("threshold_done")
        self.assertIsNone(state["alert_editor"]["entry"])
        self.assertEqual(state["alerts_draft"]["pwm"], {"enabled": False, "threshold": 70})
        self.assertEqual(state["alert_editor"]["threshold_label"], "70 %")
        self.assertEqual(state["config"], saved)
        entry = app.action("threshold_begin", alert="pwm")["alert_editor"]["entry"]
        self.assertEqual(entry["text"], "70")
        self.assertEqual(
            [key["label"] for key in app.view()["alert_editor"]["keys"]],
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "0", "<"],
        )

    def test_keypad_accepts_eight_characters_and_one_decimal_point(self):
        app = settings()
        app.action("alerts_begin")
        app.action("alerts_page", page=1)
        app.action("threshold_begin", alert="speed")
        for key in "12.3.45678.9":
            state = app.action("threshold_key", key=key)
        self.assertEqual(state["alert_editor"]["entry"]["text"], "12.34567")
        app.action("threshold_key", key="backspace")
        state = app.action("threshold_key", key="backspace")
        self.assertEqual(state["alert_editor"]["entry"]["display"], "12.345 km/h")
        for key in ("Clear", "<", "-", "e", 1, None, "00"):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "threshold key"):
                app.action("threshold_key", key=key)
        self.assertEqual(app.view()["alert_editor"]["entry"]["text"], "12.345")
        state = app.action("threshold_done")
        self.assertEqual(state["alerts_draft"]["speed"]["threshold"], 12.345)
        self.assertEqual(state["alert_editor"]["threshold_label"], "12.345 km/h")
        app.action("threshold_begin", alert="speed")
        for _ in range(6):
            app.action("threshold_key", key="backspace")
        state = app.action("threshold_key", key="backspace")
        self.assertEqual(state["alert_editor"]["entry"]["display"], "— km/h")

    def test_set_value_reads_the_entry_as_a_number_or_no_threshold(self):
        app = settings()
        app.action("alerts_begin")
        for keys, threshold, label in (
            ("", None, "Not set"), (".", None, "Not set"), ("007", 7, "7 %"),
            ("5.", 5, "5 %"), (".5", 0.5, "0.5 %"), ("0.00005", 0.00005, "0.00005 %"),
            ("707", 707, "707 %"),
        ):
            with self.subTest(keys=keys):
                app.action("threshold_begin", alert="pwm")
                for _ in range(8):
                    app.action("threshold_key", key="backspace")
                for key in keys:
                    app.action("threshold_key", key=key)
                state = app.action("threshold_done")
                self.assertEqual(state["alerts_draft"]["pwm"]["threshold"], threshold)
                self.assertIs(type(state["alerts_draft"]["pwm"]["threshold"]), type(threshold))
                self.assertEqual(state["alert_editor"]["threshold_label"], label)
        app.action("alerts_update", alert="pwm", threshold=1e-07)
        entry = app.action("threshold_begin", alert="pwm")["alert_editor"]["entry"]
        self.assertEqual(entry["text"], "1e-7")

    def test_keypad_cancel_and_swipe_up_discard_only_the_entry(self):
        app = settings()
        app.action("alerts_begin")
        app.action("alerts_update", alert="pwm", threshold=70)
        app.action("alerts_page", page=2)
        for leave in (("threshold_cancel", {}), ("swipe", {"direction": "up"})):
            with self.subTest(leave=leave[0]):
                app.action("threshold_begin", alert="pwm")
                app.action("threshold_key", key="7")
                state = app.action(leave[0], **leave[1])
                self.assertEqual(state["screen"], "settings")
                self.assertIsNone(state["alert_editor"]["entry"])
                self.assertEqual(state["alert_editor"]["page"], 2)
                self.assertEqual(state["alerts_draft"]["pwm"]["threshold"], 70)
        with self.assertRaisesRegex(ValueError, "No threshold input"):
            app.action("threshold_cancel")
        with self.assertRaisesRegex(ValueError, "No threshold input"):
            app.action("threshold_done")
        for alert in ("lost", "rain", None):
            with self.subTest(alert=alert), self.assertRaisesRegex(ValueError, "measurement alert"):
                app.action("threshold_begin", alert=alert)

    def test_plus_and_minus_step_by_one_within_the_saved_limits(self):
        app = settings()
        app.action("alerts_begin")
        state = app.action("alerts_adjust", alert="pwm", delta=1)
        self.assertEqual(state["alerts_draft"]["pwm"]["threshold"], 0)  # Not set starts at 0.
        self.assertEqual(state["alert_editor"]["threshold_label"], "0 %")
        app.action("alerts_adjust", alert="pwm", delta=-1)
        self.assertEqual(app.view()["alerts_draft"]["pwm"]["threshold"], 0)
        for alert, start, delta, expected in (
            ("pwm", 99.5, 1, 100), ("battery", 100, 1, 100), ("battery", 0.5, -1, 0),
            ("speed", 3276, 1, 3276.7), ("speed", 3276.7, 1, 3276.7), ("speed", 70.5, 1, 71.5),
            ("pwm", 707, -1, 100), ("pwm", 70, -1, 69),
        ):
            with self.subTest(alert=alert, start=start, delta=delta):
                app.action("alerts_update", alert=alert, threshold=start)
                state = app.action("alerts_adjust", alert=alert, delta=delta)
                self.assertEqual(state["alerts_draft"][alert]["threshold"], expected)
        saved = app.action("alerts_save")["config"]["alerts"]
        self.assertEqual([saved[name]["threshold"] for name in ("pwm", "speed", "battery")],
                         [69, 71.5, 0])
        app.action("alerts_begin")
        for payload in ({"alert": "lost", "delta": 1}, {"alert": "pwm", "delta": 2},
                        {"alert": "pwm", "delta": True}, {"alert": "pwm"}):
            with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, "adjustment"):
                app.action("alerts_adjust", **payload)
        for threshold in (float("nan"), float("inf"), "70", True):
            with self.subTest(threshold=threshold), self.assertRaisesRegex(ValueError, "adjustment"):
                app.action("alerts_update", alert="pwm", threshold=threshold)
                app.action("alerts_adjust", alert="pwm", delta=1)

    def test_failed_save_explains_itself_until_the_draft_changes(self):
        app = settings()
        saved = app.action("alerts_begin")["config"]
        app.action("alerts_update", alert="pwm", enabled=True)

        def fail():
            with self.assertRaisesRegex(ValueError, "threshold is required to enable pwm"):
                app.action("alerts_save")
            state = app.view()
            self.assertEqual(state["config"], saved)
            self.assertEqual(state["alert_editor"]["reason"], "A threshold is required to enable pwm")
            return state

        fail()
        # Opening, typing in and cancelling the keypad leave the explanation shown.
        app.action("threshold_begin", alert="pwm")
        app.action("threshold_key", key="7")
        app.action("threshold_cancel")
        app.action("alert_test", alert="pwm")
        self.assertIn("threshold is required", app.view()["alert_editor"]["reason"])
        for change, payload in (("alerts_page", {"page": 1}), ("alerts_update", {"alert": "lost", "enabled": False}),
                                ("alerts_adjust", {"alert": "speed", "delta": 1})):
            with self.subTest(change=change):
                fail()
                self.assertEqual(app.action(change, **payload)["alert_editor"]["reason"], "")
        fail()
        app.action("threshold_begin", alert="pwm")
        app.action("threshold_key", key="7")
        app.action("threshold_key", key="0")
        state = app.action("threshold_done")
        self.assertEqual(state["alert_editor"]["reason"], "")
        state = app.action("alerts_save")
        self.assertIsNone(state["alert_editor"])
        self.assertEqual(state["config"]["revision"], saved["revision"] + 1)
        self.assertEqual(state["config"]["alerts"]["pwm"], {"enabled": True, "threshold": 70})
        self.assertEqual(state["config"]["alerts"]["speed"], {"enabled": False, "threshold": 0})
        self.assertEqual(state["screen"], "settings")
        self.assertEqual(state["command_events"], [])

    def test_out_of_range_entry_is_refused_at_save(self):
        app = settings()
        app.action("alerts_begin")
        app.action("alerts_page", page=2)
        app.action("threshold_begin", alert="battery")
        for key in "101":
            app.action("threshold_key", key=key)
        state = app.action("threshold_done")
        self.assertEqual(state["alert_editor"]["threshold_label"], "101 %")
        with self.assertRaisesRegex(ValueError, "Invalid battery threshold"):
            app.action("alerts_save")
        self.assertEqual(app.view()["alert_editor"]["reason"], "Invalid battery threshold (0–100%)")
        self.assertEqual(app.view()["config"]["revision"], 0)

    def test_cancel_discards_the_draft_and_keeps_the_saved_alerts(self):
        app = settings()
        saved = app.action("alerts_begin")["config"]
        app.action("alerts_update", alert="pwm", enabled=True, threshold=70)
        app.action("alerts_page", page=2)
        state = app.action("alerts_cancel")
        self.assertIsNone(state["alert_editor"])
        self.assertIsNone(state["alerts_draft"])
        self.assertEqual(state["config"], saved)
        self.assertEqual(state["screen"], "settings")

    def test_page_and_entry_are_discarded_with_the_draft(self):
        discards = {
            "Cancel": (("alerts_cancel", {}),),
            "swipe up": (("swipe", {"direction": "up"}), ("swipe", {"direction": "up"})),
            "Presets": (("preset_slots", {}), ("swipe", {"direction": "up"})),
            "Save": (("threshold_done", {}), ("alerts_save", {})),
        }
        for label, actions in discards.items():
            with self.subTest(discard=label):
                app = settings()
                app.action("alerts_begin")
                app.action("alerts_page", page=1)
                app.action("threshold_begin", alert="speed")
                app.action("threshold_key", key="4")
                for action, payload in actions:
                    state = app.action(action, **payload)
                self.assertEqual(state["screen"], "settings")
                self.assertIsNone(state["alert_editor"])
                self.assertIsNone(state["alerts_draft"])
                editor = app.action("alerts_begin")["alert_editor"]
                self.assertEqual((editor["page"], editor["entry"], editor["reason"]), (0, None, ""))
        app = settings()
        app.action("alerts_begin")
        app.action("alerts_page", page=2)
        app.action("threshold_begin", alert="battery")
        editor = app.action("alerts_begin")["alert_editor"]  # Reopening starts afresh.
        self.assertEqual((editor["page"], editor["entry"]), (0, None))

    def test_an_open_editor_keeps_the_screen_awake(self):
        clock = ManualClock()
        app = settings(Application(clock=clock))
        app.action("alerts_begin")
        for action, payload in EDITING:
            clock.advance(40)
            self.assertTrue(app.action(action, **payload)["awake"])
        clock.advance(40)
        self.assertTrue(app.view()["awake"])
        app.action("alerts_cancel")
        clock.advance(30)
        self.assertFalse(app.view()["awake"])

    def test_editor_actions_follow_alerts_update_when_asleep_or_in_recovery(self):
        # Application accepts alert draft edits in any screen state; the Canvas
        # refuses touches while asleep or in recovery.
        for state in ("asleep", "recovery"):
            with self.subTest(state=state):
                clock = ManualClock()
                app = settings(Application(clock=clock))
                app.action("alerts_begin")
                if state == "asleep":
                    app.action("sleep")
                else:
                    app.action("button_down")
                    clock.advance(30)
                view = app.view()
                self.assertEqual((view["awake"], view["recovery"]), (state == "recovery", state == "recovery"))
                app.action("alerts_update", alert="lost", enabled=False)
                for action, payload in EDITING:
                    app.action(action, **payload)
                state_view = app.action("alerts_save")
                self.assertEqual(state_view["config"]["alerts"]["speed"]["threshold"], 5)
                self.assertFalse(state_view["config"]["alerts"]["lost"]["enabled"])

    def test_read_only_replay_allows_local_alert_editing_without_wheel_commands(self):
        app = Application(clock=ManualClock())
        app.action("replay_start", recording=Replay.load(FIXTURE))
        app.action("swipe", direction="down")
        app.action("alerts_begin")
        for action, payload in EDITING:
            app.action(action, **payload)
        state = app.action("alerts_save")
        self.assertEqual(state["mode"], "replay")
        self.assertEqual(state["config"]["alerts"]["speed"], {"enabled": False, "threshold": 5})
        self.assertEqual(state["command_events"], [])

    def test_any_draft_threshold_is_shown_as_the_browser_spelled_it(self):
        app = settings()
        app.action("alerts_begin")
        app.action("alerts_page", page=1)
        for threshold, label in ((float("nan"), "NaN km/h"), (float("inf"), "Infinity km/h"),
                                 (1e21, "1e+21 km/h"), (123456789012.5, "123456789012.5 km/h"),
                                 (-3, "-3 km/h")):
            with self.subTest(threshold=threshold):
                app.action("alerts_update", alert="speed", threshold=threshold)
                self.assertEqual(app.view()["alert_editor"]["threshold_label"], label)
        app.action("alerts_update", alert="speed", threshold=float("nan"))
        entry = app.action("threshold_begin", alert="speed")["alert_editor"]["entry"]
        self.assertEqual(entry["text"], "NaN")
        app.action("threshold_cancel")
        with self.assertRaisesRegex(ValueError, "Invalid speed threshold"):
            app.action("alerts_save")
        self.assertEqual(app.view()["alert_editor"]["reason"], "Invalid speed threshold (0–3276.7 km/h)")

    def test_no_editor_view_without_an_alert_draft(self):
        app = settings()
        self.assertIsNone(app.view()["alert_editor"])
        with self.assertRaises(ValueError):
            app.action("alerts_page", page=1)



class NoLive:
    async def disconnect(self):
        pass

    def status(self):
        return None


class AlertEditorControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_the_controlling_browser_edits_alerts(self):
        app = settings()
        lease = ControllerLease(app, NoLive(), ScenarioLibrary(), ManualClock(), timeout=10.0)
        owner = lease.acquire(None)
        self.assertIsNone(lease.acquire(None))  # A second browser only views.

        def request(controller, identity, action, **payload):
            return {"controller": controller, "id": identity, "action": action,
                    "epoch": app.session, **payload}

        await lease.act(request(owner, "open", "alerts_begin"))
        for index, (action, payload) in enumerate(EDITING):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "Valid controller"):
                await lease.act(request("viewer", f"viewer-{index}", action, **payload))
            state = await lease.act(request(owner, f"owner-{index}", action, **payload))
        self.assertEqual(state["alerts_draft"]["speed"]["threshold"], 5)


if __name__ == "__main__":
    unittest.main()
