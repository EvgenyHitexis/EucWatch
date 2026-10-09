# Watch preset editor (#42)

The dedicated P22 Espruino 2v14 application now carries the laptop interaction
from #41 into **Settings → Presets**. Four fixed named slots can be opened,
renamed, edited, cleared and recreated using the watch's touch handler. The
riding preset menu still applies a configured slot immediately. This document
records offline software verification; deployment and actual-watch acceptance
remain separate under #31/#37–#38 and live wheel controls under #9.

Opening resets the frame assembler and waits up to five seconds for a newly
received complete CRC-valid settings frame in the current connected session.
All three riding percentages must be valid. Saved riding values, cached settings,
speed-only telemetry, corrupt/incomplete frames and old-session notifications
cannot seed the editor. Opening sends no setting packet. A failed read requires
explicit reopening; reconnect never restores an editor or replays a command.

The four pages and touch coordinates match the staged laptop editor. Name input
has three pages of letters/digits, lowercase, spaces, Clear and backspace, with
a 24-character limit. Numeric input supports 0–100 whole percentages, Clear,
backspace, Set and Cancel. A right swipe cancels unfinished input or the clear
dialog before leaving the editor. Clear requires a separate confirmation and
preserves the slot identity/name. Newly created slots omit dip; saved slots
retain their inclusion and receive newly read values. Include copies observed
dip locally, while Omit leaves the wheel unchanged.

Completing a riding field validates and saves only the selected slot, then
submits exactly that field through the existing serialized, session-bound native
GATT writer. Requested, submitted and latest wheel values remain distinct.
Two matching settings frames after submission completion confirm the field;
they do not label the whole preset confirmed. Freshness, divergence and session
replacement remove current confirmation while retaining the terminal outcome.
Submission has the existing five-second bound and native chunk deadline;
confirmation has a ten-second bound. Pending adjustments discard extra input.
Leaving stops unsent continuation and cannot undo submitted wheel changes.

Names, clear/omit metadata, Save slot and alert preferences emit no riding
packet. A failed local save leaves the last valid active configuration intact,
keeps the edit in the open editor and reports that wheel changes are not undone.
Retry save persists locally without reissuing the wheel command. Native Storage
still stages/read-verifies the complete schema-1 content and preserves a
validated previous-good copy before replacement. Restart and compatible bundle
startup restore definitions/preferences, never commands or wheel confirmation.

## Reproduce

Run `./scripts/check.sh` for the complete suite, or these focused offline checks:

```sh
node watch/tests/preset-editor.cjs
node watch/tests/preset-editor-runtime.cjs
node watch/tests/preset-editor-bundle.cjs
```

The core suite uses the public application action/raw-notification boundary.
The runtime suite executes production `main`, CST816 interrupt decoding,
Graphics rendering, direct transport and native Storage with controlled pins,
timers, BLE promises and flash. It replays all 249 events from the retained
[laptop action/frame scenario](evidence/preset-editor/preset-editor-browser.json),
including all four editors and external seed values. Packets, selected-slot
definitions, confirmation, local-only actions and restart outcomes match.

[Runtime evidence](../../watch/evidence/preset-editor/runtime.json) retains the
source hashes, original inputs, public state transitions, expected/observed
slot definitions, native BLE chunks and Storage write hashes. Additional native
scenarios cover failed second chunks, hung writes, cancellation, disconnect,
late settlement, reconnect without replay, missing/mismatching confirmation,
failed staging and interrupted active saves. Core scenarios additionally reject
corrupt/partial/cached/old-session input and cover staleness and read deadlines.

Graphics operation renderings cover all three riding pages of each slot:
[slot 1](../../watch/evidence/preset-editor/slot-1-field-1.svg),
[slot 2](../../watch/evidence/preset-editor/slot-2-field-1.svg),
[slot 3](../../watch/evidence/preset-editor/slot-3-field-1.svg), and
[slot 4](../../watch/evidence/preset-editor/slot-4-field-1.svg), with `field-2` and
`field-3` alongside them. Failure views include
[unavailable settings](../../watch/evidence/preset-editor/unavailable-readback.svg)
and [failed save after wheel confirmation](../../watch/evidence/preset-editor/save-failure-after-wheel-change.svg).
These SVGs replay actual Graphics calls using host fonts. They do not establish
Espruino glyph dimensions, physical pixels, touch calibration or readability.
The runtime's framebuffer remains 7,200 bytes; its memory figures are simulated.

The bundle suite creates a content-versioned complete bundle under
`.test-output/watch-preset-editor/<version>/`, verifies its manifest and
rehearses staging/activation through the existing synthetic installer. It then
executes the retained versioned recovery startup and modules from fake native
Storage, exercises the editor, preserves existing configuration across startup,
and verifies held-button/failed-main recovery. [Bundle evidence](../../watch/evidence/preset-editor/bundle.json)
records exact hashes, rewritten module imports, simulated writes and pointer-last
activation. Use the existing [installation procedure](installation.md) for later
authorized deployment; the offline rehearsal changes no device.

## Remaining acceptance

Actual display/input/vibration, memory fit, live wheel controls, physical
flash/recovery behavior, installation and owner acceptance remain **pending**.
No radio scan, physical wheel connection, setting command, horn, motor operation,
watch deployment or firmware replacement was performed for this evidence.
