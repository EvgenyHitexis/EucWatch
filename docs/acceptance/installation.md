# Watch installation and recovery preparation

This is #36 tooling preparation, with no device deployment, radio scan, Storage
change, reset, motor operation or firmware change. The full application, laptop
acceptance under #31 and separate owner authorization are prerequisites to
installation. #37–#38 own later deployment and device acceptance. Preparation
does not satisfy those milestones.

The procedure follows the [accepted installation decision](https://github.com/EvgenyHitexis/EucWatch/issues/4#issuecomment-6039249427)
and [measured backup/recovery evidence](../research/p22-backup-recovery.md).
The existing private snapshot contains 135 ordinary files, 470,751 bytes, and
no StorageFiles or saved interpreter image. Its contents are not included here.
The measured snapshot is evidence for its particular unchanged P22/2v14
installation; it is not a current inventory or a firmware/bootloader backup.

## Local commands

From the repository root, using the environment installed by `scripts/setup.sh`:

```sh
experiments/laptop-feasibility/.venv/bin/python scripts/watch-bundle.py build --version review36 --output /tmp/eucwatch-review36
experiments/laptop-feasibility/.venv/bin/python scripts/watch-bundle.py verify /tmp/eucwatch-review36
experiments/laptop-feasibility/.venv/bin/python scripts/watch-bundle.py rehearse /tmp/eucwatch-review36
env PYTHONPATH=laptop experiments/laptop-feasibility/.venv/bin/python -m unittest discover -s tests -p test_installation.py
```

Choose a new 1–8 character lowercase alphanumeric version and a new output
directory for every changed payload. An existing bundle directory is never
overwritten. The manifest records exact byte lengths, SHA-256 and CRC32 for
every file, including the separate startup candidate and third-party notice.
Hardcoded module imports become `sw-<version>-<module>`; each dependency must
be included and each Storage name must fit the 28-byte limit. The recovery
startup reads `sw-active.json`, which selects the verified versioned main.
Merely renaming main without rewriting its imports would mix versions.

These commands only read source and write local artifacts. The script has no
Bluetooth dependency, connection or deployment command. `rehearse` explicitly
uses synthetic Storage, runtime and authorization values. Its printed writes
are simulated effects. `--free-bytes 1` demonstrates capacity refusal without
any staging or deletion. Preserve a known-good local bundle for custom recovery.

For a private backup, separately run the following with the real off-repository
directory substituted locally; do not post the directory, inventory or content:

```sh
experiments/laptop-feasibility/.venv/bin/python scripts/watch-bundle.py verify-backup /private/storage-backup
```

The existing export manifest is read without modification. Complete/stable
inventory, P22/2v14 identity, exact binary lengths, SHA-256 and CRC32 must match.
Paths must remain inside the backup, which must be outside this repository.
Raw StorageFile chunks and saved interpreter images are refused: their flags
and execution semantics require a separate reviewed procedure. The command
prints only counts, total size and manifest hash, never private names or bytes.
It does not revalidate the current watch remotely.

## Reviewed first-install procedure

1. Record explicit laptop acceptance, completion of the full application and
   separate deployment authorization. Keep the verified historical backup and
   an independent durable copy off-device. Check the bundle's retained hash and
   review its startup source and required driver attribution.
2. Under the authorized console session, re-read `process.env` BOARD/VERSION,
   the ordinary/StorageFile inventory, working `.bootrst` length/CRC and current
   Storage free space. Preserve P22, Espruino 2v14, existing SoftDevice and
   bootloader. Compare current content against the reviewed private inventory;
   if changed, refresh the backup rather than assuming the historical snapshot
   is current. Record any unrecognized Storage flags and stop for review.
3. Present the concrete plan: every new versioned filename, size/hash, separate
   startup replacement, activation pointer and available/required capacity.
   The planner reserves full new bytes, alignment and conservative per-file
   overhead plus startup/pointer capacity. Its estimate is a refusal guard,
   not proof of device allocation fit. No deletion is part of staging. If
   insufficient, revise the concrete procedure before deleting anything.
4. Stage complete versioned ordinary files while the working startup remains
   untouched. The future live `DeviceStorage.write` adapter must allocate each
   ordinary file at full size before filling exact binary chunks, propagate
   failed writes, and confirm exact bytes after upload. Do not serialize tokenized
   bytes as JSON strings or use `save()`. Verify lengths/remote CRC32, then exact
   download/local SHA-256 against the manifest. No incomplete/mismatched file
   can pass activation; a conflicting existing version requires a new version.
5. Treat first `.bootrst` replacement as its own reviewed risk boundary, after
   all staged content is verified. Write the independently reviewed recovery
   startup as exact bytes and verify its complete length/hash. Only then write
   `sw-active.json` last, and read its version/main plus every active payload
   back. Activation does not reset the device. A lost activation acknowledgement
   is **unknown** until content/pointer readback resolves it; do not blindly retry.
6. Perform the separately authorized restart and independent recovery checks
   below. Verify normal startup, actual display, touch/button and vibration
   operation before legacy removal. Retain exact artifact versions, expected and
   observed results. Source code and synthetic success are not device evidence.
7. Review a private explicit legacy inventory with filename, purpose, length,
   SHA-256 and backup counterpart. It must cover old application, menus,
   settings and logs, including old coupled drivers no longer used by the custom
   app. No broad erase or guessed name pattern is permitted. `remove_legacy`
   checks active custom content and each reviewed hash before deleting only those
   names. It requires recorded custom startup/controls verification; startup and
   `sw-*` names are protected. Re-read final inventory to establish the custom-only
   installation, with historical backups remaining on the laptop. There is no
   old-app selector or on-watch old-app fallback.

## Updates and restoration

Routine updates stage a complete new version and switch the pointer after
verification. They require the recorded hash of the installed independent
recovery startup and preserve `.bootrst`. Saved configuration remains outside
versioned code; do not delete it during updates. Restore a known-good custom
bundle using the same stage/verify/pointer procedure, preserving recovery and
configuration. Never resume old pending wheel commands or confirmation.

Exceptional historical restoration is separately authorized disaster recovery,
not the intended final watch state. Enter verified console recovery with the
application stopped; validate private hashes, runtime and current inventory
again. Explicitly review any surplus files and their removal before restoring;
the tooling refuses unexpected inventory instead of deleting automatically.
Restore ordinary files as exact binary bytes with full-size allocation, verifying
each download/hash. Restore startup files last, with `.bootrst` last of all.
Verify complete final inventory and every checksum before a deliberate restart.
Transitional recovery markers must not remain in the final historical inventory.
Raw StorageFile chunks are not ordinary files; unsupported types are refused.
No interrupted install or restoration is claimed atomic.

## Actual-device recovery verification, pending authorization

Record watch/runtime/bundle versions and a reproducible expected/observed table.
First demonstrate ordinary custom startup and console access. With intact
independent startup, test a reviewed failed-start candidate and a separately
reviewed stalled-start candidate. The latter must be a deliberate limited test
artifact, not damage to `.bootrst`. The owner holds the physical button through
the 30-second watchdog window; allow a 40-second observation window as in the
existing measured procedure. Confirm `Sherman-recovery` advertisement, enabled
UART console, recovery reason/marker and no riding application import. Record
observed times without treating observation delay as motor or watchdog latency.
From that console, verify and restore the known-good custom bundle, clear only
reviewed recovery/startup markers through `ShermanRecovery.exit()` once ready,
and check the normal custom dashboard after restart. Repeat button/gesture,
display, battery/charger and vibration checks under their applicable authorization.

Recovery depends on **intact recovery startup, functioning runtime, button and
watchdog**. It does not recover its own corrupt first installation. Arbitrary
startup corruption or firmware/bootloader failure has no verified full recovery
route. A Storage backup is not a firmware, SoftDevice or bootloader image.

## Offline acceptance evidence

| Scenario | Expected | Observed | Provenance/artifact |
| --- | --- | --- | --- |
| Complete first install | Old startup intact during staging; independent startup separately verified; pointer last | Passed | `tests/test_installation.py`, controlled ordinary-byte DeviceStorage |
| Insufficient space, interruption, corruption, incomplete version | No activation; old startup retained | Passed | Controlled capacity/write/read failures |
| Changed bytes under same version | Refuse before modifying active content | Passed | Public planner/staging flow |
| Update and lost acknowledgement | Preserve recovery; unknown until explicit active readback | Passed | Synthetic Storage effects and pointer/content reconciliation |
| Private exported backup | Exact bytes/checksums/inventory; refuse unsupported flags and changed bytes | Passed | Synthetic binary exporter-format manifest outside repo |
| Historical restoration | Exact non-text bytes; startup last; final inventory verified | Passed | Controlled Storage adapter, binary 0x00/0x80/0xFF fixtures |
| Explicit legacy removal | Block until custom controls verified; changed/protected inventory refused | Passed | Reviewed hashes; no blanket deletion |
| Failed/stalled custom startup | Next boot exposes independent console without importing app | Passed offline | Actual `watch/boot.js` executed in Node VM; thrown start and VM timeout model |
| Local complete bundle rehearsal | Versioned imports, complete checksums, startup/pointer ordering | Passed | `scripts/watch-bundle.py` synthetic rehearsal output; no radio adapter |
| Device install/recovery and custom-only inventory | Authorized actual-device observations | Pending | #31, #37–#38; no new physical evidence |

The offline failed/stalled test establishes code-path behavior with fake pins,
Storage and UART; the VM timeout represents a stall and subsequent reset, not a
measured P22 watchdog reset. Device memory fit, native allocation behavior,
physical hold/console recovery and interrupted on-device writes remain pending.
