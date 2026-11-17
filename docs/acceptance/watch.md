# Offline watch implementation evidence

Current preset defaults, migration, local Save/Cancel and native swipe expectations
follow #43. See [watch editor acceptance](watch-preset-editor.md) and the
[#43 matrix](local-preset-revision.md). Prior #42 artifacts retain their original
provenance and cannot establish acceptance of the current interaction. Physical
watch, deployment and owner acceptance remain pending under #9/#31/#37/#38.


This records #32/#33 software verification for the original P22 Espruino 2v14
application. It is not watch deployment or hardware acceptance. The installed
Espruino runtime, SoftDevice and bootloader remain unchanged.

Run from the repository root with Node 22 or newer (the independent test packet
generator uses Node's built-in CRC32):

```sh
node watch/tests/offline.cjs
node watch/tests/runtime.cjs
node watch/tests/alerts.cjs
node watch/tests/alerts-runtime.cjs
node watch/tests/compare-alerts.cjs
```

The first harness drives the production application's public actions, session
transitions, raw notifications and controlled clock. The second executes the
actual `main`, hardware adapter, display driver and independent recovery startup
with fake pins, I2C, native calls, BLE and timers. It regenerates
[the dashboard SVG](../../watch/evidence/dashboard.svg) and
[the evidence record](../../watch/evidence/offline.json). The SVG replays actual
Graphics draw operations using host fonts; it does not assert exact Espruino
glyphs or physical pixels. The native-transfer calls are faked, while the real
Graphics allocation is checked for a 7,200-byte framebuffer.

The alert comparison uses the exercised Python 3.12 environment at
`experiments/laptop-feasibility/.venv/bin/python`; install the existing locked
environment using the repository launcher first, or set `EUCWATCH_TEST_PYTHON`
to another Python 3.12 interpreter. All comparison operations are offline.
[Alert evidence](../../watch/evidence/alerts.json) records the reproducible raw
packets/actions, expected and observed pulse events, 322 matching public states,
and source fingerprints. It compares newly emitted pulse events because laptop
mode transitions clear diagnostic history while the watch keeps bounded
history. [The physical-editor SVG](../../watch/evidence/alerts-editor.svg) is a
host-font rendering of actual Graphics operations, with the same limits as the
dashboard artifact.

| Scenario | Expected result | Observed offline result | Provenance |
| --- | --- | --- | --- |
| Sanitized source recording | Three valid frames; speed 0, PWM 2, estimated battery 97%, average 4.09 V/cell | Passed | Existing laptop fixture, raw notification boundaries/receipt times |
| 75/77/87/99-byte frames at every split point | Identical decoded dashboard | Passed | Synthetic frames with independently generated Node CRC32 |
| Corruption, wrong identity, 10,000 noise bytes and coalesced recovery | Reject invalid input; retain at most 98 bytes; valid following frames restore freshness | Passed | Synthetic raw notifications through production parser |
| One-second silence, confirmed disconnect and stale session callback | Dashes, dim last-known wheel battery, warning; old session cannot refresh; new session needs new frames | Passed | Controlled application clock and fake direct BLE loss/reconnect |
| Render scheduling | At most five draws/second; fresh/stale presentation within target schedule under controlled time | Passed | Production presentation seam; fake clock, not a device timing measurement |
| Wheel percentage and average rounding | Clamp at 119.02/148.05 V; accepted estimate; two decimals including 4.115→4.12 | Passed | Synthetic voltage boundaries |
| Watch battery and charging | Clamp/truncate 3.5–4.19 V; disconnect sampled analog pin; refresh independently | Passed | Actual hardware adapter with fake ADC/PIN_CNF; charger debounce 500 ms |
| Physical navigation paths | Left→riding slots, down from top→Settings, up→Settings hierarchy, right→dashboard from riding slots, Settings Sleep; whole wake button cycle consumed | Passed | Public actions and raw CST816 interrupt bytes with fake pins |
| Initial idle versus established loss | Sleep after 30 idle seconds before connection; keep warning awake after connected loss | Passed | Controlled clock |
| Direct connection and cleanup | Explicit discovery/selection, FFE0/FFE1 subscribe, bounded operations, no wheel writes; failed cleanup blocks replacement connection | Passed | Actual direct adapter with fake Promise-returning 2v14 GATT |
| Wheel selection returns to the Riding dashboard (#64) | Selecting a discovered wheel on the connection screen shows the Riding dashboard; the transport calls the explicit `wheel_selected` core action, not a gesture (scope as of #64; #59 replaced `wheel_selected`) | Passed | Actual main/transport with raw CST816 tap and fake GATT; fails before the fix |
| The core decides what every touch means (#59) | Connect, select and disconnect are core actions asked of the transport; an accepted discovery opens Wheel selection and an accepted selection returns to the Riding dashboard; a refusal stays on its screen with the reason; link events never change the screen; unknown action names are refused | Passed | `wheel-selection.cjs`: public core `touch`/`gesture` with a fake transport and production render; `runtime.cjs` taps through actual main/transport |
| Startup vibration and reconnect retry | D16 idle 0; first failed reconnect can recover on a later attempt; stop after three retries; initial selection failure stays terminal | Passed | Actual hardware/transport with fake pins and delayed wheel availability |
| Independent recovery | Held startup button bypasses app imports; failed startup leaves console recovery/watchdog | Passed | Production boot code in fake runtime, no device boot attempted |
| Alert defaults/editing | Lost enabled; measurement alerts disabled with null thresholds; independent switches, decimal keypad, explicit Save/Cancel, validation and back discard | Passed | Public core and raw touch through the actual entry |
| Alert patterns/repeat/rearm | Lost 1×150 ms per interruption; PWM 3×150 ms/2 s; speed 2×150 ms/5 s; battery 500 ms once per crossing and +3/5 s continuous-fresh rearm | Passed | Controlled raw packets; laptop/watch pulse comparison |
| Alert competition/freshness | Lost>PWM>speed>battery, no overlap, every valid frame evaluated; stale cancels measurements, no overdue bursts | Passed | Public-core source-derived packets and controlled clocks |
| Watch Storage | Explicit Save survives restart; refused staging/partial activation keep old copy; interrupted first Save has validated default backup; missing/corrupt active copy recovers good backup | Passed | Actual main/store adapter with fake Storage failures; not a claim of atomic Storage |
| Vibration output | Installed D16 active-high start1/stop0, independent 150/500 ms output deadline; shutdown cannot reactivate output | Passed | Actual motor/hardware with fake pins/timers; no physical motor operation |
| Paint signature covers what the screen shows (#70) | Every view field the renderer and touch targets read is in the paint signature or is a listed derived field; "Vibration output unavailable" repaints when only the output error changes | Passed | `paint-signature.cjs` reads the production sources; `alerts.cjs` drives the public core with a failing vibration output |

`watch/app.js` owns parsing, freshness, calculations, navigation and clocks.
`watch/main.js` composes narrow adapters; its public `start(options)` returns
`core`, `transport` and `stop`. The core exposes `touch(x, y)`,
`gesture(name, payload)`, `action(name, payload)`, `receive(session, rawBytes)`,
`tick()` and `view()`. Raw notifications and replayed test input share its
actual parser.

Watch behavior change (#59): the core decides what every touch and gesture
means. `touch` hit-tests the screen and `gesture` takes the hardware's swipes,
button and battery inputs; both add the current Preset editor and entry ids,
which `main.js` and `controls.js` no longer add. Connect wheel, Disconnect wheel
and choosing a wheel on Wheel selection are core actions that ask the transport
through an adapter; the transport reports only link events (devices, session
start, connected, disconnect) and no longer sends `open_connection` or
`wheel_selected`. Two visible changes: a discovery or selection the transport
refuses now stays on its screen with the reason shown, where before nothing
showed (a discovery tapped while a timed-out connect is still pending says
"Previous Bluetooth operation is still pending"); and the core refuses every unknown action name, as the laptop does,
instead of ignoring it (`interact` and `button_hold` are accepted no-ops). Every
`watch/evidence/**` file regenerates unchanged
(`scripts/evidence-compare.py cea77ec`).

Watch behavior change (#64): from #49 until #64, selecting a wheel left the watch
on the connection screen, because the transport sent a right swipe and #49 had
limited swipe right to the riding Preset menu. The transport now calls
`wheel_selected`, which returns from the connection screen to the Riding
dashboard. Discovery, selection failure, disconnect and reconnect are unchanged.
`watch/evidence/local-presets/regression-dashboard.svg`, which `runtime.cjs`
captures after selection, showed SELECT WHEEL before #64. It now shows the
connected Riding dashboard.

Watch behavior change (#56): the alert editor (alert draft, alert page and
threshold entry) moved from `watch/app.js` into `watch/alert-editor.js`, and
the threshold keypad now holds at most 8 characters, down from 10, to match the
laptop. A '.' counts toward the 8, and only one '.' is accepted. A key typed at
the limit is ignored, as a second '.' already was; before, the key that would
have made an 11th character was refused. `node watch/tests/alert-editor.cjs`
replays the key sequence in
[alert-editor-keys.json](scenarios/alert-editor-keys.json) through the watch
alert editor alone, and `tests/test_alert_editor.py` replays the same file
through the laptop alert editor. No regenerated evidence showed an entry longer
than 8 characters, so the limit changed no evidence file;
`watch/evidence/local-presets/bundle.json` changed only because the bundle now
ships the new module.

Parity change (#55, #56 review): the laptop alert editor now follows the
watch's rules, and the shared trace has no laptop exceptions. Set value refuses
an entry above the alert's limit, or a lone '.', with "Threshold outside
supported range" and keeps the entry open; the laptop used to accept it and
refuse at Save. Every accepted editor action clears the explanation, opening
the keypad included; a refused one leaves it. Keypad Cancel needs no open
entry. Save's out-of-range text names the range on both sides, for example
"Invalid High speed threshold (0-3276.7 km/h)" (the laptop wrote "(0–100%)").
After a refused Set value both keypads keep the alert's name above "Invalid
threshold" and the entry; the watch used to replace the name.

`watch/THIRD_PARTY.md` records
pinned driver provenance and the required MIT display notice.

Battery samples occur on startup, every 30 seconds, and on a debounced charger
transition. They are independent of wheel freshness and continue with the
screen asleep. Render diagnostics expose `process.memory()`, draw count,
complete-frame receipt time, last display time, receipt-to-display maximum,
and last/maximum paint duration. The runtime harness explicitly labels its
memory values as simulated; neither source size nor the host process proves
actual P22 memory fit.

Alert and motor diagnostics each retain at most 32 events plus a total count.
They distinguish requested pattern duration, scheduler calls and independent
output-deadline stops. Software pin-call timestamps do not measure physical
motor onset. The ordinary 50 ms behavior tick evaluates independently of
rendering; raw frames also evaluate immediately. Missed pattern phases are
discarded after a long clock gap. Save stages/read-verifies complete version1
configuration and writes a validated old/default backup before active
replacement. The same local persistence format and recovery adapter remain in
use after #40 removed configuration exchange; see
[local configuration checks](local-configuration.md).

Production sources use ES5-compatible syntax and Storage module names `sw-*`.
The eventual installation bundle must rewrite those module references to its
verified versioned names before activation; merely changing the entry filename
would mix versions. `boot.js` is the separate recovery startup candidate, not
an instruction to replace the current startup. #36 owns concrete staging,
checksums, activation and recovery tooling.

Remaining device evidence follows the
[accepted watch decision](https://github.com/EvgenyHitexis/EucWatch/issues/12#issuecomment-6039430334):
after laptop acceptance and separately authorized installation, measure actual
memory fit, frame receipt/display timing, display/native palette behavior,
touch origin/rotation, full wake button cycles, charger/ADC indication, and a
10-minute stationary live session with loss/recovery. Owner review must cover
readability indoors/daylight and physical controls. Alert software is
implemented; physical vibration and owner pattern recognition remain pending.
Preset/horn software traces are recorded in [watch controls](watch-controls.md);
their physical checks remain separate. Configuration-transfer gates were
superseded by #40; their retained artifacts describe the former scope only. No firmware replacement, riding experiment, deployment, radio scan,
physical connection or horn operation was performed for this evidence.
