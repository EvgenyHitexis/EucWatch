# Offline watch implementation evidence

This records #32 software verification for the original P22 Espruino 2v14
application. It is not watch deployment or hardware acceptance. The installed
Espruino runtime, SoftDevice and bootloader remain unchanged.

Run from the repository root with Node 22 or newer (the independent test packet
generator uses Node's built-in CRC32):

```sh
node watch/tests/offline.cjs
node watch/tests/runtime.cjs
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

| Scenario | Expected result | Observed offline result | Provenance |
| --- | --- | --- | --- |
| Sanitized source recording | Three valid frames; speed 0, PWM 2, estimated battery 97%, average 4.09 V/cell | Passed | Existing laptop fixture, raw notification boundaries/receipt times |
| 75/77/87/99-byte frames at every split point | Identical decoded dashboard | Passed | Synthetic frames with independently generated Node CRC32 |
| Corruption, wrong identity, 10,000 noise bytes and coalesced recovery | Reject invalid input; retain at most 98 bytes; valid following frames restore freshness | Passed | Synthetic raw notifications through production parser |
| One-second silence, confirmed disconnect and stale session callback | Dashes, dim last-known wheel battery, warning; old session cannot refresh; new session needs new frames | Passed | Controlled application clock and fake direct BLE loss/reconnect |
| Render scheduling | At most five draws/second; fresh/stale presentation within target schedule under controlled time | Passed | Production presentation seam; fake clock, not a device timing measurement |
| Wheel percentage and average rounding | Clamp at 119.02/148.05 V; accepted estimate; two decimals including 4.115→4.12 | Passed | Synthetic voltage boundaries |
| Watch battery and charging | Clamp/truncate 3.5–4.19 V; disconnect sampled analog pin; refresh independently | Passed | Actual hardware adapter with fake ADC/PIN_CNF; charger debounce 500 ms |
| Physical navigation paths | Left→four slots, down from top→Settings, right→dashboard, Settings Sleep; whole wake button cycle consumed | Passed | Public actions and raw CST816 interrupt bytes with fake pins |
| Initial idle versus established loss | Sleep after 30 idle seconds before connection; keep warning awake after connected loss | Passed | Controlled clock |
| Direct connection and cleanup | Explicit discovery/selection, FFE0/FFE1 subscribe, bounded operations, no wheel writes; failed cleanup blocks replacement connection | Passed | Actual direct adapter with fake Promise-returning 2v14 GATT |
| Independent recovery | Held startup button bypasses app imports; failed startup leaves console recovery/watchdog | Passed | Production boot code in fake runtime, no device boot attempted |

`watch/app.js` owns parsing, freshness, calculations, navigation and clocks.
`watch/main.js` composes narrow adapters; its public `start(options)` returns
`core`, `transport` and `stop`. The core exposes `action(name, payload)`,
`receive(session, rawBytes)`, `tick()` and `view()`. Raw notifications and
replayed test input share its actual parser. `watch/THIRD_PARTY.md` records
pinned driver provenance and the required MIT display notice.

Battery samples occur on startup, every 30 seconds, and on a debounced charger
transition. They are independent of wheel freshness and continue with the
screen asleep. Render diagnostics expose `process.memory()`, draw count,
complete-frame receipt time, last display time, receipt-to-display maximum,
and last/maximum paint duration. The runtime harness explicitly labels its
memory values as simulated; neither source size nor the host process proves
actual P22 memory fit.

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
readability indoors/daylight and physical controls. Watch alerts, presets/horn
and durable configuration retain their own subsequent tickets and physical
checks. No firmware replacement, riding experiment, deployment, radio scan,
physical connection or horn operation was performed for this evidence.
