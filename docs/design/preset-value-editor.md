# Preset value editor completion

Status: confirmed by the owner, accepting all three recommended answers with
"yours". Interview complete. Not implemented.

## Owner feedback

During laptop review, the owner wanted to finish entering a name or percentage,
return to the preset editor, edit the other values, then save the whole preset.
The current keypad offers whole-editor Save/Cancel. Save persists the preset and
returns to preset selection; horizontal navigation keeps keypad entry active.
That interaction does not provide the requested way to finish one value's entry.

The requested revision gives the value-entry screen OK and Cancel, while keeping
Save for the whole preset. It revises the "no separate Set/Done" decision in
[the previous interaction specification](preset-editor-interaction.md).
[ADR 0002](../adr/0002-local-preset-editing.md) still applies: editing remains
local and only the riding preset menu applies saved settings to the wheel.

## Confirmed interaction

The preset editor and the preset value editor have distinct completion controls.

| View | Accept action | Cancel action |
| --- | --- | --- |
| Preset value editor: name or numeric keypad | OK validates this entry, accepts it into the unsaved preset draft, closes the keypad and returns to the same field's display | Cancel discards only the current entry, restores that field's value from when entry opened, closes the keypad and returns to the same field's display |
| Preset editor: field display | Save validates and persists the whole preset draft, then returns to preset selection | Cancel discards the whole preset draft and returns to preset selection |

- The keypad displays OK and Cancel. Whole-preset Save is available after the
  keypad closes; OK never writes saved configuration or a wheel-setting packet.
- A value's starting point is its current value in the draft, including a value
  accepted earlier in the same editing session. Cancelling a later entry must
  preserve that earlier accepted value and edits to other fields.
- Invalid name or percentage input keeps the keypad open with its text and a
  visible reason. Existing name and whole-percentage 0–100 validation applies.
- Swipe up from the keypad performs value-entry Cancel. Swipe up from a field
  display performs whole-preset Cancel. Higher-level upward navigation remains
  preset selection → Settings → riding dashboard.
- While the keypad is open, left/right swipes do not change fields or accept or
  discard text. After OK/Cancel closes it, left/right navigation wraps through
  Name, Pedal sensitivity, Dynamic assist and Pedal dip compensation as before.
- These meanings are identical on laptop and watch. Dip value and inclusion
  remain separate; local editing, defaults, migration, saved preferences,
  persistence recovery and riding-menu application retain their existing scope.
- A failed whole-preset Save retains the draft for retry and preserves the last
  valid saved configuration. Completed or stale entry actions cannot affect a
  later entry or preset draft.

## Acceptance examples for implementation

Starting from saved Road with sensitivity 30:

1. Enter name Commute and press OK. The Name field displays Commute; saved
   configuration still says Road. No wheel-setting packet is emitted.
2. Enter sensitivity 40 and press keypad Cancel. Sensitivity remains 30 in the
   draft, and the accepted name Commute remains in the draft.
3. Enter sensitivity 40 and press OK. Reopen sensitivity, enter 42 and Cancel.
   The draft retains 40, not the originally saved 30.
4. Press whole-preset Save. Commute and sensitivity 40 persist together; the
   other three presets and alert preferences are unchanged.
5. In a separate draft, accept several field edits and press whole-preset Cancel.
   None of that draft's edits persist.
6. Enter an empty name or invalid percentage and press OK. Entry stays open with
   a reason; Cancel still restores the prior draft value.
7. Swipe left/right during entry. Field and text remain unchanged. Swipe up
   closes entry and discards only that entry; a second upward swipe discards
   the preset draft and returns to preset selection.

Exercise these through the actual built laptop UI/backend and matching native
watch touch/render/Storage runtime. Earlier #43 evidence proves the previous
keypad interaction and does not establish acceptance of this follow-up.

## Decision relationship

This supersedes #43's whole-editor completion buttons inside active input and
field navigation while a keypad is open. ADR 0002's local editing and separate
wheel application remain valid. The change is an interaction revision; no new
architectural decision is needed. Hardware and owner acceptance remain separate.
