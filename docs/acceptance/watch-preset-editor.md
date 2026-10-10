# Local watch preset editor (#43, #47)

The historical #43 keypad behavior below is superseded by value completion.
The native watch now matches the laptop: OK validates one entry into the unsaved
draft; Cancel or swipe up discards only that entry. The field display retains
whole-preset Save/Cancel. Horizontal navigation waits until the keypad closes.
Invalid text remains visible with its reason, and entry identities reject stale
actions even within the same preset draft. Dip inclusion remains independent.

Run `node watch/tests/preset-value-editor.cjs` after the laptop value-editor flow,
plus the editor/runtime/navigation checks below. The new native test replays
every laptop pointer event through production CST816 touch, main, controls,
Graphics and Storage and compares the field, entry, draft and saved configuration.
It also asserts no Storage writes during entry, visible OK/Cancel and validation,
zero BLE writes, stale-action rejection, failed Save retry and restart.
Evidence is in `watch/evidence/preset-values/`, with the matching laptop traces in
`docs/acceptance/evidence/preset-values/`. Previous #43 artifacts are retained as
historical evidence. Hardware, physical flash/memory fit and owner acceptance
remain pending; these checks use the native runtime with simulated hardware.

## Historical #43 acceptance

Production main, CST816 touch, controls, Graphics, parser/transport and native
Storage implement the local laptop editor contract. Each saved slot opens
immediately without a wheel. Whole-editor Save/Cancel work from name and numeric
keypads. Top field buttons retain input; the character-page button remains
independent. Dip value and inclusion are separate; inclusion stays reachable below
the active dip keypad. Invalid Name input is identified from any field. No preset Clear, editor Back,
Save slot or per-field Set/Done target remains.

Only Save publishes a validated stored replacement. Failure retains the prior
saved configuration and complete draft. An unverified active Storage copy is
retired so restart uses the previous-good backup, including when a failed write
leaves valid but incorrect content. Retry is local. Operation IDs reject
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

## Native gesture parity (#49)

CST816 upward gestures now return editor → selection → Settings → dashboard.
Left/right wrap all fields during either field display or active keypad input.
The character-page button does not consume horizontal field gestures. Up cancels
all unsaved fields from normal, validation and storage-failure views. Settings
and independent alert/threshold back navigation use up; riding presets retain
right-to-dashboard return.

`node watch/tests/preset-navigation.cjs` replays the exact laptop pointer trace
as native interrupts, with independently specified screens/pages/input and final
saved values. `watch/evidence/local-presets/navigation.json` retains every event,
Graphics operation, draft, revision, Storage effect, source hash and zero packets.
Native editor/default/control/runtime/alert/local-configuration regressions,
syntax checks, frontend and Python typechecks passed. Actual touch calibration,
physical display and memory fit remain pending.
