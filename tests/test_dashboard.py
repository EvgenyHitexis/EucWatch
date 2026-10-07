"""Dashboard acceptance at the public application boundary (synthetic input)."""

import unittest
import zlib

from eucwatch import Application, ManualClock

# WheelLog Sherman L 006.0.03 source fixture. See
# docs/research/sherman-l-protocol.md for pinned provenance and independent values.
SOURCE_FRAME = bytes.fromhex(
    "dc5a5c53397afffe0aa400000df10000000a0b3d"
    "0e0e0000037a035217730064000e00b480c80000"
    "808080808080058080808080800ff30ff50ff50f"
    "f50ff50fef0ff20ff30ff30ff30ff30fed0ff30f"
    "f40ff5378c5145"
)


class DashboardTests(unittest.TestCase):
    def test_reconnect_preserves_controlled_clock_selection(self):
        host = ManualClock()
        app = Application(clock=host)
        app.action('simulator_start', controlled=True)
        app.action('simulator_configure', traffic='paused')
        app.action('disconnect')
        app.action('connect')
        app.action('simulator_emit')
        host.advance(5)
        self.assertTrue(app.view()['fresh'])
        self.assertTrue(app.view()['controlled'])

    def test_launch_is_idle_and_watch_battery_is_explicitly_simulated(self):
        app = Application(clock=ManualClock())
        state = app.view()
        self.assertEqual(state["mode"], "idle")
        self.assertFalse(state["connected"])
        self.assertEqual(state["dashboard"]["speed"], "—")
        self.assertTrue(state["dashboard"]["watch_battery_simulated"])
        self.assertEqual(state["dashboard"]["watch_battery_percent"], "80")

    def test_source_notifications_produce_original_dashboard_values(self):
        app = Application(clock=ManualClock())
        state = app.action("connect")
        for pos in range(0, len(SOURCE_FRAME), 20):
            app.receive(state["session"], SOURCE_FRAME[pos : pos + 20])
        state = app.view()
        self.assertTrue(state["fresh"])
        self.assertEqual(state["dashboard"]["speed"], "0")
        self.assertEqual(state["dashboard"]["pwm"], "2")
        self.assertEqual(state["dashboard"]["wheel_battery_percent"], "97")
        self.assertEqual(state["dashboard"]["average_cell_voltage"], "4.09")
        self.assertEqual(state["telemetry"]["speed_kmh"], -0.2)
        self.assertEqual(state["telemetry"]["firmware"], "006.0.03")

    def test_one_second_expiry_disconnect_and_fresh_recovery(self):
        clock = ManualClock()
        app = Application(clock=clock)
        session = app.action("connect")["session"]
        app.receive(session, SOURCE_FRAME)
        clock.advance(0.999)
        self.assertTrue(app.view()["fresh"])
        clock.advance(0.001)
        state = app.view()
        self.assertFalse(state["fresh"])
        self.assertEqual(state["dashboard"]["speed"], "—")
        self.assertEqual(state["dashboard"]["pwm"], "—")
        self.assertEqual(state["dashboard"]["connection"], "Telemetry lost")
        self.assertTrue(state["dashboard"]["wheel_battery_dimmed"])
        self.assertEqual(state["dashboard"]["wheel_battery_percent"], "97")
        app.receive(session, SOURCE_FRAME)
        self.assertTrue(app.view()["fresh"])
        app.action("disconnect")
        self.assertFalse(app.view()["fresh"])
        app.receive(session, SOURCE_FRAME)
        self.assertFalse(app.view()["fresh"])
        self.assertEqual(app.view()["dashboard"]["watch_battery_percent"], "80")

    def test_simulator_uses_fragmented_real_protocol_and_controlled_time(self):
        clock = ManualClock()
        app = Application(clock=clock)
        app.action(
            "simulator_configure",
            speed_kmh=12.5,
            pwm_percent=44.5,
            voltage_V=135,
            fragment_size=1,
            frame_length=75,
            watch_battery_percent=72,
        )
        state = app.action("simulator_start")
        self.assertEqual(state["dashboard"]["speed"], "13")
        self.assertEqual(state["dashboard"]["pwm"], "45")
        self.assertEqual(state["dashboard"]["wheel_battery_percent"], "55")
        self.assertEqual(state["dashboard"]["average_cell_voltage"], "3.75")
        self.assertEqual(state["dashboard"]["watch_battery_percent"], "72")
        self.assertEqual(state["diagnostics"]["valid_frames"], 1)
        app.action("simulator_configure", traffic="paused")
        state = app.action("advance", seconds=1)
        self.assertFalse(state["fresh"])
        state = app.action("simulator_emit")
        self.assertTrue(state["fresh"])

    def test_all_supported_lengths_and_fragment_boundaries_decode_at_application(self):
        for length in (75, 77, 87, 99):
            prefix = bytearray(SOURCE_FRAME[:-4])
            prefix = prefix[: length - 4]
            prefix.extend(bytes(length - 4 - len(prefix)))
            prefix[3] = length - 4
            frame = bytes(prefix) + zlib.crc32(prefix).to_bytes(4, "big")
            for split in range(1, length):
                with self.subTest(length=length, split=split):
                    app = Application(clock=ManualClock())
                    session = app.action("connect")["session"]
                    app.receive(session, frame[:split])
                    self.assertFalse(app.view()["fresh"])
                    app.receive(session, frame[split:])
                    self.assertTrue(app.view()["fresh"])
            app = Application(clock=ManualClock())
            session = app.action("connect")["session"]
            app.receive(session, frame * 3)
            self.assertEqual(app.view()["diagnostics"]["valid_frames"], 3)

    def test_battery_boundaries_and_whole_number_display(self):
        app = Application(clock=ManualClock())
        app.action("simulator_start")
        for voltage, percent, cell in (
            (110, "0", "3.06"),
            (119.02, "0", "3.31"),
            (119.16, "0", "3.31"),
            (119.17, "1", "3.31"),
            (135, "55", "3.75"),
            (148.04, "100", "4.11"),
            (148.05, "100", "4.11"),
            (160, "100", "4.44"),
        ):
            with self.subTest(voltage=voltage):
                app.action("simulator_configure", voltage_V=voltage)
                state = app.action("simulator_emit")
                self.assertEqual(state["dashboard"]["wheel_battery_percent"], percent)
                self.assertEqual(state["dashboard"]["average_cell_voltage"], cell)

    def test_all_single_bit_corruptions_recover_without_refreshing_values(self):
        for pos in range(len(SOURCE_FRAME)):
            for bit in range(8):
                with self.subTest(byte=pos, bit=bit):
                    clock = ManualClock()
                    app = Application(clock=clock)
                    session = app.action("connect")["session"]
                    app.receive(session, SOURCE_FRAME)
                    clock.advance(1)
                    corrupt = bytearray(SOURCE_FRAME)
                    corrupt[pos] ^= 1 << bit
                    app.receive(session, bytes(corrupt))
                    self.assertFalse(app.view()["fresh"])
                    app.receive(session, SOURCE_FRAME)
                    self.assertTrue(app.view()["fresh"])
                    self.assertEqual(app.view()["diagnostics"]["valid_frames"], 2)

    def test_unknown_identity_lengths_and_large_noise_are_not_telemetry(self):
        app = Application(clock=ManualClock())
        session = app.action("connect")["session"]
        other_family = bytearray(SOURCE_FRAME[:-4])
        other_family[28:30] = (5010).to_bytes(2, "big")
        frame = bytes(other_family) + zlib.crc32(other_family).to_bytes(4, "big")
        app.receive(session, frame)
        app.receive(session, b"\xdc\x5a\x5c\xff" + b"x" * 10000)
        self.assertFalse(app.view()["fresh"])
        self.assertEqual(app.view()["diagnostics"]["valid_frames"], 0)
        app.receive(session, SOURCE_FRAME)
        self.assertTrue(app.view()["fresh"])

    def test_resume_and_session_change_reject_old_notifications(self):
        clock = ManualClock()
        app = Application(clock=clock)
        old_session = app.action("connect")["session"]
        app.receive(old_session, SOURCE_FRAME)
        clock.advance(60, suspended=True)
        state = app.view()
        self.assertFalse(state["fresh"])
        self.assertEqual(state["diagnostics"]["resume_events"], 1)
        app.receive(old_session, SOURCE_FRAME)
        self.assertFalse(app.view()["fresh"])
        app.receive(state["session"], SOURCE_FRAME)
        self.assertTrue(app.view()["fresh"])
        current = app.action("connect")["session"]
        app.receive(state["session"], SOURCE_FRAME)
        self.assertFalse(app.view()["fresh"])
        app.receive(current, SOURCE_FRAME)
        self.assertTrue(app.view()["fresh"])

    def test_invalid_simulator_edits_leave_previous_settings_unchanged(self):
        app = Application(clock=ManualClock())
        previous = app.view()["simulator"]
        for payload in (
            {"speed_kmh": True},
            {"voltage_V": float("nan")},
            {"frame_length": 76},
            {"fragment_size": 0},
            {"watch_battery_percent": 101},
            {"traffic": "unknown"},
        ):
            with self.assertRaises(ValueError):
                app.action("simulator_configure", **payload)
            self.assertEqual(app.view()["simulator"], previous)

    def test_controlled_simulator_ignores_host_time_and_advances_only_explicitly(self):
        host_clock = ManualClock()
        app = Application(clock=host_clock)
        app.action("simulator_start", controlled=True)
        app.action("simulator_configure", traffic="paused")
        host_clock.advance(60)
        self.assertTrue(app.view()["fresh"])
        self.assertEqual(app.view()["elapsed_s"], 0)
        state = app.action("advance", seconds=1)
        self.assertFalse(state["fresh"])
        app.action("simulator_start", controlled=False)
        app.action("simulator_configure", traffic="paused")
        host_clock.advance(1)
        self.assertFalse(app.view()["fresh"])


if __name__ == "__main__":
    unittest.main()
