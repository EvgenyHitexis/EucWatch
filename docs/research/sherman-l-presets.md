# Sherman L riding-preset protocol evidence

Investigated 2026-10-06 for [Establish the Sherman L riding-preset control protocol](https://github.com/EvgenyHitexis/EucWatch/issues/6). Scope: protocol facts and remaining decisions for configurable presets while the watch is unavailable. No wheel writes, watch investigation, or application implementation occurred.

## Finding

Percentage-based presets are a plausible planning direction, but the evidence does **not** yet establish a complete Sherman L write contract for all three requested controls. The owner explicitly identifies Acceleration Assist, pedal hardness, and optional Pedal Dip as percentage controls in EUC World. Preserve those three concepts; do not replace them with three discrete riding modes or with a pedal angle in degrees.

There is a concrete candidate command and readback for acceleration assistance. Manufacturer documentation confirms adjustable riding-mode hardness from 0 to 100%, with lower values softer. However, app reverse-engineering distinguishes continuous ride-mode hardness from a separate control also called pedal hardness/softness/sensitivity. Pedal Dip's exact correspondence remains unresolved. Fast switching while riding is a requirement to investigate, not a verified firmware capability. [Manufacturer manual, page 10][manual], [reference commands][commands], [app audit, F6][audit].

## Evidence and provenance

Sources are pinned to FreeWheel `7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca` and WheelLog `f44e39e5388e500a5d2f315d1dcf32f167607bf8` to match [the earlier telemetry investigation](sherman-l-protocol.md). The Sherman L manufacturer manual is the FCC-filed PDF mirrored by FCCID.io; its image-based page 10 was downloaded, rendered, and visually inspected. It establishes wheel-side UI behavior, not BLE bytes. [Manual][manual].

FreeWheel is primary evidence for what **FreeWheel implements**. Its audit and command fixtures attribute byte mappings to reverse-engineering Leaperkim Android app v1.4.8; this investigation did not independently obtain or decompile that APK. Treat those attributions as app-derived evidence, not manufacturer-published protocol guarantees. The audit expressly marks continuous ride mode as needing a hardware capture. [Audit][audit], [app-derived command fixtures][appcommands].

The earlier WheelLog Sherman L fixture identifies firmware `006.0.03`, but its settings page is subtype 5, not subtype 8. It proves neither successful preset writes nor assistance settings readback. FreeWheel's separate settings fixture is generated for a **Lynx** with `buildExtendedFrame`, while its Sherman L baseline is also synthesized; these are not physical Sherman L setting-change recordings. [WheelLog fixture][fixture], [FreeWheel generated fixtures][synthetic].

EUC World’s own release announcement for version 2.48.0 (28 August 2024) explicitly equates community acceleration assist with its Dynamic assist setting and describes developing support using a supplied Sherman L. This is direct developer testimony linking the UI concept to that model, stronger than generic Veteran-family support. It does not publish command bytes, a minimum firmware revision, or Pedal Dip’s mapping. Correlating its terminology with FreeWheel suggests the `0x1F` candidate; that byte-level link remains an inference. [EUC World announcement][eucworld].

## Keep the controls distinct

All offsets below are zero-based within a command or a fully assembled notification frame. These are candidate mappings pending the owner's app-label/firmware correlation.

| Requested concept / related field | Range evidence | Candidate write | Candidate observation | Evidence boundary |
| --- | --- | --- | --- | --- |
| Acceleration Assist | FreeWheel exposes Dynamic Assist 0–100% | `LdAp`, command `0x1F`, byte 5=`01`, byte 6=`02`, value at 26, raw percentage | Subtype 8, unsigned byte 66 | App-derived name is acceleration/deceleration helper; strongest candidate for requested assist, not a measured Sherman L effect curve |
| Riding-mode pedal hardness | Manufacturer: 0–100%, lower softer | App audit: command `0x0C`, value at 7 is percentage + 10; `LkAp` and `LdAp` forms | Main-frame byte 31 interpreted by official-app audit as percentage + 100 | Explicit Sherman L model association, but upstream marks continuous encoding NEEDS-CAPTURE |
| Separate pedal hardness/softness/sensitivity | FreeWheel exposes Pedal Hardness 0–100% | `LdAp`, `0x0F`, byte 5=`01`, byte 6=`02`, raw value at 10 | Subtype 8, unsigned byte 50 | A different field from `0x0C`; do not silently choose between them based on English label |
| Optional Pedal Dip | Owner says percentage; protocol range not independently established | **Unresolved** | **Unresolved** | Do not assign it to `0x0F` or `0x21` without evidence |
| Acceleration reduction/limit, related but unrequested | FreeWheel exposes 0–100% | `LdAp`, `0x21`, byte 5=`01`, byte 6=`02`, raw value at 28 | Subtype 8, unsigned byte 68 | Separate candidate field; its name does not establish equivalence to Pedal Dip |

Sources: [manufacturer hardness][manual], [continuous-mode audit F6][audit], [commands `0x0F`, `0x1F`, `0x21`][commands], [subtype readback][readback], [FreeWheel percentage controls][settings], [wire-value tests][wiretests]. The newer fields' raw percentage behavior is executable code plus tests; no exact physical response, granularity accepted by firmware, or minimum Sherman L revision is established.

Static pedal tilt is explicitly separate: the reference sends signed tenths of a degree through command `0x10`, within −8° to +8°. Its main-frame pitch measurement is an instantaneous angle, not proof of the configured Pedal Dip percentage. The owner's percentage clarification rules out treating this angle command as the requested third preset value. [Tilt command and correction, F2][audit], [tilt vectors][appcommands], [settings units][settings].

The existing WheelLog adapter only sends `SETh`, `SETm`, or `SETs` for pedal-mode changes and does not decode subtype-8 controls. FreeWheel likewise maps byte 31 only for discrete values 1/2/3, returning unknown for continuous values. Neither implementation can simply be copied as a complete Sherman L percentage-hardness feature. [WheelLog adapter][wheellog], [FreeWheel mode parser][modeparse].

## Command envelope and transport

The telemetry investigation identifies service `0000ffe0-0000-1000-8000-00805f9b34fb` and characteristic `0000ffe1-0000-1000-8000-00805f9b34fb`. The app-derived reference uses this characteristic for commands as well as telemetry. It reports sequential writes in chunks no larger than 20 bytes. Commands exceed 20 bytes even though the setting value is only one byte. [Existing transport evidence](sherman-l-protocol.md#direct-connection), [app-derived transport notes][reference].

For the implemented new-style percentage controls, the pre-checksum command is:

```text
4C 64 41 70  <command>  01 02  <80 padding to value position>  <value>
```

Append four bytes of standard CRC32 over the complete pre-checksum command, most significant byte first. Payload length is value-position + 1; there is no extra length byte. Thus `0x0F` totals 15 bytes, `0x1F` totals 31, and `0x21` totals 33. The `02` byte is significant even for percentage sliders; the constructor's generic comment about using zero for other settings must not override its actual call sites. [Builders and CRC][builders], [percentage calls][commands].

Continuous ride-mode `0x0C` is different: the app-derived format uses byte 5=`01`, and either legacy header `4C 6B 41 70` with byte 6=`80` or new header `4C 64 41 70` with byte 6=`00`. Both place the candidate percentage + 10 at byte 7 and append a separate CRC. The official-app audit reports the paired format for non-Patton models; this is a compatibility strategy, not atomic setting commit. The later implementation's missing continuous-mode support remains material. [Audit F6/F10][audit], [command forms][appcommands].

FreeWheel's default non-KingSong transport selects BLE write **without response**, no automatic retries, and no enforced inter-write spacing. Its Android implementation reports a successful submission, explicitly not peer application. That is a reference choice, not proof that every Sherman L GATT revision has identical properties; inspect the actual characteristic before choosing a runtime API. Even a GATT write response would not prove that firmware applied the requested setting. [Transport profile][transport], [Android write implementation][blewrite].

## Readback, confirmation, and partial presets

Subtype 8 is identified by byte 46 of a validated telemetry frame. FreeWheel decodes percentage candidates from bytes 50, 66, and 68, treating `0x80` as unsupported. The new app should require the field to precede the CRC, then validate its range. FreeWheel's current helper bounds against total frame size and merges missing/unsupported fields with retained values; its audit flags the CRC-boundary defect. Do not let an old retained value prove a current write succeeded. [Readback][readback], [retained settings merge][merge], [audit F8][audit].

No reviewed source provides a preset transaction ID, all-fields commit, rollback, or command-specific acceptance/rejection for these percentage writes. The observed contract is individual setting writes plus independently streamed state. Therefore partial application is a real design possibility: the first setting may change before a later command fails or the connection drops. This is an inference from the command/readback structure, not a demonstrated wheel fault. [Command branches][commands], [readback structure][readback].

Planning implications, not settled user-interface decisions:

- Track requested preset separately from fresh observed settings. Only label a preset active once every included, correctly mapped field agrees in observations received after the switch request.
- Represent pending, confirmed, partial/failed, and unknown outcomes. A successful BLE enqueue is not confirmed application; an interrupted sequence must not claim the whole preset changed.
- Keep fragmented command bytes serialized. If horn access shares this channel, schedule it at complete-command boundaries; interleaving a horn inside the fragments of a 31-byte setting command could corrupt the command stream.
- Preserve unknown/unsupported fields and settings the preset does not include. Optional Pedal Dip should not become an invented zero-valued write.
- Do not infer a retry count, rollback order, switch deadline, or persistence policy from missing protocol documentation. Readback cadence and command acceptance latency need observation before an “instant” switching claim.

These requirements follow from the lack of an observed atomic transaction and from submission-only BLE semantics. [Builders][builders], [transport result semantics][transport], [readback][readback].

## Motion, firmware, and persistence limits

The reference command builder checks a broad model-family capability level (`mVer >= 3`) and excludes Nosfet from two newer percentage controls. Here `mVer` is a **model family**, not a Sherman L software version: family 6 cannot prove a control exists on every `006.*` firmware. The subtype-8 unsupported marker is a stronger per-field clue, still requiring the correct mapping. No exact minimum Sherman L firmware for assist, separate softness, or Pedal Dip was established. [Capabilities and calls][commands], [identity parsing][modeparse], [readback][readback].

The inspected builders contain no speed condition for these setters. That only shows client behavior. It does not establish whether the wheel rejects changes while moving, delays them, ramps them, applies abruptly, or beeps. The manufacturer page describing adjustable hardness does not document remote setting changes during motion. Firmware-side motion restrictions remain open. [Command code][commands], [manual][manual].

No cited command field describes saving, volatile-only application, flash wear limits, or preset slots on the wheel. No wheel reboot/disconnect test was performed. App-owned preset definitions and wheel-owned current settings must therefore be modeled separately, with reconnect behavior decided after persistence is observed. There is also no evidenced command to query a named wheel preset. [Command construction][builders], [readback][readback].

## Independent offline vector check

Python `zlib.crc32` was used to construct these candidate vectors from the pinned source layout. They are examples for parser/encoder comparison, **not captured Sherman L commands** and not instructions to send to a wheel. No upstream suite was run.

```text
Dynamic assist 60%, 31 bytes:
4c6441701f0102808080808080808080808080808080808080803c6831fed2
Separate sensitivity/hardness 50%, 15 bytes:
4c6441700f010280808032b28c8c46
Acceleration reduction 40%, 33 bytes:
4c64417021010280808080808080808080808080808080808080808028c549a32e
Candidate continuous riding mode 50%, 12 bytes per format:
4c6b41700c01803cf08f1891
4c6441700c01003c3d44f033
```

Reproduction: create a byte array through the value position, fill unused positions with `0x80`, set header/command/flags/value as above, and append `zlib.crc32(payload).to_bytes(4, "big")`. Source tests independently exercise raw 0/50/100 for `0x0F`, 60 for assistance, and 40 for reduction; continuous mode lacks an equivalent demonstrated hardware round trip. [Builders][builders], [wire tests][wiretests], [audit F6][audit].

## Precise follow-up questions

Tracked by [Verify EUC World control mappings and horn on the owner’s Sherman L](https://github.com/EvgenyHitexis/EucWatch/issues/9).

1. Which exact percentage UI controls in the owner's app correspond to continuous `0x0C`, separate `0x0F`, assist `0x1F`, and reduction `0x21`? Identify Pedal Dip without substituting the degree-based `0x10`. Record app version, exact labels, and wheel firmware.
2. For each mapped field, can a controlled setting change produce a matching outgoing command and fresh readback on the owner's Sherman L? Establish endpoints, step size, unsupported behavior, and continuous mode's asymmetric offsets. This is a future evidence task, not performed here.
3. What persists after disconnect/reconnect and ordinary power cycling? How does firmware handle a command while moving, and is that behavior documented or reproducibly observed?
4. What are complete-command write timing and subtype-8 update timing? What happens when a preset sequence is interrupted? These facts gate the fast-switch and priority-horn interaction policy.

The initial investigation can close with these explicit findings and follow-ups. It must not be recorded as “all three preset controls verified for riding.” The watch's absence does not block planning the preset model, confirmation behavior, or the remaining EUC protocol questions.

[manual]: https://fccid.io/2BDSK-SHERMAN-L/User-Manual/User-Manual-7527579.pdf#page=10
[audit]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/docs/official-app-audits/veteran-leaperkim-nosfet.md
[reference]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/docs/leaperkim-protocol-reference.md
[commands]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonMain/kotlin/org/freewheel/core/protocol/VeteranDecoder.kt#L1258-L1310
[builders]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonMain/kotlin/org/freewheel/core/protocol/VeteranDecoder.kt#L975-L1037
[readback]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonMain/kotlin/org/freewheel/core/protocol/VeteranDecoder.kt#L514-L553
[merge]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonMain/kotlin/org/freewheel/core/protocol/VeteranDecoder.kt#L440-L461
[modeparse]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonMain/kotlin/org/freewheel/core/protocol/VeteranDecoder.kt#L331-L351
[settings]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonMain/kotlin/org/freewheel/core/domain/settings/WheelSettingsConfig.kt#L97-L115
[appcommands]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonTest/kotlin/org/freewheel/core/protocol/LeaperkimAppCommands.kt
[wiretests]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonTest/kotlin/org/freewheel/core/protocol/VeteranCommandWireMappingTest.kt#L106-L124
[transport]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonMain/kotlin/org/freewheel/core/service/WheelTransportProfile.kt#L38-L52
[blewrite]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/androidMain/kotlin/org/freewheel/core/service/BleManager.android.kt#L797-L843
[synthetic]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonTest/kotlin/org/freewheel/core/protocol/fixtures/LeaperkimBatch1Fixtures.kt#L238-L305
[wheellog]: https://github.com/Wheellog/Wheellog.Android/blob/f44e39e5388e500a5d2f315d1dcf32f167607bf8/app/src/main/java/com/cooper/wheellog/utils/VeteranAdapter.java
[fixture]: https://github.com/Wheellog/Wheellog.Android/blob/f44e39e5388e500a5d2f315d1dcf32f167607bf8/app/src/test/java/com/cooper/wheellog/utils/VeteranAdapterTest.kt#L488-L519

[eucworld]: https://euc.world/blog/euc-world-2-48-0-has-been-released/
