# Sherman L direct Bluetooth telemetry contract

Investigated 2026-10-06 for [Establish the Sherman L Bluetooth telemetry contract](https://github.com/EvgenyHitexis/EucWatch/issues/3). This is research for an original custom watch application. The owner's watch and wheel firmware have not been identified or tested.

## Finding and evidence boundary

The proposed riding dashboard has a substantiated read path: connect as a BLE central, subscribe to FFE1 in FFE0, assemble Veteran-family frames, validate CRC32, and decode Sherman L model-family 6. Speed, pack voltage, wheel temperature, and reported PWM are present. WheelLog estimates battery percentage from voltage. A deeper cross-check finds an additional candidate for wheel-reported state of charge in FreeWheel, not exercised by the available Sherman L packet; distinguish that candidate from the verified voltage path. Connection status comes from transport state and freshness of valid telemetry.

WheelLog contains an explicit Sherman L firmware `006.0.03` test fixture, a full CRC-valid 87-byte frame, and expected measurements. This establishes a concrete starting contract for that firmware; it does not establish compatibility with every firmware or the unidentified watch. No manufacturer-issued byte-level specification was located in this investigation. Statements below distinguish implementation evidence, independently repeated calculations, recommendations, and remaining verification. [Decoder][decoder], [fixture][fixture].

## Pinned primary sources

WheelLog revision: `f44e39e5388e500a5d2f315d1dcf32f167607bf8`. Igor's EUC Watch reference revision: `c12e42acd069667ddb08ba8da3bf1e3a0a9c08cc`. FreeWheel revision: `7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca`. ESPHome reference revision: `46f86791b94a8a0408c7099f8f27f316b187de8d`. Source was retrieved through GitHub's contents API with raw accept headers; no local code checkout or persistent source cache was created. Multiple implementations are corroboration of interpretation, not automatically independent hardware observations.

| Source | Evidence |
| --- | --- |
| [VeteranAdapter.java][decoder] | Model identification, offsets, battery curves, assembly and CRC |
| [VeteranAdapterTest.kt][fixture] | Explicit Sherman L firmware 006.0.03 fixture |
| [Constants.kt][constants] | Full GATT UUIDs |
| [BluetoothService.kt][ble] | Notification delivery and MTU negotiation |
| [WheelData.java][data] | Notification setup, unit conversion, hardware PWM |
| [GotwayVirtualAdapter.java][detect] | Protocol selection using frame header |
| [EUC Watch eucVeteran.js][watch] | Direct-watch setup and independent main-field scaling |
| [FreeWheel VeteranDecoder.kt][freewheel] | Cross-check, extended version identity, candidate reported SOC |
| [FreeWheel SOC tables][soc] | Alternative voltage estimate, attributed by authors to manufacturer app |
| [ESPHome Veteran component][esphome] | Additional parser comparison; hardware reports concern other models |

## Direct connection

Service: `0000ffe0-0000-1000-8000-00805f9b34fb`.
Notification characteristic: `0000ffe1-0000-1000-8000-00805f9b34fb`.

WheelLog initially recognizes the service as Gotway-style, subscribes, then switches to Veteran on header `DC 5A 5C`; Begode instead begins `55 AA`. UUIDs alone do not identify Sherman L. The family is established from a validated telemetry frame's version word. [Constants][constants], [detection][detect], [setup][data].

The watch reference calls `NRF.connect`, discovers FFE0 then FFE1, registers the notification callback and disconnect listener, and calls `startNotifications`. Its requested connection interval is 7.5–15 ms, an implementation choice rather than a measured telemetry cadence or mandatory interval. No proprietary authentication or polling command occurs in that read setup. Confirm the owner's firmware accepts the same sequence. [Watch][watch].

Normal GATT subscription configuration is still required through the chosen BLE stack. Optional connect beeps, light changes, trip resets, and wheel commands in the references are unrelated to the requested read path and should not be copied into it. Discovery should let the owner select the device, remember its identity, and verify family 6 in received telemetry. Exact advertised name, address stability, bonding, and simultaneous phone connection behavior remain unverified. [Watch][watch], [WheelLog setup][data].

The exact WheelLog call chain is `onServicesDiscovered` → `detectWheel` → the Gotway branch's `setCharacteristicNotification(characteristic, true)` → `wheelConnection.setNotify(characteristic, enabled)`. Successful `onCharacteristicUpdate` callbacks route the received byte array to decoding. Unlike its KingSong branch, the Gotway/Veteran branch does not separately write a descriptor in WheelData; notification configuration is delegated to the BLE library's `setNotify`. This distinction matters when porting to a different stack: reproduce successful subscription, not just a local callback registration. [BLE setup and delivery][ble], [selection and subscription][data].

The dependency is Blessed Android 2.4.1, pinned here to `29a8b58fb26a87c2bfe8dd518a6a2bd41d2bb256`. Its `setNotify` verifies notification/indication properties and the client configuration descriptor, enables the local callback, and queues the descriptor write. This resolves the apparent missing subscription write in WheelLog. A successful enqueue is not subscription completion: wait for the stack's completion callback before reporting a subscribed connection. [Dependency declaration][appbuild], [actual subscription implementation][blessed].

## Stream framing and CRC

Offsets start at the first `DC` byte, not at a notification boundary.

| Offset | Meaning |
| --- | --- |
| 0–2 | Header `DC 5A 5C` |
| 3 | Unsigned length L |
| 4 onward | Core fields and extensions |
| L through L+3 | Modern-format CRC32, big-endian |

Modern total frame size is `L + 4`. Compute standard CRC32 (`java.util.zip.CRC32`, independently checked with Python `zlib.crc32`) over bytes `[0,L)`, including header and length, and compare with the final unsigned big-endian word. WheelLog enables CRC when L > 38, and keeps checking CRC thereafter. Its older no-CRC path is not evidence that Sherman L should accept unchecked frames. The watch reference instead bypasses CRC below firmware 3012, a different heuristic. A new app should require CRC for the demonstrated Sherman L format and investigate unfamiliar formats explicitly. [Unpacker][decoder], [watch checksum][watch].

WheelLog consumes byte-by-byte across notifications. It resets incomplete assembly after a gap over 100 ms and performs additional charge/pedal-byte sanity checks. These are reference heuristics, not manufacturer timing or value guarantees. A new parser needs bounded storage, length checks before access, corrupt-data recovery, split headers, and support for multiple frames per callback. The watch reference assumes headers start notifications and drops overlong accumulated input, so it is not a complete stream-parser template. [Unpacker][decoder], [watch assembler][watch].

The specific WheelLog sanity gates reject byte 22 unless zero, byte 23 unless 0 or 1, and byte 30 unless 0 or 7. They can reject a valid-CRC frame before CRC evaluation if new firmware changes these fields. Its unpacker also accepts old short frames without CRC before `usingCrc` is enabled, while the decoder reads through offset 35 and optional BMS branches assume further offsets. A new Sherman L-only parser should validate its own minimum/maximum supported length and each extension boundary rather than inherit these implicit assumptions. [Unpacker and field reads][decoder].

## Sherman L fixture and independent check

The upstream `decode veteran sherman l` test supplies these five chunks, 20/20/20/20/7 bytes:

```text
dc5a5c53397afffe0aa400000df10000000a0b3d
0e0e0000037a035217730064000e00b480c80000
808080808080058080808080800ff30ff50ff50f
f50ff50fef0ff20ff30ff30ff30ff30fed0ff30f
f40ff5378c5145
```

Concatenation is 87 bytes. Length L is `0x53` (83); CRC trailer is `37 8c 51 45`. A read-only Python calculation during this investigation independently returned CRC32 `0x378c5145` and the following values. The full upstream test suite was not executed. [Fixture][fixture], [conversion][data].

| Quantity | Independently decoded result |
| --- | --- |
| Firmware | 6003 → family 6, version 006.0.03 |
| Voltage | 147.14 V |
| Signed speed | −0.2 km/h |
| Main temperature | 28.77 °C |
| PWM | 1.80% |

The fixture's own assertions check absolute speed in tenths as 2, integer temperature 28, voltage 147.14, phase current 1.0 A, trip 2.724 km, total distance 3569 m, battery estimate 97%, pitch 0.14°, and version 006.0.03. Its test configuration does not establish a hardware-PWM assertion; 1.80% above is an independent decoding using the implementation's documented arithmetic, not an upstream assertion. These are fixture observations, not measurements from the owner's wheel. [Fixture][fixture].

## Core field contract

All 16-bit fields here are big-endian; signed means two's-complement.

| Quantity | Offset/type | Conversion |
| --- | --- | --- |
| Voltage | 4, uint16 | raw / 100 V |
| Speed | 6, int16 | raw / 10 km/h; retain sign internally |
| Main temperature | 18, int16 | raw / 100 °C; exact physical sensor location not established |
| Firmware/model | 28, uint16 | family = floor(raw/1000); family 6 explicitly means Sherman L |
| PWM | 34, uint16 | raw / 100 percent; raw / 10000 duty fraction |
| Battery percentage | no native field used by WheelLog | voltage estimate; FreeWheel subtype-2/byte-50 candidate discussed below |
| Connection status | no payload field | BLE lifecycle and valid-frame freshness |

Firmware formatting is family, then floor((raw modulo 1000)/100), then raw modulo 100. For raw 6003, WheelLog renders `006.0.03`. The decoder also contains trip/total distance, phase current, sleep/charge state, speed settings, pedal mode, and pitch. Their presence is not a reason to expand the first dashboard. [Decoder][decoder], [unit conversion][data].

Additional fields decoded by WheelLog, useful for understanding the frame even though they are outside the initial display:

| Quantity | Offset/type | Interpretation and boundary |
| --- | --- | --- |
| Trip distance | 8, two uint16 words | `(BE16(10) << 16) \| BE16(8)`, meters; low word first |
| Total distance | 12, two uint16 words | `(BE16(14) << 16) \| BE16(12)`, meters; low word first |
| Phase current | 16, int16 | raw / 10 A; do not label as measured battery current |
| Auto-off/sleep | 20, uint16 | interpreted by WheelLog as seconds |
| Charge mode | 22, uint16 | charging status; fixture value 0 |
| Speed alarm setting | 24, uint16 | raw / 10 km/h; not average speed |
| Tiltback speed setting | 26, uint16 | raw / 10 km/h; not a dashboard alert instruction |
| Pedal/settings region | 30, uint16 in WheelLog | fixture value 100; not established as a simple three-value enum |
| Pitch | 32, int16 | raw / 100 degrees |

Distance uses swapped 16-bit words, not conventional 32-bit big-endian. WheelLog's helpers return zero on short inputs; a new decoder must represent missing/invalid data explicitly rather than accepting these zero defaults. WheelLog's battery-current value is derived from phase current multiplied by its PWM fraction; it is not an additional independent current measurement in the core frame. [Field reads][decoder], [integer helpers][math], [current calculation][data].

The watch reference corroborates voltage /100, speed /10, temperature /100, and PWM /100. It differs on current: it divides offset 16 by 100, while WheelLog's final physical phase current is raw /10. FreeWheel and the Sherman L fixture support WheelLog's /10 interpretation. The watch implementation should not be used as the authority for that field. [Watch][watch], [WheelData][data], [FreeWheel][freewheel].

### Reported PWM

WheelLog explicitly treats Veteran family >=2 as hardware-PWM capable, including Sherman L family 6. Its hardware path divides received output by 10000 to obtain a duty fraction. A separate calculated-PWM fallback uses speed and voltage. The new app should preserve reported-PWM provenance instead of silently substituting an estimate. [Recognition and conversion][data], [decoder][decoder].

The sources do not establish a manufacturer guarantee relating the field to exact remaining torque, cutout margin, or a universal alert threshold. Display support is established; vibration thresholds and behavior remain decisions, with ordinary hardware validation still required.

### Battery estimate

WheelLog explicitly groups Sherman L with Lynx for the curve and returns 36 cells for family 6. Its default calculation, with V in volts, is 0% at V<=119.02, 100% at V>=148.05, otherwise `round((V-119.02)/0.2903)`. [Battery branches][decoder].

Its optional improved curve is 0% at V<=115.20; `round((V-115.20)/0.81)` through 122.40; `round((V-119.70)/0.306)` through 150.30; then 100%. These are application heuristics, not native wheel state-of-charge or calibrated energy/range measurements. A later UI decision should document the selected curve, clamp its result, and consider showing actual voltage alongside estimated percent. [Battery branches][decoder].

WheelData can replace the adapter's result again when its custom-percent setting is enabled. Consequently a screenshot from WheelLog need not match either adapter curve even at the same voltage. Retain the raw voltage and document which estimation policy is used. [Custom-percent override][custombattery].

### Additional temperatures and BMS

Family >=5 also has extended BMS packets. Byte 46 is a subtype; subtypes <4 address BMS1 and the following group BMS2. Subtypes 3/7 contain six signed temperature words at offsets 47,49,51,53,55,57 divided by 100. Cell values are spread across subtypes 1/5, 2/6, 3/7, in millivolts, while 0/4 can contain currents at offsets 69/71. Subtype 8 remains unrecognized in WheelLog. Exact sensor identities, complete-cycle freshness, and a dedicated motor-temperature field are not established. None is required for the initial main-temperature display. [BMS decoder][decoder].

The page-five Sherman L fixture yields BMS2 cells 1–15 at offsets 53–82: `4.083, 4.085, 4.085, 4.085, 4.085, 4.079, 4.082, 4.083, 4.083, 4.083, 4.083, 4.077, 4.083, 4.084, 4.085 V`. This independent calculation confirms one page's layout, not a complete BMS cycle. Pages 1/5 and 2/6 start their 15 cells at byte 53; pages 3/7 start their remaining cells at byte 59. Sherman L uses 36 series cells, so the first six final-page cell values complete the pack. Check field ends against L, the end of pre-CRC data, rather than against the total frame length; never decode checksum bytes as cell readings. Track page freshness/completeness before deriving pack aggregates. [Fixture][fixture], [BMS decoder][decoder].

## MTU and freshness implications

The explicit fixture represents an 87-byte application frame in chunks <=20 bytes. Thus a frame >20 bytes does not by itself require ATT MTU >23; the app still needs a larger assembly buffer. This is a fixture representation, not proof of all live Sherman L notification behavior. [Fixture][fixture].

Current WheelLog requests MTU 517 and describes payload capacity as MTU minus 3, falling back to default 23. Its comment explains the maximum request in terms of extended KingSong frames, so it is not evidence Sherman L requires 517. Verify the owner's actual negotiated MTU, maximum notification size, all observed frame lengths, and runtime truncation. A one-byte length represents at most 259 total bytes, but supported lengths should be justified by real firmware evidence rather than accepting every possible value. [BLE code][ble], [unpacker][decoder].

On 5 May 2026, the community maintainer described unfinished watch firmware changes for buffers larger than about 20 bytes. That exchange concerned Nosfet support: it is a watch-runtime warning, not a Sherman L failure report. A 15 November 2024 chat message asking about a Sherman L update establishes a request, not working compatibility. [May discussion](../ChatExport_2026-10-06/messages11.html#message13193), [November question](../ChatExport_2026-10-06/messages11.html#message11508).

Proposed app requirement: timestamp accepted frames monotonically and distinguish disconnected, connecting, waiting-for-data, live, and stale. Never present a retained value as fresh when notifications stop or validation fails. No authoritative cadence, stale timeout, or alert latency was found; those need measurement. The reference 100 ms assembly reset is not a justified dashboard-staleness threshold.

## Cross-checks and conflicts

### Firmware identity is wider than WheelLog's field

FreeWheel reconstructs `fullVersion = (byte30 << 16) | (byte28 << 8) | byte29`. Its implementation attributes zero high byte to Leaperkim and `0x07` to Nosfet. Sherman L's demonstrated `00 17 73` still yields 6003 and family 6; the implementations agree for this frame. Preserve all three identity bytes instead of treating byte 30 solely as part of a pedal setting. FreeWheel interprets byte 31 as ride mode; a value like 100 is not established as a three-position enum. This is implementation evidence beyond WheelLog, not a new observation from the owner's wheel. [Version reconstruction and mode](https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonMain/kotlin/org/freewheel/core/protocol/VeteranDecoder.kt#L331-L351).

### Reported SOC candidate and different battery estimates

FreeWheel selects a subtype with the unsigned byte at offset 46. For subtype 2 only, it accepts byte 50 as reported battery percent when it is 0–100. `0x80`, present as unsupported/filler data elsewhere, is not a valid percent. It retains a valid reported value across other subtypes. If a subsequent subtype-2 frame has no valid percent, it uses and retains its voltage estimate instead. This distinction is important for provenance and freshness: simply displaying its headline percent would hide whether the latest value was reported or estimated. [Subtype selection](https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonMain/kotlin/org/freewheel/core/protocol/VeteranDecoder.kt#L402-L405), [percent field](https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonMain/kotlin/org/freewheel/core/protocol/VeteranDecoder.kt#L496-L507), [retention](https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonMain/kotlin/org/freewheel/core/protocol/VeteranDecoder.kt#L683-L703).

This candidate is absent from WheelLog's battery decoding and unverified by the available Sherman L page-five packet. Do not claim that all Sherman L firmware supplies it. If implemented later, validate the subtype, payload boundary and value, timestamp it separately, and keep an explicit voltage-derived fallback.

FreeWheel also maps family 6 to its `LYNX_151V` lookup table, whose authors attribute it to the Leaperkim Android app. The table returns 0% at/below 113.40 V and 100% at/above 148.50 V; its intermediate selection returns 60% at 135.00 V. At that same voltage WheelLog's default is 55% and its improved curve is 50%. These materially different estimates mean the battery display requires a documented policy, rather than assuming every application's percent is the same measurement. This research inspected FreeWheel's implementation and provenance notes, not the manufacturer APK itself. [Table selection](https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonMain/kotlin/org/freewheel/core/protocol/VeteranDecoder.kt#L655-L669), [table and conversion][soc].

### Why the old watch parser is not a specification

- Igor's v2 module calls offset 24 average speed; WheelLog and FreeWheel identify it as the configured speed-alarm threshold.
- Its current scaling differs by a factor of ten from WheelLog, FreeWheel, and the Sherman L fixture interpretation.
- The older P8 module assumes fixed 20-byte fragments and reads continuation offset 12 as PWM; under that assumption this is absolute byte 32, the modern pitch field, instead of PWM at 34.
- Its v2 notification assembler expects a header at a callback boundary and an exact accumulated size. A stream implementation must handle arbitrary fragmentation and concatenation.

[v2 field reads](https://github.com/igorpl/eucWatch/blob/c12e42acd069667ddb08ba8da3bf1e3a0a9c08cc/v2/euc/eucVeteran/eucVeteran.js#L39-L79), [old P8 parser](https://github.com/igorpl/eucWatch/blob/c12e42acd069667ddb08ba8da3bf1e3a0a9c08cc/P8/eucVeteran/eucVeteran.js#L48-L99), [v2 assembly](https://github.com/igorpl/eucWatch/blob/c12e42acd069667ddb08ba8da3bf1e3a0a9c08cc/v2/euc/eucVeteran/eucVeteran.js#L100-L124).

### Temperature, MTU, and provenance limits

ESPHome labels the main field as motor temperature and an extended field as controller temperature, but its hardware reports concern Lynx/Aero rather than Sherman L. WheelLog and FreeWheel use a generic main-temperature field. The first app should not claim a motor/MOSFET sensor identity from this evidence alone. [ESPHome field interpretation][esphome].

FreeWheel's app-derived reference says the manufacturer app requests MTU 120 and chunks writes at 20 bytes. WheelLog requests 517, and its Sherman L fixture arrives in chunks of at most 20. These are three different observations; none proves a mandatory Sherman L receive MTU. [App-derived protocol notes](https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/docs/leaperkim-protocol-reference.md#L5-L12), [WheelLog BLE][ble], [fixture][fixture].

FreeWheel's explicit Sherman L fixture is synthesized by `buildMainFrame(ver=6000, voltage=13500)`; its old-board fixture is inherited from legacy WheelLog tests. Neither is an independent physical Sherman L recording. Its official-app audit is useful reverse-engineering evidence, but documentation and code differ in places; use the pinned executable behavior and retain the provenance distinction. [Synthetic fixture](https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonTest/kotlin/org/freewheel/core/protocol/fixtures/LeaperkimBatch1Fixtures.kt#L238-L246), [inherited fixture](https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonTest/kotlin/org/freewheel/core/protocol/fixtures/VeteranFixtures.kt#L3-L23), [audit](https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/docs/official-app-audits/veteran-leaperkim-nosfet.md).

## History and evidence strength

Sherman L support was merged on 5 September 2024 in [WheelLog's Sherman L change](https://github.com/Wheellog/Wheellog.Android/pull/500), merge `cd43f2e6e8a8a4bfb0a95bdb91cf9484f8377cf4`. The later [CRC verification fix](https://github.com/Wheellog/Wheellog.Android/pull/505), merged 1 October 2024 as `a4833f75d95ca4d432520b295917cf3483109c27`, makes CRC checking remain enabled after a valid long frame. This explains why older parsers can disagree about short-frame validation.

The named Sherman L test is the strongest model-specific packet evidence found in WheelLog. It verifies completion after the five chunks and common telemetry, but does not assert hardware PWM, speed sign, BMS cells, reconnect behavior, corrupt-frame handling, or the full page cycle. Its 1.80% PWM is our separate calculation, not an asserted upstream test result. The Lynx BMS replay in `RawDataTest.kt` is commented out and references a `RAW1.csv` absent from the pinned tree; it is not an executable Sherman L capture test. [Sherman L fixture][fixture], [raw-test source][rawtests].

## Reproducible independent calculation

The following standard-library-only Python calculation was executed during this investigation. It verifies the source fixture, selected units, and rejection of all 696 possible single-bit changes by length/CRC validation. It is a fixture verifier, not a production stream parser or a substitute for live-wheel testing. No Android test suite was run.

```python
import zlib,struct,json
chunks=[
"dc5a5c53397afffe0aa400000df10000000a0b3d",
"0e0e0000037a035217730064000e00b480c80000",
"808080808080058080808080800ff30ff50ff50f",
"f50ff50fef0ff20ff30ff30ff30ff30fed0ff30f",
"f40ff5378c5145"]
frame=bytes.fromhex("".join(chunks))
u16=lambda off:struct.unpack_from(">H",frame,off)[0]
i16=lambda off:struct.unpack_from(">h",frame,off)[0]
length=frame[3]
valid=lambda f:len(f)==f[3]+4 and zlib.crc32(f[:f[3]])==int.from_bytes(f[f[3]:],"big")
assert len(frame)==87 and length==83 and valid(frame)
assert zlib.crc32(frame[:length])==0x378c5145
assert (u16(4),i16(6),i16(16),i16(18),u16(28),u16(34),frame[46])==(14714,-2,10,2877,6003,180,5)
assert (u16(10)<<16 | u16(8))==2724
assert (u16(14)<<16 | u16(12))==3569
checked=0
for bytepos in range(len(frame)):
 for bit in range(8):
  corrupt=bytearray(frame);corrupt[bytepos]^=1<<bit
  assert not valid(corrupt)
  checked+=1
print(json.dumps({"bytes":len(frame),"chunks":[len(bytes.fromhex(c)) for c in chunks],"crc32":hex(zlib.crc32(frame[:length])),"voltage_V":u16(4)/100,"speed_kmh":i16(6)/10,"phase_current_A":i16(16)/10,"temperature_C":i16(18)/100,"firmware_word":u16(28),"PWM_percent":u16(34)/100,"BMS_page":frame[46],"single_bit_corruptions_rejected":checked},indent=2))
```

Observed result: 87 bytes, length 83, CRC `0x378c5145`; 147.14 V, -0.2 km/h, 1.0 A phase current, 28.77 °C, firmware word 6003, 1.80% PWM, BMS page 5; all 696 single-bit mutations rejected.

## Remaining verification

1. Identify watch processor/revision, runtime/install path, BLE-central support, memory, display, and vibration capability. The box photograph does not establish them.
2. Record wheel firmware, advertised identity, services and characteristic properties; confirm subscription-only telemetry, bonding and competing-phone behavior.
3. Capture normal read-only notifications with boundaries/timestamps; confirm family 6, lengths, CRC, MTU, no truncation, and cadence.
4. Compare speed, voltage, reported PWM, and main temperature with a known working display in ordinary conditions. Check the subtype-2/byte-50 reported-SOC candidate and select/document the voltage fallback. Document rounding and battery provenance. Decoding validation does not require a wheel-limit experiment.
5. Observe disconnect, wheel-off, reconnect, and connected-without-valid-data cases to choose freshness and reconnect policy.
6. On the identified watch, measure display/vibration responsiveness and battery cost. Alert UX, thresholds, hysteresis, and repetition remain human decisions.

This note supplies a protocol starting contract and a concrete Sherman L vector without requiring the owner to reverse-engineer it. It does not establish watch compatibility, implement an app, authorize wheel writes, or resolve human interface decisions.

[decoder]: https://github.com/Wheellog/Wheellog.Android/blob/f44e39e5388e500a5d2f315d1dcf32f167607bf8/app/src/main/java/com/cooper/wheellog/utils/VeteranAdapter.java
[fixture]: https://github.com/Wheellog/Wheellog.Android/blob/f44e39e5388e500a5d2f315d1dcf32f167607bf8/app/src/test/java/com/cooper/wheellog/utils/VeteranAdapterTest.kt#L488-L519
[constants]: https://github.com/Wheellog/Wheellog.Android/blob/f44e39e5388e500a5d2f315d1dcf32f167607bf8/app/src/main/java/com/cooper/wheellog/utils/Constants.kt
[ble]: https://github.com/Wheellog/Wheellog.Android/blob/f44e39e5388e500a5d2f315d1dcf32f167607bf8/app/src/main/java/com/cooper/wheellog/BluetoothService.kt
[data]: https://github.com/Wheellog/Wheellog.Android/blob/f44e39e5388e500a5d2f315d1dcf32f167607bf8/app/src/main/java/com/cooper/wheellog/WheelData.java
[detect]: https://github.com/Wheellog/Wheellog.Android/blob/f44e39e5388e500a5d2f315d1dcf32f167607bf8/app/src/main/java/com/cooper/wheellog/utils/GotwayVirtualAdapter.java
[watch]: https://github.com/igorpl/eucWatch/blob/c12e42acd069667ddb08ba8da3bf1e3a0a9c08cc/v2/euc/eucVeteran/eucVeteran.js
[appbuild]: https://github.com/Wheellog/Wheellog.Android/blob/f44e39e5388e500a5d2f315d1dcf32f167607bf8/app/build.gradle#L133
[blessed]: https://github.com/weliem/blessed-android/blob/29a8b58fb26a87c2bfe8dd518a6a2bd41d2bb256/blessed/src/main/java/com/welie/blessed/BluetoothPeripheral.java#L1422-L1485
[math]: https://github.com/Wheellog/Wheellog.Android/blob/f44e39e5388e500a5d2f315d1dcf32f167607bf8/app/src/main/java/com/cooper/wheellog/utils/MathsUtil.java#L108-L140
[custombattery]: https://github.com/Wheellog/Wheellog.Android/blob/f44e39e5388e500a5d2f315d1dcf32f167607bf8/app/src/main/java/com/cooper/wheellog/WheelData.java#L1058-L1073
[rawtests]: https://github.com/Wheellog/Wheellog.Android/blob/f44e39e5388e500a5d2f315d1dcf32f167607bf8/app/src/test/java/com/cooper/wheellog/RawDataTest.kt
[freewheel]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonMain/kotlin/org/freewheel/core/protocol/VeteranDecoder.kt#L321-L420
[soc]: https://github.com/nathan234/FreeWheel/blob/7c250f7f0c9b81249f1587a0b73ee2a8a827a7ca/core/src/commonMain/kotlin/org/freewheel/core/protocol/VeteranSocTables.kt
[esphome]: https://github.com/vaninanton/esphome-euc-leaperkim-nosfet/blob/46f86791b94a8a0408c7099f8f27f316b187de8d/components/veteran/veteran.cpp#L184-L217
