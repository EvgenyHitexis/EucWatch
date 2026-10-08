# Sherman L riding application

The Ubuntu laptop application establishes the watch experience using a 240×240
Canvas interface and a separate scenario/editor panel. Python owns telemetry,
behavior and time. Normal launch is idle and performs no Bluetooth operations.

Install Python 3.12, uv, Node/npm and a browser, then run:

```bash
./scripts/setup.sh
./scripts/launch.sh
```

The launcher opens the browser after readiness and stops the backend on Ctrl-C.
After setup, the same launch command works offline; it uses the exercised locked
Python environment and already-built frontend assets. Set `EUCWATCH_NO_BROWSER=1`
for terminal-only operation and `EUCWATCH_PORT=8766` to choose another loopback port.
Do not run as root. Simulator controls send protocol-shaped traffic through the
same parser used by the application. Synthetic results establish software behavior.

Sessions are recorded before decoding into versioned JSONL in
`$XDG_DATA_HOME/eucwatch/recordings` (default `~/.local/share/eucwatch/recordings`).
Storage/queue failures are visible and stop capture. Download deliberately from
the panel; keep private live recordings off GitHub. Import a recording and step
through it in read-only replay; retained outgoing events never send commands.
The sanitized source fixture in `experiments/laptop-feasibility/evidence/` is
safe to use for reproducible parser/replay checks.

Run checks with `./scripts/check.sh`. Acceptance scenarios and evidence are in
[docs/acceptance/laptop.md](docs/acceptance/laptop.md). Physical acceptance remains
separate: no live horn, riding experiment or watch deployment is authorized here.

The panel includes four saved presets, alert editing, configuration backup and
review, reusable controlled scenarios, and explicit wheel/watch discovery.
Saved configuration uses the XDG configuration directory. Configuration transfer
starts with the wheel disconnected and requires explicit review and Transfer;
uncertain activation requires saved-content readback. The simulated watch and
each selected real watch retain separate reconciliation histories. Live wheel
control requires a fresh selected session; replay always remains read-only.

The original P22 Espruino 2v14 application lives in [watch/](watch/).
Its 240×240 monochrome interface, bounded control and alert behavior, native
Storage adapter and Nordic UART endpoint are exercised offline. Follow
[installation preparation](docs/acceptance/installation.md) to build and rehearse
a local versioned bundle; deployment requires later acceptance and authorization.
For real Chrome flows using fake transports, run
`EUCWATCH_BROWSER_CHECKS=1 ./scripts/check.sh` (Chrome must be installed).
