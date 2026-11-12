# Keep preset editing separate from wheel application

The owner's review clarified that preset settings define a local riding preset
and have no interaction with the wheel: the editor opens saved values without
requiring a connection, Save stores the whole selected preset, and Cancel
discards the draft. Wheel application occurs only when the rider chooses a
preset in the riding preset menu, preserving that menu's immediate application
and distinct submission/confirmation outcomes. This supersedes ADR 0001's
fresh-wheel editor seeding and per-adjustment wheel writes so that saving a
preset and applying it have clear, separate meanings on both laptop and watch.
