# Edit four local presets against current wheel settings

Status: the editor's fresh-wheel seeding and immediate adjustment writes are
superseded by [ADR 0002](0002-local-preset-editing.md). The historical decision
below explains the previous implementation. Four fixed slots, independent local
configuration and immediate application from the riding preset menu remain.

The laptop application stages the production watch experience, and the watch operates independently during riding. Each environment retains exactly four named preset slots and its own alert preferences; current riding settings belong to the wheel and may also be changed through another application. The owner confirmed this correction as the next implementation scope on 2026-10-09, following the [resolved preset-editor decision](https://github.com/EvgenyHitexis/EucWatch/issues/39#issuecomment-6082478274) and [amended specification](https://github.com/EvgenyHitexis/EucWatch/issues/17).

Opening a selected slot's editor waits for fresh settings from the current wheel session. Each completed riding-value adjustment writes directly to the wheel and updates only that slot, while submission and wheel confirmation remain distinct. Slot names, clearing, optional-field inclusion and watch vibration preferences are local. Existing one-tap preset application, durable local configuration and bounded command outcomes remain required; cancelling input cannot undo a submitted command.

This replaces laptop-only definition editing and laptop/watch configuration transfer, including shared-base conflict reconciliation. Keeping those workflows would make the laptop a configuration authority rather than a staging prototype and would leave the watch dependent on a separate editor. The laptop watch-sized editor and offline watch implementation must establish the corrected behavior before the relevant acceptance milestones; their results do not establish live wheel or actual-watch acceptance.
