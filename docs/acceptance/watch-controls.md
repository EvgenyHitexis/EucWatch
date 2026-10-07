# Offline watch preset and horn evidence (#34)

Run from the repository root:

```sh
node watch/tests/control.cjs
node watch/tests/offline.cjs
node watch/tests/runtime.cjs
node watch/tests/alerts.cjs
node watch/tests/alerts-runtime.cjs
node watch/tests/compare-alerts.cjs
```

The control harness executes the production ES5 App, parser, preset/horn behavior,
touch targets, renderer and direct BLE adapter. It injects a clock, ordinary
configuration store, command output and fake NRF/GATT objects. It never discovers
or connects a real device. The Python comparison uses the existing installed
`experiments/laptop-feasibility/.venv/bin/python` and actual laptop Application.
[Machine-readable traces](../../watch/evidence/control.json) retain identical
raw/action inputs, expected laptop outcomes, observed watch outcomes and native
adapter chunk bytes. The [offline watch procedure](watch.md) retains display,
hardware-adapter and recovery provenance.

| Scenario | Expected | Observed |
| --- | --- | --- |
| Moving one-tap preset | Four fixed touch targets; unconfigured targets disabled; configured tap returns dashboard with Applying; extra taps discarded | Actual shared hit target and renderer assertions passed at synthetic 25 km/h; two serialized writes when dip omitted |
| All-field confirmation | Two consecutive fresh subtype-8 CRC-valid frames after complete submission; included dip also required | Passed; cached/pre-write and alternating individual matches did not confirm; optional dip confirmed only after two complete matching frames |
| Failure and time limits | Individual post-write two-frame evidence retained; unknown/mismatched fields explicit; terminal result stable; fresh retry explicit | Passed partial rejection, 5-second total submission and 10-second post-submission confirmation limits, staleness, session change, late receipts, divergence and definition clearing; preset menu renders each retained actual/requested field outcome and later fresh differing actual values |
| Physical-button model | Sleeping press/release consumed; once per eligible awake press; no held repetition or queued unavailable press | Passed, including a consumed wake cycle held across session replacement; stale, pending preset confirmation and recovery blocked with reasons |
| Direct writer | Same subscribed FFE1 session; <=20-byte serial chunks; guard every continuation; failure stops unsent work | Passed property rejection, native partial-chunk failure, fresh-telemetry bounded hang, retained native writer ownership until settlement and ignored late completion |
| Laptop/watch comparison | Same outcomes through actual applications using identical raw/control/time traces | Success, partial submission rejection and stale/late receipt traces matched speed, pending/status, each field and confirmed name |

Setting packets use the accepted laptop command mappings: `LdAp` command 15,
31 and 33, value offsets 10, 26 and 28, with big-endian CRC32. Readback comes
only from complete validated subtype-8 frames at offsets 50, 66 and 68. The
sanitized base fixture is WheelLog's Sherman L 006.0.03 vector; settings/movement
are synthetic modifications with recomputed CRC, not owner captures. Source,
owner one-point roundtrip limits and verification decisions are retained in
[telemetry fixture provenance](../research/sherman-l-protocol.md) and
[issues #6](https://github.com/EvgenyHitexis/EucWatch/issues/6),
[#8](https://github.com/EvgenyHitexis/EucWatch/issues/8).

The horn packet `4c6b41700e0080808001ca87e66f` is the WheelLog `LkAp` candidate
from [issue #7 horn research](https://github.com/EvgenyHitexis/EucWatch/issues/7)
and the existing laptop `laptop/eucwatch/horn.py` command fixture. The application
reports “Horn request sent” after transport receipt, with two-second feedback.
It establishes no audible outcome, duration, repeat behavior or stop command.
It adds no vibration pattern.

The adapter targets the installed Espruino 2v14 API, rather than browser GATT
options. [RELEASE_2V14 writeValue](https://github.com/espruino/Espruino/blob/RELEASE_2V14/libs/bluetooth/jswrap_bluetooth.c#L3911-L3957)
takes data and returns a Promise. The
[nRF implementation](https://github.com/espruino/Espruino/blob/RELEASE_2V14/targets/nrf5x/bluetooth.c#L3275-L3305)
chooses write-command behavior from the discovered characteristic's
`properties.writeWithoutResponse`; the adapter requires it, calls
`writeValue(Uint8Array)` and serializes 20-byte chunks. It does not invent a
response-options argument, initialization command or MTU change. A whole preset
has a five-second submission budget; each native operation is bounded by three
seconds and that remaining budget. An unresolved native operation retains its
writer even after application failure, preventing overlapping retries.

These are reproducible software results. Actual P22 touch/button recognition,
font fit/readability, memory/timing, live multi-setting behavior, audible horn
and long-hold recovery coexistence require laptop acceptance, authorized staged
deployment and owner evidence. No watch was deployed and no horn was sounded.
[#9](https://github.com/EvgenyHitexis/EucWatch/issues/9) and
[#31](https://github.com/EvgenyHitexis/EucWatch/issues/31) remain open.
