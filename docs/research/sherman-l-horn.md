# Sherman L alarm-speaker horn feasibility

Investigated 2026-10-06 for [Establish Sherman L alarm-speaker horn control](https://github.com/EvgenyHitexis/EucWatch/issues/7). This is protocol research for planning; no wheel connection, command transmission, firmware modification, or watch investigation was performed.

## Finding

A concrete **wheel-beep command candidate exists**, including exact bytes and a BLE write path. That makes a physical-button horn a reasonable feature to plan conditionally. It does **not** yet establish a reliable horn on the owner's Sherman L firmware, instantaneous response, a sustained tone while held, or priority relative to the wheel's warnings. Keep the user requirement; make verified horn support a capability rather than inferring it from successful telemetry.

WheelLog implements `wheelBeep` for modern Veteran-family wheels; its family identification includes Sherman L as 6. FreeWheel implements an old/new command pair and supplies app-derived fixtures. These sources establish what applications send, not what this particular wheel audibly does. [WheelLog adapter][wl-adapter], [FreeWheel command implementation][fw-decoder], [app-derived fixtures][fixtures].

## Evidence and provenance

| Source | What it establishes | Boundary |
| --- | --- | --- |
| WheelLog `f44e39e5388e500a5d2f315d1dcf32f167607bf8` | Beep payload; family selection; BLE transport | No Sherman L horn audio/latency fixture found |
| FreeWheel `7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca` | Two binary variants; fixtures attributed to Leaperkim Android app v1.4.8 | The author reverse-engineered the app; this is not a manufacturer protocol specification |
| FreeWheel variant-policy test | Checks payload and CRC against fixtures at synthetic family 5 | Lynx-family encoding test, not Sherman L hardware behavior |
| Manufacturer Sherman L manual, FCC exhibit 7527579 | Wheel settings and control terminology | Inspected controls do not specify remote horn operation or alarm arbitration |
| LoEUC developer's live dashboard documentation | Explicitly describes its own Leaperkim horn workaround as unverified on hardware | Different implementation claim; no published bytes on that page |

Primary code was read from pinned GitHub contents APIs. The [FreeWheel audit][audit] documents its reverse-engineering provenance and known discrepancies, including legacy text-command differences. The manufacturer-authored manual was inspected as rendered pages from its [FCC-submission mirror][manual]; the document's hosting mirror is not its author. [Variant tests][tests].

## Candidate protocol contract

Use the existing direct BLE connection: service `0000ffe0-0000-1000-8000-00805f9b34fb`, characteristic `0000ffe1-0000-1000-8000-00805f9b34fb`. WheelLog routes Veteran writes through `WriteType.WITHOUT_RESPONSE`. Its command-routing result indicates transport submission, not audible horn confirmation. The characteristic and connection properties still need checking on the owner's firmware. [UUID constants][constants], [BLE write implementation][wl-ble], [command routing][wl-data].

Two candidate packets, each 14 bytes:

```text
LkAp: 4c 6b 41 70 0e 00 80 80 80 01 ca 87 e6 6f
LdAp: 4c 64 41 70 0e 00 00 80 80 01 f8 67 9f 85
```

The first ten bytes are the payload; the last four are standard CRC32 of that payload, big-endian. Offset 4 is command `0x0e`; offset 5 is zero; offset 9 is one. In the new form, offset 6 is zero instead of `0x80`. No duration or release parameter is defined by these implementations. [Encoders][fw-decoder], [payload fixtures][fixtures].

WheelLog sends **only LkAp** when its model-family integer is at least 3; Sherman L selects this branch. FreeWheel sends **LkAp then LdAp** for the same family range. This is an application-policy difference, not proof that sending both is necessary or that it makes exactly one sound. Each packet fits a 20-byte ATT payload. Do not combine 28 bytes into an unexamined single write at default MTU. [WheelLog][wl-adapter], [FreeWheel][fw-decoder].

The author's app audit says the manufacturer app combines both CRC-bearing variants except for Patton's `004` prefix. Its protocol note describes sequential write chunks capped at 20 bytes. This would include Sherman L's `006` prefix, but was not independently verified against an APK or a live capture here. Old-model ASCII `b` behavior is not the Sherman L contract; the audit even records a discrepancy between that spelling and the manufacturer's legacy command. [App audit][audit], [protocol note][reference].

## What “horn” means here

The researched feature sends a short control message to the **wheel**. It is not phone audio playback, Bluetooth music streaming, or a watch confirmation sound. A local vibration could acknowledge button handling later, but must not claim that the wheel sounded. This distinction follows from the BLE command path, not an audio capture. [Routing][wl-data], [transport][wl-ble].

Alarm threshold configuration is a different operation. FreeWheel separates `Beep` from `SetAlarmSpeed`; the manual's page 18 identifies an overspeed alarm setting. Changing alarm thresholds, PWM limits, key-tone volume or other settings is not an established way to implement this horn. Page 11 is headed “Button Volume Settable” but its explanatory text discusses battery pages; that apparent copy error prevents deriving reliable volume semantics from it. [Decoder][fw-decoder], [manufacturer manual, pages 11 and 18][manual].

A useful conflicting source is the [LoEUC author's horn documentation][loeuc]. It says its Leaperkim/NOSFET action relies on a command-acceptance beep from a command that otherwise changes nothing, and explicitly says the beep has not been checked on a real wheel. This is not proof that the packets above fail, nor proof of a dedicated firmware horn handler. It reinforces the need to separate application naming from observed wheel behavior. The live page was checked with an HTTP fetch because search and opened-page snapshots differed.

## Unresolved behavior that affects the specification

These are evidence gaps, not declarations that the feature is impossible:

- **Sound:** No inspected Sherman L recording proves which transducer sounds, tone, loudness, duration, or volume-setting dependence.
- **Press/release:** The command builders provide a beep trigger; they do not establish start/stop commands, a duration field, or a hold-to-sound contract. Do not invent a stop command by changing the value to zero.
- **Repeat:** No established minimum interval, rate limit, duplicate suppression, or behavior of the old/new pair was found. A repeat loop is not justified by the encoding test.
- **Confirmation:** No horn-specific ACK, sequence number, or “currently sounding” readback was found in the inspected decoder. A successful unacknowledged write and continued telemetry cannot prove audible success.
- **Responsiveness:** No measured button-to-sound latency or reconnect-to-ready bound was found. Maintaining an already connected link is an architectural inference for prompt response; it is not a latency guarantee.
- **Warnings:** No source inspected specifies whether a requested beep interrupts, queues behind, mixes with, or is suppressed by onboard alarms. Alarm preservation remains a requirement to verify, not a behavior to assert.

These boundaries come from inspecting the command builders, tests and documented telemetry/settings contract; none of those substitutes for a measurement on the owner's wheel. [Builders][fw-decoder], [tests][tests], [telemetry research](sherman-l-protocol.md).

## Planning handoff

Proposed requirements for the later interaction decision, not settled UX:

1. Give horn access an immediately reachable physical-button action, subject to the eventual watch's actual button API.
2. Treat one press as a request for one verified beep behavior. Decide hold/repetition only after duration and repeat behavior are known.
3. Reject unavailable actions immediately; discard expired requests on disconnect and never replay an old horn press after reconnection.
4. Keep horn events separate from saved riding presets and give them a bounded command-queue delay. Define the actual latency target with the rider, then measure it.
5. Never change warning thresholds or volumes as a side effect of pressing horn. Verify coexistence with ordinary warning behavior before calling it supported.

A concrete later validation task can record model and firmware, capture a known-working application's horn writes, compare packets, then observe single requests with the wheel stationary. Record sound onset/duration, whether both variants are needed, repeated requests, volume dependence, state/readback changes, and disconnect handling. Alarm arbitration needs manufacturer/firmware evidence or a suitable controlled test; it does not require inducing a hazardous riding condition. No wheel-write experiment is authorized or performed by this report.

## Independent packet check

Executed with Python's standard library, without network or wheel access:

```python
import zlib
payloads = [bytes.fromhex("4c6b41700e0080808001"),
            bytes.fromhex("4c6441700e0000808001")]
for payload in payloads:
    packet = payload + zlib.crc32(payload).to_bytes(4, "big")
    print(packet.hex(" "))
```

The outputs match both packets above; the first also matches WheelLog's embedded constant. This verifies arithmetic and transcription only. No upstream application test suite was executed.

[wl-adapter]: https://github.com/Wheellog/Wheellog.Android/blob/f44e39e5388e500a5d2f315d1dcf32f167607bf8/app/src/main/java/com/cooper/wheellog/utils/VeteranAdapter.java
[wl-ble]: https://github.com/Wheellog/Wheellog.Android/blob/f44e39e5388e500a5d2f315d1dcf32f167607bf8/app/src/main/java/com/cooper/wheellog/BluetoothService.kt#L480-L505
[wl-data]: https://github.com/Wheellog/Wheellog.Android/blob/f44e39e5388e500a5d2f315d1dcf32f167607bf8/app/src/main/java/com/cooper/wheellog/WheelData.java#L140-L145
[constants]: https://github.com/Wheellog/Wheellog.Android/blob/f44e39e5388e500a5d2f315d1dcf32f167607bf8/app/src/main/java/com/cooper/wheellog/utils/Constants.kt
[fw-decoder]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonMain/kotlin/org/freewheel/core/protocol/VeteranDecoder.kt
[fixtures]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonTest/kotlin/org/freewheel/core/protocol/LeaperkimAppCommands.kt
[tests]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonTest/kotlin/org/freewheel/core/protocol/VeteranCommandVariantPolicyTest.kt
[audit]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/docs/official-app-audits/veteran-leaperkim-nosfet.md
[reference]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/docs/leaperkim-protocol-reference.md
[manual]: https://fccid.io/2BDSK-SHERMAN-L/User-Manual/User-Manual-7527579.pdf
[loeuc]: https://loeuc.ru/en/docs/dashboard#horn
