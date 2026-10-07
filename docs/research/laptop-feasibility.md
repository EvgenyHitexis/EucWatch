# Ubuntu BLE and laptop session feasibility

Measured 2026-10-07 for [Verify Ubuntu BLE access and laptop session feasibility](https://github.com/EvgenyHitexis/EucWatch/issues/15). The owner explicitly deferred wheel verification and selected laptop feasibility. This is a bounded experiment supporting the selected architecture, not delivery of the laptop application.

**Verdict: partial pass.** Ordinary-user BLE discovery, fixture capture/replay, and browser-independent synthetic recording passed. No measured result requires changing the Python-owned session boundary. Live Sherman L discovery/selection, GATT subscription, real telemetry, reconnect, and physical laptop suspend/resume remain unverified. Keep the task open; this does not establish complete hardware feasibility.

## Artifacts and environment

- [Sanitized measured results](laptop-feasibility-evidence.json).
- [Reproducible experiment](../../experiments/laptop-feasibility/), including exact dependency pins and `uv.lock`.
- [Small recorded fixture](../../experiments/laptop-feasibility/evidence/fixture-recording.jsonl), retaining bytes, notification boundaries and synthetic receipt times.
- [Protocol source and fixture provenance](sherman-l-protocol.md). The packet is from upstream WheelLog's Sherman L fixture, not the owner's wheel.

Ubuntu 24.04.5 LTS; kernel 7.0.0-38-generic; Python 3.12.3; BlueZ package 5.72-0ubuntu5.5; uv 0.9.26; Bleak 3.0.2; dbus-fast 5.2.0; aiohttp 3.14.4; Google Chrome 154.0.8037.92. Run as ordinary uid 1000. The isolated environment targets Python 3.12 specifically; all transitive Python versions and hashes are in the lockfile. Chrome is an installed-system dependency whose tested version is recorded, not managed by that lockfile.

No Bluetooth policy changes, elevated Bluetooth process, device connection, GATT subscription, application-level wheel command, or watch change occurred. Installing dependencies needed access to uv's user cache; launching Chrome on a virtual display needed execution outside the workspace sandbox. Those execution permissions did not make the probes root processes.

## Measurements

| Check | Result | Evidence boundary |
| --- | --- | --- |
| Ordinary-user Bleak scan/start/stop | Passed: 5.09 seconds, 171 advertisement callbacks, 35 distinct devices | Aggregate counts only; identities were not retained or matched to the wheel |
| Adapter after scanner exit | `Discovering: no` | Local observation, not a general exclusivity guarantee |
| Frame assembly | Passed: all 86 two-part split positions, byte-at-a-time input, three coalesced frames | Only evidenced 87-byte fixture format supported |
| Corruption/recovery | Passed: 696 single-bit mutations followed by a valid frame, plus invalid-length/noise recovery | Strict fixture-length parser, not a general firmware parser |
| Raw recording/replay | Passed: 13 notifications, including corrupt/noise input and a time gap, replayed to identical per-event states and three valid frames | Times are synthetic; no actual wheel cadence measured |
| Hidden browser tab | Passed: actual `visibilityState=hidden` for 3 seconds, backend added 29 valid frames | Short hidden-tab observation, not long-duration browser throttle qualification |
| Forced renderer freeze | Passed: 2 seconds, backend added 20 frames; browser poll counter stayed at 4 between freeze/resume events | Explicit CDP freeze, not natural Chrome freezing or host suspend |
| Browser reload | Passed: same backend session; observed frame count advanced from 56 to 58 | Tiny read-only view, not application UI acceptance |
| Input stops/resumes | Passed: browser displayed `fresh=false` after synthetic feed stopped, then fresh again after new input | One-second probe timeout, not the product's agreed policy |
| Probe pages closed | Passed: backend added 10 frames | Recording ownership stays in Python |
| Synthetic suspend and command lifecycle | Passed: stale retained telemetry, pending intent cancellation, rejection of old callbacks, no resubmission after reconnect, expired-intent rejection and duplicate suppression | In-memory fake transport; no real control submission or actual suspend |

The final browser run recorded 355 synthetic notifications and 71 valid frames in 8.22 seconds. It checked every recorded byte and sequence against the generated stream and checked timestamp ordering. Its full JSONL remains locally in the experiment's ignored `output/browser-recording.jsonl`; the summary contains its SHA-256. The committed smaller fixture recording supports reproducible offline replay without treating synthetic captures as owner hardware evidence.

## What the probe establishes

Bleak uses BlueZ over D-Bus on Linux. Its scanner context manager starts and stops the application's discovery session. This laptop actually exercised that path successfully. Upstream default policy alone would not prove local access. Discovery is shared across clients, so another application's scan could legitimately leave global discovery active after ours exits. [Bleak Linux backend](https://bleak.readthedocs.io/en/latest/backends/linux.html), [Bleak scanner API](https://bleak.readthedocs.io/en/latest/api/scanner.html), [BlueZ Adapter API](https://github.com/bluez/bluez/blob/master/doc/org.bluez.Adapter.rst).

The same small Python core receives source-fixture bytes during generation and replay. The browser only reads current state. This concretely supports keeping telemetry processing, the recording clock and session state outside page timers. It does not validate production backpressure, durable configuration, real alerts, control transport or the future watch port.

The final browser probe uses Chrome's direct debugging protocol, an isolated temporary profile, and headed Chrome on Xvfb. It does not enable focus emulation or disable background throttling. Both actual hidden visibility and freeze/resume events were measured. Initial Playwright attempts timed out waiting for hidden visibility, even after disabling selected launch defaults and sending a focus-emulation override on a separate protocol session. Those runs were not counted as passing evidence. Playwright's source explains why its defaults are unsuitable for assuming natural background behavior; the final harness bypasses them. [Playwright Chromium switches](https://github.com/microsoft/playwright/blob/main/packages/playwright-core/src/server/chromium/chromiumSwitches.ts), [Playwright page setup](https://github.com/microsoft/playwright/blob/main/packages/playwright-core/src/server/chromium/crPage.ts), [Chrome page lifecycle](https://developer.chrome.com/docs/web-platform/page-lifecycle-api).

Python exposes `CLOCK_BOOTTIME` on this laptop. Linux defines it to include suspend time, whereas `CLOCK_MONOTONIC` excludes suspend. The offline probe injects a 60-second boottime jump while monotonic time advances only 10 ms, then verifies stale state and cancelled fake intents. This exercises one model of recovery; it does not establish the laptop's actual wake/Bluetooth event ordering. The probe's timing constants and epoch invalidation are demonstration choices, not resolved product policies. [Python time clocks](https://docs.python.org/3/library/time.html#time.CLOCK_BOOTTIME), [PEP 418 clock semantics](https://peps.python.org/pep-0418/#clock-monotonic-clock-monotonic-raw-clock-boottime).

## Reproduce

From the repository root, install the locked probe environment once:

```bash
uv sync --project experiments/laptop-feasibility --frozen --python /usr/bin/python3
```

Then run from its directory. These commands use the environment directly and do not resolve dependencies again:

```bash
cd experiments/laptop-feasibility
.venv/bin/python probe.py
.venv/bin/python probe.py --scan
xvfb-run -a .venv/bin/python browser_probe.py
```

The first command is entirely offline. `--scan` performs a five-second active advertisement scan, retaining only aggregate counts and making no device connections. The browser command requires installed Chrome and Xvfb, serves synthetic state on a temporary loopback port, and removes its temporary browser profile when done. Outputs go to ignored `output/`; committed evidence is a retained snapshot, not automatically overwritten by subsequent runs. The probe contains no BLE connect or write path.

## Remaining evidence before resolution

1. With the owner available to observe the stationary wheel, select the correct Sherman L and record sanitized identity/firmware evidence, service and FFE1 properties, subscription outcome, notification boundaries, callback receipt times, cadence and CRC results. Establish whether subscription alone yields data before considering any initialization writes.
2. Capture a controlled real disconnect/reconnect and assess competing phone/watch connections. Advertisement scanning does not prove GATT or notification permission.
3. Observe actual laptop suspend/resume at an agreed time, including telemetry becoming stale and reconnect behavior. Do not suspend the operator's laptop as an unattended side effect of this probe.
4. Feed a sanitized live capture through the same offline assembly/recording checks. The present fixture-only length whitelist must be revisited if owner firmware emits another format.

Preset mappings, fresh setting readback and audible horn verification stay in [Verify EUC World control mappings and horn on the owner’s Sherman L](https://github.com/EvgenyHitexis/EucWatch/issues/9). The full application acceptance checklist stays in [Define the laptop prototype and pre-watch acceptance criteria](https://github.com/EvgenyHitexis/EucWatch/issues/10). No decision ticket is resolved by the synthetic evidence alone.
