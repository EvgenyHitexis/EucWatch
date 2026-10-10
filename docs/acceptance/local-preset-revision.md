# Local preset revision acceptance (#43, #44–#50)

This account covers offline software acceptance for the agreed local preset
revision. The initial review baseline is `398fd51`. Existing research files and
private owner material were left outside these implementation commits. Hardware
and owner acceptance remain pending; no physical wheel operation, audible horn,
watch deployment or firmware change was performed.

| Slice | Reviewable commit | Result and evidence |
| --- | --- | --- |
| #44 laptop defaults/migration | `fa6bb44` | Passed: [literal shared inputs](scenarios/local-presets.json), [built laptop defaults and exact packets](evidence/local-presets/defaults-laptop.json), `tests/test_preset_defaults.py` |
| #45 watch defaults/migration | `1e67798` | Passed: [native load, lists, Storage recovery, exact GATT chunks](../../watch/evidence/local-presets/defaults.json) |
| #46 laptop local editor | `f873517` | Passed: [real pointer input trace, expected definitions and saved outcomes](evidence/local-presets/editor-laptop.json), `tests/test_preset_editor.py`, HTTP and controlled-client checks |
| #47 watch local editor | `4dc0a8c` | Passed: [same trace through production main/touch/Graphics/Storage](../../watch/evidence/local-presets/editor.json) |
| #48 laptop gestures | `501e742` | Passed: [ordered pointer inputs and literal screen/page/text expectations](evidence/local-presets/navigation-laptop.json) |
| #49 watch gestures | `3fd02dd` | Passed: [same trace through native CST816 and rendered controls](../../watch/evidence/local-presets/navigation.json) |
| #50 composed acceptance | Current acceptance commit | Full check and bundle outcome recorded below; hardware gates remain separate |

Expected saved definitions and packets are literal fixture values, not values
computed by the production encoder or one implementation used as the other's
oracle. Both actual interfaces edit all four slots with case/spaces/digits,
character clearing/backspace and active-keypad Save. Selection/editor Clear,
Save slot, Back and Set/Done targets are absent. Up discards complete drafts;
horizontal swipes retain incomplete input and wrap both ends, even crossing
former completion coordinates. The separate riding menu retains right-to-return.

| Acceptance area | Observed software outcome | Reproduction/artifact |
| --- | --- | --- |
| Defaults and migration | All four exact defaults, mixed custom/empty legacy slots, present zero/nonzero dip and absent dip, independent alerts; repeated startup does not reset content/revision | Shared `local-presets.json`; laptop defaults tests; watch defaults JSON |
| Saved dip vs application | Omitted Road/Drag values retained; each default emits only sensitivity/assist packets while simulator dip 83 remains unchanged; included zero/nonzero emits dip | Defaults browser/native tests and packet/chunk artifacts |
| Local draft isolation | All editor operations emit zero setting packets; changing/corrupt/old-session readings and reconnect cannot seed or erase active input | [shared raw-frame inputs](scenarios/local-editor-frames.json), [laptop observations](evidence/local-presets/raw-frames-laptop.json), native editor fault results |
| Save, Cancel, validation | Whole selected slot commits once; active text included; other slots/preferences unchanged; invalid text and failed storage retain draft; Cancel/up do not save | Editor and gesture traces, adjacent PNG/SVG renderings |
| Durability/recovery | First-save defaults and sole legacy backup remain recoverable; refused staging, partial activation and native JSON precision loss cannot publish invalid content; retry/restart retain valid definitions | Laptop file adapter tests; native Storage effects in defaults/editor JSON |
| Stale operations | Completed/stale IDs refused; import/reload and owner document replacement retire editor; duplicate HTTP requests cannot repeat Save; no draft/command/confirmation replay after restart | HTTP/editor tests, browser lifecycle result |
| Immediate application | Saved included values only; one active operation, no tap queue, existing eligibility, 5-second submission/10-second confirmation bounds, two matching fresh current-session frames, explicit partial/unknown/failure outcomes, revision stops unsent continuation | `test_control`, `test_live_control`, `watch/tests/control.cjs`, native editor pending-write test and complete browser flow |
| Independent behavior | Alerts, dashboard freshness, recording/read-only replay, owner lease, controlled horn eligibility, wake-only cycles and prolonged-hold recovery retained; configuration transfer remains withdrawn | Full repository regression entry point, lifecycle/browser results |
| Versioned bundle | Complete bundle build/verify/synthetic stage/activation, versioned imports, fresh/migrated/custom startup, held-button and absent-main recovery | [bundle manifest/rehearsal](../../watch/evidence/local-presets/bundle.json); complete bundle under `.test-output/watch-preset-editor/<version>/` |
| Hardware/owner | Pending, not performed | #9 live wheel; #31 laptop owner/live review; #37 deployment/recovery gate; #38 actual display/input/vibration, memory fit, flash/BLE and owner acceptance |

## Reproduction

From the repository root, after `./scripts/setup.sh`:

```sh
EUCWATCH_BROWSER_CHECKS=1 ./scripts/check.sh
uvx ty check --python experiments/laptop-feasibility/.venv/bin/python laptop
node watch/tests/preset-editor-bundle.cjs
```

The check entry point runs Python application/HTTP/file tests, frontend
TypeScript/Vite build, five actual Chrome flows, and twelve watch suites. Browser
traces run before native replay so source/trace hashes refer to the same run.
Only external time, file/flash, BLE and physical-input boundaries are controlled;
application/parser/store/transport/render modules are real production code.
Native Graphics SVGs reproduce drawing operations with host fonts, not measured
physical display output. Flash atomicity, physical memory fit and hardware timing
are not inferred from VM results.

Older `evidence/preset-editor/` and `watch/evidence/preset-editor/` artifacts remain
unchanged as #41/#42 historical evidence. ADR 0001 remains historical; #43 and ADR
0002 govern this revision. Milestones #31 and #38 now state the local-editor
expectations and retain all owner/hardware gates. Parent #43/#17 and deployment
milestones were not closed or otherwise changed.

## Final validation

`EUCWATCH_BROWSER_CHECKS=1 ./scripts/check.sh` passed: **156 Python tests,
TypeScript/Vite build, five Chrome flows and twelve watch suites**.
Python typechecking passed separately. The complete content-versioned watch
bundle is **`b4bd9077`**; its manifest, synthetic activation/readback and compatible
startup/recovery results are retained in the bundle artifact linked above.

[Validation and source fingerprints](evidence/local-presets/validation.json) and
[full check output](evidence/local-presets/full-check.log) retain exact commands
and outcomes. The `regression-*.json` files alongside them retain current browser,
backup, recording, control and lifecycle observations; matching native regression
outputs live in `watch/evidence/local-presets/`. Public ticket snapshots are in
`evidence/local-presets/specifications/`. Earlier failed checks and their resolved
causes are recorded in validation JSON; no failed application check is counted
as a pass. Physical/owner checks remain explicitly pending in the matrix.
