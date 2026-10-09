# Laptop watch-sized preset editor (#41)

This implements the four-slot wheel-owned editor resolved in #39, on the laptop
staging interface. It establishes software behavior for the later watch
implementation. Live wheel evidence and owner review remain **pending**;
no physical wheel command or watch deployment was performed.

Launch with `./scripts/launch.sh`. Start the simulator, swipe down from the top
of the dashboard, then tap **Presets** in Settings. All four fixed slots have
an edit area and a separate Clear area. Tap a slot to request fresh wheel
settings. Opening sends no setting packet. The read has a five-second bound and
only a newly assembled complete CRC-valid current-session settings frame with
all three percentages available can seed it. Old saved values, cached readback,
speed-only frames, corruption, incomplete fields and old sessions cannot open
an editable screen. Reopen explicitly after an unavailable result or reconnect.

The editor has four pages: Name, Pedal sensitivity, Dynamic assist and Pedal dip
compensation. Tap the top left/right arrows to select a page. Tap its value to
open the text or numeric keypad. Names support paged letters and digits,
lowercase, spaces, clearing and backspace, up to 24 characters. Numeric entry
supports digits, clearing and backspace; **Set** completes a whole percentage
from 0 to 100. **Cancel** or a right swipe discards unfinished keypad input.
An invalid value is refused without a command. All controls stay inside the
240×240 interface; the desktop definition editor has been removed.

Set on a riding field submits exactly that field's evidenced packet through the
existing serialized control adapter and saves the selected slot's definition.
Further edits are discarded while that operation is pending. Requested values,
submission completion and current wheel readings/confirmation are separate.
Confirmation requires two consecutive matching valid frames after submission.
Submission is bounded to five seconds and confirmation to ten seconds after
submission completes. Transport failure, mismatch, missing readback, staleness,
session replacement and partial/unknown outcomes retain explicit reasons.
A field edit confirms that field, never the entire named riding preset.
Externally changed settings or stale telemetry invalidate current confirmation;
the terminal operation result remains historical evidence.

Name edits and dip inclusion/omission are local. Dip starts omitted for new
slots and retains existing inclusion for saved slots, using current readback
when included. Inclusion copies the latest observed dip without submitting a
packet; omission leaves the wheel value unchanged. **Save slot** explicitly
creates a slot from the seed or retries local persistence; it sends no packet.
Clear from either the editor or slot list requires a separate confirmation and
retains the slot's
identity and name. Clearing and leaving cannot undo wheel changes. Leaving the
editor terminates a pending editor operation and prevents unsent continuation.
There is no automatic rollback, retry or reconnect/reload replay. The riding
menu still applies a configured slot immediately with one tap.

A storage error leaves the last valid active/saved configuration intact and
retains the edited value in the open editor. It reports that wheel changes are
not undone. After storage recovers, Retry save persists that definition without
resubmitting a wheel command. Restart restores only local definitions and
preferences, never an editor, queued command or wheel confirmation.

## Reproduction and evidence

Run the complete checks with `EUCWATCH_BROWSER_CHECKS=1 ./scripts/check.sh`.
The focused application checks use:

```sh
env PYTHONPATH=laptop:tests experiments/laptop-feasibility/.venv/bin/python -m unittest test_preset_editor test_presets test_live_control test_http_control
```

`tests/browser_preset_editor.py` is the reusable action/raw-frame flow invoked
by `tests/browser_flow.py` against the actual built frontend and HTTP backend.
The retained [browser scenario and outcomes](evidence/preset-editor/preset-editor-browser.json)
include ordered taps/swipes/frame responses, external seed values, saved
outcomes, source hashes and explicit pending hardware/owner status. Raw frame
responses traverse the real parser; the existing simulator command adapter
receives actual encoded commands. Controlled BLE tests use the real live
session and chunk writer with a fake selected client, without Bluetooth access.
Read-only recording replay remains covered by the existing replay checks.

| Scenario | Expected and observed software result | Evidence |
| --- | --- | --- |
| Open every slot after external wheel changes | Wait; seed new settings; opening emits nothing | Application tests; browser action/frame scenario |
| Cached/partial/corrupt/speed-only/old-session input | Cannot seed; bounded visible unavailable result | Application tests; unavailable rendering |
| Complete each of three riding fields in each slot | One exact field packet; selected definition updated; two fresh frames confirm | Browser scenario; controlled BLE application tests |
| Text input, numeric Cancel, local name, include/omit dip | Usable watch input; local actions emit no command | Browser scenario |
| Clear Cancel, Clear commit, recreate all four slots | Fixed identities/names; other slots unchanged | Browser scenario |
| Missing/mismatching readback, failed/hung submission | Bounded unconfirmed result; no automatic retry | Application tests |
| Disconnect during live chunk submission; replacement session | Unsent tail stopped; old input rejected; replacement sends nothing | Controlled BLE tests |
| Failed storage after a wheel change | Last valid local config retained; wheel change stays; local retry emits nothing | Application tests; failed-save rendering |
| Restart, reload and duplicate HTTP completion | Definitions survive; commands and confirmation never replay | Browser scenario; FileStore and HTTP tests |
| External divergence or stale telemetry after confirmation | Current confirmation lost; terminal result retained | Application tests |

Renderings are retained for all three riding pages of each editor:
[slot 1](evidence/preset-editor/slot-1-field-1.png),
[slot 2](evidence/preset-editor/slot-2-field-1.png),
[slot 3](evidence/preset-editor/slot-3-field-1.png),
[slot 4](evidence/preset-editor/slot-4-field-1.png), with corresponding
`field-2` and `field-3` images in the same directory. Failure renderings show
[unavailable readback](evidence/preset-editor/unavailable-readback.png) and
[failed local save after wheel change](evidence/preset-editor/save-failure-after-wheel-change.png).
These are 240×240 Canvas images, not actual-watch display acceptance. Physical
range support, setting persistence and owner review remain under #9/#31; the
production watch editor and device acceptance are subsequent work.
