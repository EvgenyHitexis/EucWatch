# Local watch preset editor (#43, #47)

Production main, CST816 touch, controls, Graphics, parser/transport and native
Storage implement the local laptop editor contract. Each saved slot opens
immediately without a wheel. Whole-editor Save/Cancel work from name and numeric
keypads. Top field buttons retain input; the character-page button remains
independent. Dip value and inclusion are separate. No preset Clear, editor Back,
Save slot or per-field Set/Done target remains.

Only Save publishes a validated stored replacement. Failure retains the prior
active configuration and complete draft. Retry is local. Operation IDs reject
stale/duplicate completion; configuration reload retires an editor. Incoming
settings and reconnects cannot replace draft input. Committed revisions invalidate
riding-menu requests and stop unsent native writes as before.

Passed reproduction commands:

```
node watch/tests/preset-editor.cjs
node watch/tests/preset-editor-runtime.cjs
node watch/tests/preset-defaults.cjs
node watch/tests/control.cjs
node watch/tests/runtime.cjs
node watch/tests/alerts-runtime.cjs
node watch/tests/local-configuration.cjs
```

`watch/evidence/local-presets/editor.json` retains the exact laptop input trace,
expected saved definitions, per-event views, Graphics renderings, packets (none),
native Storage effects, interrupted-write/recovery outcomes and source hashes.
SVG renderings are adjacent. The real production modules run under the existing
Node VM harness; only time, physical inputs, BLE and flash are controlled.

`watch/evidence/preset-editor/` remains historical #42 evidence for the previous
wheel-owned interaction and does not establish #43 acceptance. Matching revised
gestures are the #49 slice. Device display/input/vibration, memory fit, physical
flash guarantees, live wheel controls, deployment and owner acceptance remain
pending under #9/#31/#37/#38.
