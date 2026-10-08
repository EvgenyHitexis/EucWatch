# Reproducible simulator scenarios

This is supporting software evidence for #30 and the incremental #31 acceptance
record. #31 remains open for required live Sherman L evidence and explicit owner
review. Saved/imported scenarios perform no physical operation and cannot
contain preset, horn, configuration-transfer or arbitrary backend commands.

Run `./scripts/setup.sh` once, then `./scripts/launch.sh` from the repository root.
In the separate panel, configure the simulator, give the scenario a name and
choose **Save current inputs**. This persists the complete simulator inputs and
three default steps: advance 0.2 seconds, 0.2 seconds, then 1.0 second. Save does
not start the scenario. Export produces a validated JSON file. Choose a file
and **Review file** to inspect the complete inputs and steps; neither review nor
export activates anything. **Start reviewed or saved scenario** explicitly begins
a fresh controlled simulator session; **Next scenario step** runs one step.
Imported review/start is transient; it does not silently replace the saved file.

The version-one format has exactly these fields:

| Field | Meaning |
| --- | --- |
| `version: 1` | Supported scenario schema |
| `name` | Readable name, 1–80 characters |
| `seed: 0` | Fixed specified inputs; there is no random generator |
| `clock: "controlled"` | Application-owned controlled elapsed time |
| `input: "protocol-shaped"` | Actual simulator notifications enter the parser/behavior path |
| `simulator` | Complete validated `Simulator.values`, including frame fragmentation and control failure/readback parameters |
| `steps` | 1–64 explicit telemetry/time/session actions |

Files are bounded to 32 KiB. Unknown, missing, duplicate or unsupported fields,
invalid simulator values and unsupported actions are rejected before activation.
The permitted steps are `advance` with finite `seconds` from 0 to 3600,
`simulator_emit`, `simulator_configure` with validated settings, `disconnect`
and `connect`. No extra fields are accepted on `simulator_emit`, `disconnect`
or `connect`.
Command behavior remains an explicit watch interaction outside this input
sequence. Non-default `control_*` parameters are labelled **higher-level control
injections**; their scripted failure/readback behavior is simulator evidence,
not a physical packet or wheel response measurement.

Saved scenarios use
`$XDG_DATA_HOME/eucwatch/scenarios/current.json` (normally
`~/.local/share/eucwatch/scenarios/current.json`) with validated atomic file
replacement. Browser storage is not authoritative. Backend restart loads the
definition without starting it. Load/save failures are visible; a failed save
requires reading saved content before retrying rather than assuming the disk
changed successfully. Invalid review preserves the previous definition/preview.

The runner binds its steps to its controlled simulator session. Its own explicit
disconnect/connect steps update that binding; an external mode/session change
ends the sequence without delivering later steps. It needs an explicit new
Start. Configuration-transfer mode must return to riding before a scenario can
start. Browser-delayed file reads are discarded when the input/session epoch
changes. Backend behavior, raw parsing, freshness and vibration scheduling remain
in `Application`; the scenario module does not maintain another behavior clock.

## Reproduce freshness and connection recovery

The complete importable [freshness scenario](scenarios/freshness.json) uses the
inputs and seven steps below. Review it in the panel before explicitly starting.

Save/export simulator inputs with speed 25 km/h, voltage 148.05 V and PWM 45%.
Use the exported complete `simulator` object and replace `steps` with:

```json
[
  {"action":"simulator_configure","traffic":"paused"},
  {"action":"advance","seconds":1.1},
  {"action":"simulator_configure","traffic":"normal"},
  {"action":"simulator_emit"},
  {"action":"disconnect"},
  {"action":"connect"},
  {"action":"simulator_emit"}
]
```

Review the complete file, Start, then execute its seven steps. Expected: initial
speed 25 and estimated wheel battery 100%; paused traffic plus 1.1 seconds gives
speed/PWM dashes and dim cached battery; new normal bytes restore freshness;
disconnect invalidates immediately; connect alone leaves readings unavailable;
new bytes restore them. No wheel command event occurs. The focused test runs
this sequence through the real application and checks raw-notification evidence.

The definition controls telemetry values, fragmentation, traffic and explicitly
labelled control injections. It does not restore saved alert/preset definitions
or an entire prior wheel-control state. Include the saved configuration export,
application revision and any prior synthetic setting changes in the acceptance
record when their effects matter. An exact raw traffic record remains the replay
artifact for byte-for-byte evidence. Fixed seed 0 does not establish randomized
coverage or physical behavior.

## Software evidence and pending acceptance

Run:

```sh
env PYTHONPATH=laptop experiments/laptop-feasibility/.venv/bin/python -m unittest discover -s tests -p test_scenarios.py
```

| Scenario | Expected | Observed | Provenance/artifact |
| --- | --- | --- | --- |
| Save/export/review | Complete validated input definition; no activation | Passed | `tests/test_scenarios.py`; public ScenarioLibrary with real Application |
| Explicit seven-step freshness/recovery | Actual raw parsing, stale/dim display, session invalidation, fresh recovery; no commands | Passed | Controlled Application clock and protocol-shaped notifications |
| Invalid, duplicate, oversized or command-bearing file | Refuse; retain previous review/saved definition | Passed | Public import boundary |
| Maximum 64 steps | Export remains bounded/importable | Passed | Complete simulator settings repeated through supported configure steps |
| Restart/storage failure | Load without autostart; visible failure | Passed | Real temporary file store and narrow failing store adapter |
| Replay replacement/external session interference | Explicit new controlled start; abandoned steps do not run | Passed | Real replay/session actions |
| Control failure/readback settings | Visible higher-level injection provenance | Passed | Non-default simulator control parameters |
| Browser Save/Export/Review/Start/Step | Actual frontend/backend flows and delayed-file protection | Collected by integrated browser acceptance | #30 lifecycle/browser evidence |
| Live wheel mappings, persistence, horn and owner review | Authorized measured evidence | Pending | #9 and #31; no scenario closes these checks |

For each reviewed acceptance run retain the exported scenario, expected/observed
results, saved configuration where relevant, source revision, simulator/replay/live
provenance and artifact links. Keep private captures, device identities, historical
backups and community archives out of commits and tracker updates.
