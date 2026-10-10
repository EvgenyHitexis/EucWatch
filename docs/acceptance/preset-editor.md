# Local laptop preset editor (#43, #46)

Settings → Presets opens any of the four saved definitions immediately, including
without a wheel connection. Input and dip inclusion change only one transient
draft. Name input supports case, spaces, digits, character clearing and backspace.
Top arrows select fields even with a keypad open; the `1/3` character button pages
letters independently. Empty numeric text survives page changes.
Dip inclusion remains available below the numeric keypad, preserving its entered
value. Invalid Name input is identified even when Save is tapped on another field.

Save validates the whole definition, including active input and omitted dip,
then commits one slot and returns to selection. Cancel discards the entire draft
from either a field page or keypad. Invalid input and failed local storage keep
the draft open for correction/retry. Save/Cancel replace Save slot, Back, preset
Clear and Set/Done. No editor action reads or writes wheel settings. Each editor
has an operation ID; completed/stale saves cannot overwrite a later operation.
Reviewed configuration replacement retires an open editor. Other slots and alerts
compose from current saved configuration. A successful Save still invalidates
pending/currently confirmed riding-menu requests by revision.

The riding menu alone applies saved included fields immediately, retaining its
serialization, deadlines and fresh confirmation rules. Local Save is never wheel
confirmation. Schema/default/migration evidence is in `local-configuration.md`.
Gesture changes are tracked separately in #48.

Reproduce:

```
PYTHONPATH=laptop:tests experiments/laptop-feasibility/.venv/bin/python -m unittest test_preset_editor test_presets test_backup test_http_control test_control test_live_control test_local_configuration
npm run build --prefix frontend
PYTHONPATH=laptop:tests experiments/laptop-feasibility/.venv/bin/python tests/browser_preset_editor.py
uvx ty check --python experiments/laptop-feasibility/.venv/bin/python laptop
```

Passed: public local-editor scenarios, HTTP duplicate/stale completion, controlled
live-client isolation/reconnection, storage retry, revision invalidation, all-four
actual Canvas name/numeric input, direct active-input Save, Cancel, validation and
restart. Reusable exact pointer trace, independent expectations, saved states,
zero command output and source hashes: `evidence/local-presets/editor-laptop.json`.
The same directory holds 240×240 PNGs for every slot and validation/save failure.

`evidence/preset-editor/` is retained historical #41 evidence for the superseded
wheel-owned interaction. It cannot establish #43 acceptance. Owner review, live
wheel validation, deployment and physical watch acceptance remain pending.

## Laptop gestures (#48)

Down from the dashboard opens Settings. Up returns editor → preset selection →
Settings → dashboard one level per gesture, discarding an editor exactly like
Cancel. Left/right wrap through all four fields, including active keypads and
unfinished numeric text. Right leaves only the separate riding preset menu.
Alert Settings uses upward back navigation while keeping independent Save/Cancel.

`tests/browser_preset_navigation.py` drives actual pointer down/move/up events
across former control coordinates. `evidence/local-presets/navigation-laptop.json`
contains each input with literal expected screen/page/text, observed drafts and
saved revisions. It covers all slots, both wraps, active name/numeric input,
empty validation, Save after navigation, failed Save then up, restart and zero
packets. Run it with the same Python environment as the editor flow above.
34 focused navigation/editor/lifecycle/alert checks, frontend build and Python
typechecking passed.
The built Chrome browser ownership/reload/background/lease lifecycle flow also
passed (`tests/browser_lifecycle.py`; current output `.test-output/lifecycle.json`).
