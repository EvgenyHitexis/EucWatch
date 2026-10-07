# Laptop application stack and Bluetooth integration

Investigated 2026-10-07 for [Choose the laptop application stack and Bluetooth integration](https://github.com/EvgenyHitexis/EucWatch/issues/13). This is supporting evidence and a conditional recommendation, not an owner-approved stack decision. No packages were installed and no Bluetooth scan, connection, subscription, or device write was attempted.

## Local evidence

Read-only commands on the owner's laptop returned Ubuntu 24.04.5 LTS, kernel `7.0.0-38-generic`, Python 3.12.3, Node 24.13.0, npm 11.13.0 and BlueZ 5.72. `uv` and Google Chrome executables exist. System Python cannot currently import Bleak, PySide6 or aiohttp; this does not inventory isolated environments. Sources: `/etc/os-release`, `uname -r`, runtime version commands, `command -v`, and `importlib.util.find_spec`.

`systemctl is-active bluetooth` returned `active`; ordinary-user `bluetoothctl show` reported a powered adapter with central and peripheral roles and no active discovery. `/usr/share/dbus-1/system.d/bluetooth.conf` permits the default policy to send to `org.bluez`. This establishes adapter visibility and an apparently suitable D-Bus policy, **not** successful scan/connect/notification authorization. The two advertised roles do not establish simultaneous-role operation or simultaneous watch/wheel connections. No such concurrency is needed merely to connect the laptop directly to the wheel.

The existing [Sherman L protocol evidence](sherman-l-protocol.md) supplies FFE0/FFE1, raw fragmented notification fixtures and CRC validation; owner's wheel firmware compatibility remains unmeasured. The [watch identification decision](https://github.com/EvgenyHitexis/EucWatch/issues/2#issuecomment-6020880120) identifies P22/Espruino 2v14 with 64 KiB RAM. Laptop/browser source portability to this watch remains unproven; fixtures and behavioral contracts can be shared without requiring identical runtimes.

## Comparison

| Approach | Fit for this application | Specific cost or uncertainty |
| --- | --- | --- |
| Browser UI plus local Python/Bleak process | Canvas watch view alongside ordinary HTML editor/scenario controls; normal BlueZ integration; persistent session outside browser | Python and frontend toolchains; local API and process lifecycle to implement |
| Electron plus native Node BLE | Same web rendering, a standalone window, Node-owned session and files | Must select and validate a particular BLE binding; native-addon packaging and Linux permissions vary |
| Python/PySide6 plus Bleak | Native window, one main language, custom-painted watch view and separate widgets | Qt/asyncio integration and packaging; less direct reuse of web UI tooling |
| Browser-only Web Bluetooth | One UI/runtime, direct GATT API where supported | Linux flag/support and browser permission constraints; page lifecycle is a poor owner for recordings and timing |

Bleak documents Linux support from BlueZ 5.55 and uses asynchronous D-Bus access; the measured BlueZ 5.72 meets that documented minimum. Bleak objects belong to one asyncio event loop. Its current Linux documentation describes `StartNotify` as the default again after a short-lived 3.0.0–3.0.1 change, so pin a tested release instead of assuming all current variants behave identically. [Supported backends](https://bleak.readthedocs.io/en/latest/backends/index.html), [Linux backend](https://bleak.readthedocs.io/en/latest/backends/linux.html).

Electron itself supplies Web Bluetooth integration with application-managed device selection; that is distinct from native Node BLE. Native Node addons may require rebuilding for Electron's ABI. As one concrete native option, `@abandonware/noble` documents Linux raw-network capability setup; those requirements must not be generalized to every Node binding or silently imposed on this laptop. A BlueZ D-Bus binding is another possibility but was not evaluated here. [Electron device APIs](https://www.electronjs.org/docs/latest/tutorial/devices), [native addons](https://www.electronjs.org/docs/latest/tutorial/using-native-node-modules), [Noble permissions](https://github.com/abandonware/noble#running-without-rootsudo-linux-specific).

PySide6's QtAsyncio remains a technical preview covering event-loop fundamentals, rather than all asyncio networking facilities. Consequently, do not assume it is a drop-in event loop for Bleak's D-Bus dependencies. A dedicated standard asyncio worker loop with Qt signals is a candidate boundary requiring a check. [QtAsyncio documentation](https://doc.qt.io/qtforpython-6/PySide6/QtAsyncio/index.html).

Chrome's official guide still requires experimental web-platform features for Linux Web Bluetooth and a user gesture for device requests. Browser-only should therefore pass a real machine check before selection. It cannot be justified simply because Chrome is installed. [Chrome Bluetooth guide](https://developer.chrome.com/docs/capabilities/bluetooth), [specification implementation status](https://github.com/whatwg/bluetooth/blob/main/implementation-status.md).

## Conditional recommendation and boundaries

If an Ubuntu-first browser tab is acceptable, prefer **TypeScript/Canvas presentation plus a Python asyncio application process using Bleak/BlueZ**. This is an engineering recommendation inferred from the measured environment and documented APIs. Keep the entire parser, state transitions, freshness, alerts, command lifecycle, simulator and replay controller in one Python behavior core; the browser sends intents and renders state. This avoids parallel Python/JavaScript parsers within the laptop application. Future watch code can implement the accepted behavior against shared traces and expected results; literal Python reuse on Espruino is not proposed.

The local process should own the clock and session independently of tab visibility. Chrome documents substantial throttling of hidden-page timers and suspended animation callbacks; exact historical throttle thresholds are not a timing contract for installed Chrome. Backend ownership prevents browser timer policy from changing recorded event order or alert decisions. UI rendering and audible/visual presentation can still be delayed in a hidden tab. Whole-machine sleep still pauses application execution. [Chrome timer behavior](https://developer.chrome.com/blog/timer-throttling-in-chrome-88).

Proposed recording boundary: stamp each notification immediately at callback ingress with sequence, session identifier, characteristic, raw bytes and elapsed receive time, before decoding. Bleak supplies characteristic and bytes to the notification callback, not a wheel-originated timestamp: record these as **host receipt times**. Include connection transitions, user intents and simulator events for behavioral replay. Live, replay and simulated traffic should converge at the same parser/core seam; scenario-only semantic injection must be explicitly identified. [Bleak notifications](https://bleak.readthedocs.io/en/latest/api/client.html#bleak.BleakClient.start_notify).

Inject the core's clock. Replay advances virtual time from recorded events rather than counting GUI ticks. Use monotonic elapsed time for live operation and wall-clock time only as session metadata; document suspend handling. On this Linux target `CLOCK_BOOTTIME` includes suspend time, unlike `CLOCK_MONOTONIC`; this supports marking retained telemetry stale immediately after resume. Neither clock makes alerts execute while asleep. [Python time clocks](https://docs.python.org/3/library/time.html).

Proposed local launch: a repository command builds frontend assets when needed, runs the locked Python environment, serves the assets/API on loopback and opens the browser after readiness. After dependency installation, normal startup should work offline. `uv run` supports project environment management; an actual single-command launcher remains work to implement. Store settings/scenarios and wheel recordings in application-owned local files with explicit format versions; browser storage should not be the only copy. Keep recording writes ordered and bounded, report storage failures, and separate live-command capability from simulator/replay sessions. [uv project workflow](https://docs.astral.sh/uv/guides/projects/).

## Bounded checks still needed

1. Dependency-only integration check: pinned Bleak on the ordinary user session can access BlueZ without privilege changes. Then, when live observation is authorized, select the owner's wheel and establish FFE1 notification delivery without riding-setting writes.
2. Capture notification sizes, timestamps, disconnect behavior and CRC-valid family identity; validate packet assembly and record/replay equivalence using the same core. Confirm a phone/watch connection does not block the intended laptop session.
3. Hide/reload the browser during a synthetic session: backend recording and decisions continue, and the UI reconnects to current authoritative state. Separately check suspend/resume marks data stale and does not replay pending live commands.
4. Verify one-command startup/shutdown, offline relaunch, saved configuration and recordings, including busy-port and unavailable-Bluetooth behavior. Distribution to other operating systems needs its own packaging and BLE checks if requested.

These checks are proposed evidence gates; none has been represented as completed. Standalone-window preference or immediate cross-platform distribution may change the comparison without changing the need for a transport-independent behavior core.
