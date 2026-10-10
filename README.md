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

Edit the four saved presets through watch-sized **Settings → Presets**.
Editing works locally without a wheel connection. Keypad OK accepts one value
into the unsaved draft; keypad Cancel or swipe up discards only that entry.
Close the keypad before navigating fields. On a field display, Save stores the
whole selected preset; Cancel or swipe up discards its
draft. Swipe left/right wraps through fields. Dip inclusion is separate from its
remembered value. Only selecting a preset in the riding menu applies it to the wheel. See
[preset editor behavior and evidence](docs/acceptance/preset-editor.md).
The separate panel supports alert editing, local configuration backup/import/restore,
reusable controlled scenarios and explicit wheel discovery. Saved laptop configuration uses the XDG configuration
directory; the watch retains its own presets and alert preferences in native
Storage. Each environment operates independently and preserves existing local
configuration across restart and compatible updates. See the
[local configuration checks](docs/acceptance/local-configuration.md). Live wheel
control requires a fresh selected session; replay always remains read-only.

The original P22 Espruino 2v14 application lives in [watch/](watch/).
Its 240×240 monochrome interface, bounded control and alert behavior, native
Storage adapter and independent recovery UART are exercised offline. See
[the matching watch preset editor checks](docs/acceptance/watch-preset-editor.md)
for the four-slot touch/keypad implementation and reusable laptop scenario results.
Follow [installation preparation](docs/acceptance/installation.md) to build and rehearse
a local versioned bundle; deployment requires later acceptance and authorization.
For real Chrome flows using fake transports, run
`EUCWATCH_BROWSER_CHECKS=1 ./scripts/check.sh` (Chrome must be installed).
