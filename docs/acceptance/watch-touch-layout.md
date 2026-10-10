# Watch touch layout revision

The owner stopped the #31 walkthrough during R4 because instruction hints took
too much screen space and the spacing and touch areas would be difficult on the
small watch. The owner explicitly confirmed: “Yes—remove those hints”.

The laptop Canvas and production watch now omit on-screen gesture instructions,
“Tap to apply”, “tap to switch” and preset editing hints. Gesture help remains
outside the simulated watch and in accessibility labels. Validation, disabled
states, connection status and operation results remain visible.

The 240×240 layouts use these touch areas:

| Control | Dimensions in display pixels |
| --- | --- |
| Laptop Settings rows | 216×56 |
| Watch Settings rows, including its Connect wheel row | 216×44 |
| Preset selection rows | 216×44 |
| Preset field value | 216×112; dip value 216×60 with a separate 216×44 inclusion control |
| Save, Cancel and OK | 104×40 |
| Alert enable and Test vibration | 216×40 |
| Alert threshold / decrement / increment | 104×40 / 48×40 / 48×40 |
| Numeric keypad keys | 68×32 |
| Name keypad keys / utility keys | 48×32 / 40×32 |

Names retain the existing three character pages, now arranged in four columns
so the case, Space, Clear, backspace and page controls can be taller. Dip
inclusion remains reachable during numeric entry beside the entered value.
Rendered buttons and hit testing use the same rectangles; the gaps between
buttons do not trigger an adjacent action.

Local draft and value-entry semantics, saved defaults, gestures, alert patterns
and wheel command behavior are unchanged. The native riding menu keeps its
per-field result area after an attempt, using its compact grid when those
results are present. In the ordinary menu, preset targets are taller.

## Verification and owner review

The [validation manifest](evidence/touch-layout/validation.json) records 160
Python tests, the frontend build, six browser flows, launcher shutdown/relaunch
and thirteen native watch suites, with scoped follow-up runs after review.
Renderings include [Settings](evidence/touch-layout/settings.png),
[alerts](evidence/touch-layout/alerts.png), the
[name keypad](evidence/touch-layout/name-entry.png) and
[invalid dip input](evidence/touch-layout/invalid-dip.png). Browser pointer journeys are
replayed through the native watch touch, rendering and Storage runtime.
Boundary taps exercise the enlarged value and completion controls, and gaps
between completion buttons preserve the draft. These checks establish software
behavior; physical finger comfort remains unreviewed.

Native text fitting uses the actual font width from
[`Graphics.stringWidth`](https://www.espruino.com/Reference#l_Graphics_stringWidth).
The runtime boundary uses synthetic variable-width glyph measurements to verify
that wide names fit their slot row and value button. Invalid percentage entry
shows the complete 0–100 whole-number constraint above a separate value band.

The owner walkthrough is paused. R1–R3 observations retain their original scope
and appearance; they do not approve this layout revision. R4 stopped after the
missing-threshold Save check, and R4–R6 plus overall owner acceptance remain
incomplete. No watch installation or physical wheel operation was performed.

## Standards

No documented-rule or ADR violations. The reviewer suggested sharing riding-menu
rectangles between rendering and hit testing and renaming the boolean `name` to
`isNameEntry`. Both suggestions were implemented and rechecked; no remaining
material findings.

## Spec

The reviewer found two P2 readability issues: native labels used a character-count
estimate that could overflow for wide names, and validation text could overlap
the entered value or omit the percentage range. Both were reproduced, corrected
and rechecked. The review found no scope creep or remaining material findings.

Final review: Standards — zero unresolved findings; Spec — zero unresolved findings.
