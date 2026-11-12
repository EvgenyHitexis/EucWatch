# Preset editor interaction revision

Status: original interaction confirmed by the owner and implemented through
[#43](https://github.com/EvgenyHitexis/EucWatch/issues/43) and #44–#50. See the
[offline acceptance account](../acceptance/local-preset-revision.md).
The subsequently confirmed [preset value editor revision](preset-value-editor.md)
supersedes the active-keypad completion and navigation decisions below. That
follow-up is not yet implemented.

## Original #43 decisions

- Swipe down opens Settings from the riding dashboard. Swipe up returns one
  level: preset editor → preset selection → Settings → riding dashboard.
- Within the preset editor, swipe left advances through Name, Pedal sensitivity,
  Dynamic assist and Pedal dip compensation. Swipe right goes backward. Both
  directions wrap at the ends.
- The preset editor has Save and Cancel actions. Remove Save slot and the
  separate editor Clear action.
- Cancel exits the preset editor to preset selection and saves nothing.
- Save saves all settings of the selected preset. Editing one preset leaves
  the other three unchanged.
- Preset editing is entirely local and works without a wheel connection. Open
  an existing preset from its saved values; wheel changes and external wheel
  readings do not seed or modify the preset draft. Opening, typing, page changes,
  Save and Cancel emit no wheel-setting packet.
- Applying a preset to the wheel occurs only from the separate riding preset
  menu. Preserve immediate application and its bounded submission/confirmation
  behavior.
- Save and Cancel retain their whole-editor meanings while text or numeric input
  is open. There is no separate Set/Done action. Horizontal swipes navigate the
  editor fields while retaining draft input.
- Successful Save returns to preset selection.
- Swipe up from the editor discards its unsaved draft and returns to preset
  selection, just like Cancel. Other upward swipes return one level.
- Invalid input keeps the editor open with a visible reason. A local save failure
  keeps the draft available for retry and preserves the last valid saved
  configuration. These are local operations and never submit a wheel command.
- Remove Clear from the Settings preset selection list. It presents the four
  named preset slots for editing.
- Provide four configured default presets: Jump, Forest, Road and Drag. All
  initially omit dip when applied. Retain each default's dip value locally even
  while omitted, including Drag's value of 5.
- Both the laptop application and watch start with these four editable presets.
  They are initial values for custom presets, not immutable modes. Saving later
  edits replaces only that slot's local definition.
- Initialize new configuration and previously unconfigured slots from these
  defaults. Preserve already configured custom presets through restart and
  compatible updates; do not reset their names or values to defaults.

## Default presets

All values are percentages. Assist means Dynamic assist; pedal means Pedal
sensitivity. Road uses the documented owner wheel settings as fixed default
values, without reading the wheel at editor-open time.

| Slot | Name | Dynamic assist | Pedal sensitivity | Saved dip | Dip included on application |
| --- | --- | --- | --- | --- | --- |
| 1 | Jump | 0 | 0 | 0 | No |
| 2 | Forest | 0 | 70 | 0 | No |
| 3 | Road | 25 | 30 | 10 | No |
| 4 | Drag | 70 | 20 | 5 | No |

Road's values come from the 2026-10-07 `last_confirmed_settings` and restored
final readback in [retained owner evidence](../research/sherman-l-roundtrip-attempt-evidence.json).
These are documented baseline values, not a claim about the wheel's live state.

## Original interview completion

The owner confirmed the combined interaction for #43. The later value-editor
interview is recorded separately in the follow-up linked above.
Physical wheel and actual-watch acceptance remain separate.

## Historical #41/#42 behavior and decision conflict

At the original decision, the implementation wrote a completed riding adjustment
to the wheel and persisted the selected preset immediately. Save slot saved the
current draft locally and stayed in the editor; Cancel could not undo prior saved
adjustments or submitted wheel commands. Clear removed a slot's saved riding
values while preserving its identity and name, without changing the wheel.

[ADR 0002](../adr/0002-local-preset-editing.md) records the owner's correction:
local-only editing replaces both immediate persistence and wheel interaction
inside the editor. [ADR 0001](../adr/0001-wheel-owned-preset-editing.md) remains
as a historical record of the previous behavior.

The revised interaction must be carried through both the laptop staging
application and dedicated watch application, with matching reusable scenarios.
Existing offline results remain evidence for the previous interaction and do
not establish acceptance of this revision.
