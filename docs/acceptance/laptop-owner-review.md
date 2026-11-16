# Laptop owner review (#31)

The owner said “I like how app looks” on 2026-10-10. This records visual approval;
the complete behavioral review below is still pending. Automated results and
remaining live evidence are in [the acceptance register](laptop.md).

**Walkthrough paused at the owner's request during R4.** The owner rejected the
space used by on-screen hints and the small touch areas. The resulting
[touch layout revision](watch-touch-layout.md) requires a new visual review;
the observations below describe the previous layout. R4 only reached the
[missing-threshold Save check](evidence/laptop-31/owner-review/r4-partial.json)
and has not passed.

Review progress: **R1–R3 observed pass** through the owner-operated simulator.
[Six supplied screenshots and the completed 7/7 backend state](evidence/laptop-31/owner-review/r1.json)
show initial readings, stale presentation, recovery, disconnect, waiting without
fresh data and final recovery. [R2 navigation and sleep](evidence/laptop-31/owner-review/r2.json)
records Settings, sleep/wake, upward return and riding-menu entry/return, with
zero command events. [R3 local preset editing](evidence/laptop-31/owner-review/r3.json)
records value OK/Cancel, whole-preset Save/Cancel, field loops, separate dip
inclusion and upward return. Road sensitivity is saved at 40; all other saved
content is unchanged and editing emitted no wheel commands. R4–R6 and overall
owner acceptance remain pending.

**Agent walkthrough, 2026-11-16 (not owner acceptance).** At the owner's request
an agent ran the revised-layout screens and R4–R6 in headless Chrome against
this review session, following the table below. [Its record](evidence/laptop-31/agent-walkthrough-2026-11-16/phase-A.json),
[relaunch check](evidence/laptop-31/agent-walkthrough-2026-11-16/phase-B.json),
24 Canvas snapshots and [driver](evidence/laptop-31/agent-walkthrough-2026-11-16/driver.py)
show every R4–R6 expectation met, with zero wheel commands. One step differs: R4
advanced 0.9 s, not 1 s (see the note after the table). The first attempt with
1 s advances stopped on a real lost-telemetry alert. The agent also found that
the missing-threshold error names the alert by its internal key (“enable pwm”)
and replaces the alert title while shown. This run does not replace the owner's
visual review of the revised layout or the owner's R4–R6 acceptance.

**Owner acceptance, 2026-11-16.** After reading the agent walkthrough above, the
owner accepted the revised touch layout and R4–R6 (“yes. i accept”). The owner
did not operate the simulator for R4–R6. The acceptance rests on that run's
record and snapshots. With R1–R3, every simulator review row is now accepted.
#69 (missing-threshold error wording) remains open, and so does the remaining
live evidence below.

## Review session

Use a separate profile so review edits preserve the owner's normal saved presets.
From the repository root, after the initial `./scripts/setup.sh`:

```sh
npm run build --prefix frontend
XDG_CONFIG_HOME="$PWD/.test-output/owner-review/config" \
XDG_DATA_HOME="$PWD/.test-output/owner-review/data" \
EUCWATCH_PORT=8766 ./scripts/launch.sh
```

Open <http://127.0.0.1:8766/>. Ctrl-C in the launching terminal stops this session.
Run the same command again to review persistence offline. It reuses this review
profile; it does not reset it. The first launch has Jump, Forest, Road and Drag.
If the agent has already started this session, use the existing page and have
the agent stop/relaunch it for R6; do not start a second copy on the same port.
If the screen sleeps while reading these instructions, press the modeled side
button once to wake it.

Use the watch-sized screen for editing, gestures, selecting presets and the side
button. The separate panel supplies simulator inputs, time, traces and files.
All values below are synthetic review inputs. Stay in simulator or replay mode
for this walkthrough; no live wheel connection is part of it.

## Walkthrough

| Review | Actions | Expected experience |
| --- | --- | --- |
| R1 — dashboard and freshness | Under Reproducible scenarios, choose `docs/acceptance/scenarios/freshness.json`, Review file, then Start reviewed or saved scenario. Run all seven Next scenario step actions. | Start shows 25 km/h, PWM 45%, estimated battery 100% and average cell 4.11 V. Step 2 shows dashes and dimmed retained wheel battery. Step 4 restores readings; step 5 disconnects; step 6 alone has no fresh readings; step 7 restores them. Watch battery stays independent. |
| R2 — navigation and sleep | Swipe down from the dashboard's top. Open Sleep screen, then press and release the side button. Swipe up to return to the dashboard. | Settings buttons are consistent and readable. The button cycle only wakes the screen. Settings returns upward; riding presets return by swiping right. |
| R3 — local presets | Down → Presets. Open each of the four slots and check its name and fields. On Road, change sensitivity from 30 to 40 and press keypad OK. Reopen it, enter 42 and Cancel. Save from the field display. Reopen Road and check 40. Make another draft change and cancel the whole draft. From preset selection, swipe up to Settings, then up to the dashboard. | OK returns to the field without saving. Entry Cancel restores the latest accepted value (40). Save persists the whole preset. Whole-draft Cancel preserves the saved definition. Horizontal swipes wrap fields only after the keypad closes; upward swipes cancel one level at a time. Dip inclusion and remembered value remain separate. Editing never applies a preset to the wheel. |
| R4 — alerts | Down → Vibration alerts. Enable PWM with no threshold and try Save. Enter 70 through the threshold keypad, Set value, then Save. Reopen Vibration alerts, toggle it off and Cancel. Reopen Vibration alerts again. Use Test vibration on each of the four alert pages, advancing simulator time by 0.9 seconds after each test. Cancel back to Settings, then swipe up to the dashboard. | Invalid Save explains the missing threshold. Saved PWM stays enabled at 70 after Cancel. The trace shows PWM: three 150 ms pulses; speed: two 150 ms pulses; battery: one 500 ms pulse; lost telemetry: one 150 ms pulse. Multi-pulse gaps are 150 ms. These are simulated traces, not physical vibration. |
| R5 — riding controls and feedback | With fresh simulator readings, swipe left from dashboard and tap Road. Advance time by 0.2 seconds twice. Press/release the side button while awake. For a failure, set Settings readback to Missing, Send simulator readings, select Road again, then advance by 0.2 seconds repeatedly until confirmation expires after 10 seconds. Restore Matching, Send simulator readings and select Road again for an explicit retry. | A single tap returns immediately to the dashboard with Applying, then Confirmed after fresh matching readings. Missing readback cannot confirm; timeout is visible. A new explicit selection can succeed. The awake button reports a simulated horn request; holding it does not repeat. There is no audible-horn claim. |
| R6 — replay and retention | End the simulator session. Load `experiments/laptop-feasibility/evidence/fixture-recording.jsonl` under Read-only replay and step its 13 events. Reload the browser; stop/relaunch when convenient. | Replay finishes at speed 0, PWM 2%, estimated battery 97%, average cell 4.09 V. Riding controls are unavailable in replay; local editing remains possible. Browser reload does not repeat commands. Relaunch is idle with saved preset/alert values, without drafts or a confirmed preset. |

For R4, stay under 1 second per advance: telemetry is fresh for less than
1.0 s and an advance emits no frames, so a 1-second advance raises a real
lost-telemetry alert between the test patterns. For R3, keypad Clear removes
characters; it does not delete a preset. For R5,
advancing once by 10 seconds would also make telemetry stale: use short advances
so the missing-settings timeout can be reviewed with fresh telemetry. The
non-default Missing setting is a labelled higher-level simulator injection.

Report the row IDs accepted and any confusing or incorrect behavior. Acceptance
must come from the owner; the automated run does not fill in this response.

## Remaining live evidence

Existing observations are reusable: Sherman L 006.0.10 single-setting
30→31→30 sensitivity, 25→26→25 assist and 10→11→10 dip roundtrips, plus changed
sensitivity power-cycle persistence. The owner's report that other apps change
these settings during riding remains accepted planning evidence.

The following remain incomplete under [#9](https://github.com/EvgenyHitexis/EucWatch/issues/9)
and [#31](https://github.com/EvgenyHitexis/EucWatch/issues/31):

- Current application telemetry/cadence and reconnect observations, with exact
  application/wheel versions and private recording hashes.
- Included setting ranges and owner app-version provenance; full application
  preset submission and fresh all-field confirmation, including partial changes
  and disconnect outcomes.
- Changed assist and dip persistence through owner-operated power cycles.
- Our implementation's behavior during riding.
- Audible horn variant, result, latency, duration, repeated presses and alarm
  coexistence. Horn work remains explicitly deferred.

Each physical session needs a concrete bounded procedure and owner readiness;
deferred horn tests, new riding experiments and watch deployment need separate
authorization. Successful simulator review does not complete these rows or
authorize installation. Physical laptop suspend testing remains omitted by the
owner's earlier decision.
