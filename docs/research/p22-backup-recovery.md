# P22 backup, startup and recovery prerequisites

Investigated 2026-10-07 for [Establish the watch backup and recovery prerequisites](https://github.com/EvgenyHitexis/EucWatch/issues/11). This supports the existing decision to retain Espruino 2v14 and replace the eucWatch application completely. It does not authorize application installation or firmware replacement.

## Device evidence and private backup

The known watch accepted the previously demonstrated Nordic UART console handshake. Runtime identity remained P22 / Espruino 2v14. Source inspection uses Espruino release `af8e933289968020d40fc55b18be8879ac55f085` and EUC Watch `72744e4003405de5e6a754777929866ea7b065fc`; the installed runtime's empty build-commit field prevents claiming an exact source match.

The Storage export uses binary Base64 chunks, validates each file against an on-watch CRC32 and records a local SHA-256 and byte count. It includes hidden startup files and tokenized JavaScript bytes. A text/JSON re-encoding would not preserve these files. Full contents, device identity, settings and logs stay in a private directory outside the repository. The public evidence contains only selected technical metadata and non-personal code hashes.

All **135 files, totaling 470,751 bytes**, passed export-time on-watch CRC validation, independent local SHA-256 verification, and a subsequent on-watch length/CRC sweep. Initial and final inventories matched. The [sanitized evidence](p22-backup-recovery-evidence.json) records the results. Private backup and restore manifests map every watch filename to its binary file, checksums and restoration order. This is a Storage payload backup, not an internal firmware, SoftDevice, bootloader, UICR or deleted-record flash image. A running application export is not an atomic whole-device snapshot; per-file verification and the later sweep delimit consistency.

Espruino 2v14 includes dot-files in `Storage.list()`, but suppresses continuation chunks of `StorageFile` objects. The exporter separately checks `{sf:false}` and `{sf:true}`. This device has 135 ordinary files and zero StorageFiles, with only `.bootrst` and `.display` as dot-files; no `.varimg` saved interpreter image was present. On another installation, raw StorageFile chunks require flag-aware restoration through the logical StorageFile API; writing raw chunk names with ordinary `Storage.write` loses their type. [Storage implementation][storage], [enumeration and raw reads][flash].

## Actual graphics and hardware contracts

Live graphics queries returned **240 × 240 pixels, 1 bit per pixel, 7,200 framebuffer bytes**. Stored and active configuration report 4 bpp; the instantiated graphics object is the authoritative measurement for the current driver. Installed `.display` explicitly selects one-bit graphics and uses native blitting with an RGB565 palette. Two palette entries per framebuffer bit mapping do not make the LCD monochrome: partial rectangles can be transferred using different palettes. The laptop/watch rendering contract must preserve those drawing and update constraints, rather than assume a full four-bit color framebuffer. [B1/D display implementation][display].

Installed startup dependency order is `.bootrst` → `.display`/cached display module → `handler` → `clock` → `euc`. `.bootrst` also reads screen-orientation settings and may create defaults when absent. The old handler mixes hardware setup with settings, connection modes, notifications, clock and wheel behavior. The custom app needs its own startup and a small hardware layer; keeping the old handler wholesale would contradict the owner's final-state requirement. The display code also references old application globals, so reusing it requires adapting those dependencies while retaining its known-working pin setup/native blitter and license notices. Physical B1-versus-D identification is not needed merely to read or restore this exact payload on this unchanged device; selecting different initialization or firmware still requires appropriate hardware evidence. [Installed-package baseline][identification], [published startup][init].

### Watch battery and charging

The actual runtime battery function samples `D31` and computes `voltage = 7.1 * analogRead(D31)`. Its normal percentage path clamps to 0 at/below 3.5 V and 100 at/above 4.19 V, truncating the linear interpolation between them. `batt()` returns voltage rounded to two decimals; `batt(1)` returns the percentage; `batt("info")` returns combined text. A truthy second argument bypasses percentage clamping. These are the installed conversion constants, not measured calibration accuracy.

The function samples on each call and then disconnects the analog pin through the GPIO configuration register for power saving. There is no independent battery sampling service in that function. The exported clock calls it during initialization and charging-state-related drawing; the custom app must own its refresh policy. The installed charging handler watches D19 with 500 ms debounce; on this P22 path it treats high as charging, sets `ew.is.ondc`, and changes accelerometer/display behavior. Charger transitions, percentage accuracy and sampling power cost were not physically tested. [Display/battery implementation][display], [charging handler][charge].

### Vibration

The installed bindings are D16, active level 1. `buzzer.sys`, `.alrm` and `.euc` bind `digitalPulse` directly; `.nav` does so only when navigation buzzing is enabled. A scalar is a pulse duration in milliseconds; arrays alternate active and inactive durations. The timer API returns before completion. This supports investigating distinct pulse patterns, but it does not establish physical strength control, exact perceived patterns or alarm scheduling behavior. No vibration command was sent. The new app must own queuing, cancellation and priority instead of inheriting old handler policy. [Buzzer bindings][buzz], [version-pinned digitalPulse implementation][pulse].

## Recovery boundary

The exported `.bootrst` contains a 30-second watchdog, kicked every three seconds only while BTN1 is released. A held button or a `devmode` marker at startup bypasses the old display/handler/clock/wheel application. Normal developer mode writes `devmode="done"` and advertises `Espruino-devmode`; a subsequent button press removes the markers and resets to working mode. The installed bytes support this path; a physical round trip must be recorded separately. The upstream README's 20-second wording disagrees with the 30-second installed code. [Startup implementation][init].

Holding BTN1 in generic nRF52 Espruino startup skips saved-state autoload, but **does not universally bypass `.bootrst`**. `.boot0`–`.boot3` and `.bootrst` have their own execution rules; Bangle-specific button suppression is not a P22 guarantee. Thus the observed application recovery mechanism depends on a functioning runtime, button, watchdog and recovery startup file. It does not recover arbitrary corruption of that startup file or firmware. [nRF52 entry][entry], [interpreter startup][interactive], [boot selection][flash].

Current live reads show **stored `cli=1` and active `cli=1`**. This supersedes the earlier identification session's stored `cli=0` observation. The backup procedure did not persist any setting change. Post-reset console behavior must still be observed; the working application and developer-mode advertisement are separate connection states, and recovery checks must identify the right one.

## Firmware and bootloader evidence

The repository's archived P22 Espruino 2v14 DFU zip has SHA-256 `f332d3c7d8e920c84b54d7b745525349a6bf4d6e29cf6c868993ddaee7efe06c`. Its manifest contains application firmware only. Its 257,796-byte application binary has SHA-256 `04d56559e4ce0b6b742a02d3eba8636b575df3ca1643313ab6aca5c7d0dd6d64`. This artifact is a candidate to compare, not a verified restore package for the installed binary or bootloader. [Pinned artifact][firmware].

Bounded FICR/UICR and SoftDevice metadata reads are captured in the sanitized evidence. They use documented nRF52832 chip-info registers, UICR `NRFFW[0]` for bootloader address, `NRFFW[1]` for MBR parameter page, and SDK12 SoftDevice information at `0x3000`. Optional fields are guarded by the reported structure size. A 256-byte application-prefix CRC can disprove exact equality to the archived binary but cannot prove whole-image identity. These reads exclude unique device IDs and encryption roots. [Nordic register reference][ficr], [SDK bootloader addressing][bootloader], [SoftDevice information layout][sd].

Observed: part `0x52832`, 64 KiB RAM, 512 KiB flash, application start `0x1f000`, bootloader address `0x78000`, MBR parameter page `0x7e000`, SoftDevice ID 132, FWID `0x91`, numeric version `3001000` (S132 3.1.0). The application prefix CRC is `b0cdaca3`, matching the archived candidate's first 256 bytes. This corroborates a candidate layout; it does not establish the full firmware hash, bootloader build or DFU compatibility.

No DFU transition, firmware write, bootloader write, reset or boot-file edit is part of these probes. The actual bootloader build, physical DFU-entry procedure, accepted image validation rules and exact firmware match still need evidence before firmware recovery can be called verified. No matching SWD pad/open-case procedure for this particular watch has been established. Stock-to-Espruino installation steps must not be reused as discovery steps on the working device.

## Proposed installation, update and restore sequence

This sequence is input to [Choose the watch runtime and installation approach](https://github.com/EvgenyHitexis/EucWatch/issues/4), not an approved deployment or a completed recovery test.

1. Verify the private backup manifest, checksums and matching runtime identity before any change. Keep an independent off-device copy. Review and observe a developer-mode round trip while the original application is intact; record the remaining firmware-recovery limitation.
2. Build and validate the replacement startup and hardware layer against the measured display, touch, button, charging and vibration contracts. The recovery entry must expose BLE console independently of the main riding application and check the button before importing application modules. Application syntax errors or a stalled application must not disable the intended recovery route. That route still depends on intact recovery code.
3. Stage non-startup files under versioned custom-app names, verify complete sizes/checksums, and check available Storage. Do not use `save()` or a broad erase. Test before selecting a new entry point; a partially transferred version must not become active.
4. Change the startup entry only under the reviewed installation procedure after recovery checks. Treat the initial replacement of `.bootrst` as a separate risk boundary: the new application's supervisor cannot rescue its own invalid installation. Keep the Espruino runtime, bootloader and SoftDevice unchanged.
5. Verify independent custom startup, BLE console recovery, display/input and vibration operation. Then remove the old eucWatch application, menus, settings and logs from the watch using an explicit inventory. The final watch contains the dedicated Sherman L app and necessary adapted hardware support; there is no eucWatch selector or fallback. Prior application backups remain on the laptop.
6. For later updates, stage and verify a complete new custom-app version before switching. Restore the prior custom-app version from the laptop if needed; routine application updates should not rewrite the recovery supervisor.
7. For restoration of this historical snapshot, enter a verified console/recovery state with application execution stopped, validate runtime compatibility, restore ordinary files as exact binary bytes with full-size allocation before chunk filling, and restore the startup entry last. Verify remote content checksums and inventory before deliberate restart. Keep transitional recovery markers out of the final restored inventory. A full old-app restoration is disaster recovery, not the desired final product state. Do not claim an interrupted restore is atomic.

## Controlled recovery observation to perform next

After the backup is verified and durably stored, with the owner observing the watch and no wheel session active: hold the side button through the watchdog restart (allow at least 35 seconds), then release it. The expected evidence is an `Espruino-devmode` advertisement and a working UART console, not a particular LCD screen. The current `.bootrst` creates its developer-mode marker as part of this operation. Read runtime identity and Storage without changing application files. A subsequent short button press should erase the marker and restart the original application. If its console is disabled afterward, use the already documented Bluetooth-console menu control; do not flash or erase anything to regain access. Record success or the exact deviation. This is a concrete proposed observation, not a claim that it has happened.

## Reproduce the read-only probes

The scripts use the already locked Bleak environment in `experiments/laptop-feasibility`. Supply a private identity JSON containing the known watch address; do not commit it. Use an output directory outside this repository. The exporter reads Storage, while the second probe verifies the local SHA-256 values and rechecks every remote length/CRC before recording bounded recovery metadata. Both disconnect afterward. Nordic UART GATT writes carry console read expressions; they are not Storage/firmware writes. The existing application may still update its own transient state or logs during a console connection.

```bash
experiments/laptop-feasibility/.venv/bin/python experiments/watch-recovery/export_storage.py --identity /private/identity.json --output /private/storage
experiments/laptop-feasibility/.venv/bin/python experiments/watch-recovery/read_recovery_identity.py --identity /private/identity.json --backup /private/storage --output /private/recovery-identity.json
```

[identification]: https://github.com/EvgenyHitexis/EucWatch/issues/2#issuecomment-6020880120
[storage]: https://github.com/espruino/Espruino/blob/af8e933289968020d40fc55b18be8879ac55f085/src/jswrap_storage.c
[flash]: https://github.com/espruino/Espruino/blob/af8e933289968020d40fc55b18be8879ac55f085/src/jsflash.c
[display]: https://github.com/enaon/eucWatch/blob/72744e4003405de5e6a754777929866ea7b065fc/v2/init/lcd_P8_16bit_rev.js
[init]: https://github.com/enaon/eucWatch/blob/72744e4003405de5e6a754777929866ea7b065fc/v2/init/init.js
[charge]: https://github.com/enaon/eucWatch/blob/72744e4003405de5e6a754777929866ea7b065fc/v2/handler/handler_charge.js
[buzz]: https://github.com/enaon/eucWatch/blob/72744e4003405de5e6a754777929866ea7b065fc/v2/handler/handler_buzz.js
[pulse]: https://github.com/espruino/Espruino/blob/af8e933289968020d40fc55b18be8879ac55f085/src/jswrap_io.c
[entry]: https://github.com/espruino/Espruino/blob/af8e933289968020d40fc55b18be8879ac55f085/targets/nrf5x/main.c
[interactive]: https://github.com/espruino/Espruino/blob/af8e933289968020d40fc55b18be8879ac55f085/src/jsinteractive.c
[firmware]: https://github.com/enaon/eucWatch/blob/72744e4003405de5e6a754777929866ea7b065fc/tools/hackme/step4-espruino_2v14_eucWatch_P22.zip
[ficr]: https://docs.nordicsemi.com/r/bundle/ps_nrf52832/page/ficr.html
[bootloader]: https://github.com/espruino/Espruino/blob/af8e933289968020d40fc55b18be8879ac55f085/targetlibs/nrf5x_12/components/libraries/bootloader/nrf_bootloader_info.h
[sd]: https://github.com/espruino/Espruino/blob/af8e933289968020d40fc55b18be8879ac55f085/targetlibs/nrf5x_12/components/softdevice/s132/headers/nrf_sdm.h
