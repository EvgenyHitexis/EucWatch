# Watch configuration transfer — offline evidence

> Historical record — configuration synchronization/transfer and its review/conflict
> gates (#28/#29/#35) were superseded on 2026-10-09 by
> [the resolved owner correction](https://github.com/EvgenyHitexis/EucWatch/issues/39#issuecomment-6082478274)
> and [issue #40](https://github.com/EvgenyHitexis/EucWatch/issues/40).
> The workflow, endpoint and referenced transfer test commands have been removed.
> Retained evidence below preserves its original provenance and applies only to
> the previous scope; it is not acceptance of the revised product. Use
> [local configuration checks](local-configuration.md) for the replacement gates.


This is implementation evidence for [#35](https://github.com/EvgenyHitexis/EucWatch/issues/35), under the accepted [#17 specification](https://github.com/EvgenyHitexis/EucWatch/issues/17). It does not establish real watch BLE, flash persistence, memory fit, installation or riding behavior. No hardware operations or deployment were performed.

From the repository root, run:

```sh
node watch/tests/transfer.cjs
node watch/tests/transfer-wire.cjs
env PYTHONPATH=laptop uv run --offline --no-sync --project experiments/laptop-feasibility python -m unittest discover -s tests -p test_watch_wire.py
```

The first command exercises the production watch endpoint and Storage adapter through byte JSONL requests and saved-content readback. The second executes the actual watch entry point, physical-input adapter, application, rendering, transport and transfer adapter in the existing Node hardware harness. It regenerates [expected/observed results and source fingerprints](../../watch/evidence/transfer.json). The Python command drives the actual ES5 endpoint and Storage implementation through the shared laptop protocol; its transport is an offline byte bridge. The fixture supplies protocol shape, with speed/settings changes and CRC regenerated explicitly; it is not new wheel evidence.

| Scenario | Expected result | Observed offline result |
| --- | --- | --- |
| Settings transfer entry at initial idle or with fresh speed exactly zero | End the wheel session, clear confirmation/pending application, block wheel commands | Actual touch entry and public application traces pass; late callbacks cannot submit the next preset command or horn |
| Delayed wheel disconnect | Do not advertise/accept laptop transfer until central cleanup is confirmed | Peripheral service creation waits for the actual transport's closed/nonbusy state |
| Fragmented/coalesced requests | Assemble complete bounded lines; recover after an oversized line | Seven-byte fragments, multiple lines and a 700-byte rejected line pass |
| Complete configuration read | Stable snapshot, sorted keys, UTF-8 bytes, SHA-256 and 64-byte CRC32 chunks | Python/watch roundtrip and 24-character UTF-8 names pass; 2v14 high-byte JSON escaping is modeled explicitly |
| Stage/validate/commit | Receive in order, validate the complete version-one document, stage and read-verify before activation | No active change before commit; new revision and full content verified after restart |
| Unsupported/incomplete/corrupt/oversized data | Reject without replacing usable saved content | Duplicate JSON keys, missing bytes, stale content, bad order/CRC and 4,097-byte staging rejected |
| Storage refusal/partial writes | Preserve a validated independent copy | Stage, backup and active failures tested; interrupted first activation recovers validated defaults; subsequent partial activation recovers the previous saved copy |
| Save after backup recovery | Keep the sole valid backup while replacing a corrupt/missing active copy | Successful replacement and repeated interrupted activation retain a readable saved copy; a backup-write fault cannot destroy the recovered copy |
| Different numeric JSON formatting | Bind staging to the digest of the verified watch bytes | Actual Python/watch transfer with a `1e-7` threshold passes a subsequent replacement despite Python formatting it as `1e-07` |
| Lost commit acknowledgement | Read active content before assuming success or retry | Restart/readback finds the committed revision; a repeated commit without a new reviewed stage is rejected |
| `finish` | Queue acknowledgement, stop peripheral advertising and confirm laptop disconnection before returning/reconnecting | Active peripheral connection blocks return even after response submission; refused output cannot automatically return |
| Cancel, staging timeout and explicit Return | Cancel staging without activation; preserve usable content; require fresh telemetry after return | Abort, 30-second staging timeout and explicit Return pass; transfer remains awake |
| Long hold during transfer | Stop transfer and preserve independent recovery console | Actual button/watchdog path closes transfer, resets and restores Bluetooth console in the recovery startup |

The wire contract retains `protocol:1`, bounded 512-byte JSONL messages and 64-byte decoded chunks. `read`, `read_chunk`, `stage`, `chunk`, `validate`, `commit`, and `abort` match the laptop contract. `finish` replies with `returned:true`; it does not apply a riding preset or request the horn. Saved watch content is limited to **4,096 bytes** for this runtime. Larger configurations return an explicit error for review. Snapshot digests cover the exact returned bytes; callers must not assume Python and Espruino serialize every floating-point number identically.

`sw-config-stage.json` is written and reread during validation. Activation verifies that stage again, preserves a validated previous/default copy in `sw-config-backup.json`, then writes/rereads `sw-config.json`. If the active copy is corrupt or missing, an existing valid backup remains intact throughout replacement. Loading checks the active copy and falls back to the validated backup. Comparisons check actual values rather than serialize them again: upstream 2v14 JSON formatting can round precise numbers, and a meaning-changing roundtrip is rejected before activation with an explicit review error. Configuration copying preserves numeric values independently of JSON formatting. Staging uses the digest of a freshly verified remote snapshot, preserving the exact watch serialization rather than recomputing its digest in Python. These are separate Storage operations, not a transaction: acknowledgement loss and interrupted activation remain uncertain until active saved content is read. The test harness injects refusal and partial writes at these boundaries, and models near-integer rounding for a `19.99999999` threshold.

The native adapter routes the console to `LoopbackA` before accepting protocol input on `Bluetooth.on('data')`. Responses are queued in at most 1,024 bytes and submitted in 20-byte chunks. Explicit false writes are retried only while bounded; exceptions or dropped-byte flags retain a failed transfer that requires readback/reconnection or explicit Return. A software queue accepting all reply bytes does not prove their physical delivery. `NRF.sleep()` stops advertising and requests peripheral disconnection; `NRF.getSecurityStatus().connected` must become false before normal wheel connection behavior resumes. Return leaves peripheral advertising asleep during wheel operation. Independent recovery startup explicitly restores the Bluetooth console and advertising.

Primary API provenance is pinned to Espruino **2v14**, commit `af8e933289968020d40fc55b18be8879ac55f085`: [native SHA-256](https://github.com/espruino/Espruino/blob/af8e933289968020d40fc55b18be8879ac55f085/libs/crypto/jswrap_crypto.c), [CRC32 and console routing](https://github.com/espruino/Espruino/blob/af8e933289968020d40fc55b18be8879ac55f085/src/jswrap_espruino.c), [Serial write](https://github.com/espruino/Espruino/blob/af8e933289968020d40fc55b18be8879ac55f085/src/jswrap_serial.c), [peripheral connection state/services/sleep](https://github.com/espruino/Espruino/blob/af8e933289968020d40fc55b18be8879ac55f085/libs/bluetooth/jswrap_bluetooth.c), [Storage operations](https://github.com/espruino/Espruino/blob/af8e933289968020d40fc55b18be8879ac55f085/src/jswrap_storage.c), and [JSON byte escaping](https://github.com/espruino/Espruino/blob/af8e933289968020d40fc55b18be8879ac55f085/src/jsutils.c). The console separation pattern is documented by [Espruino BLE access control](https://www.espruino.com/BLE%20Security).

Before deployment/acceptance, verify these APIs and the concrete application's memory/timing on the installed P22 build, which reports no exact build commit. SHA-256 is conditional in upstream builds; the [pinned P22 board definition](https://github.com/enaon/eucWatch/blob/72744e4003405de5e6a754777929866ea7b065fc/tools/boards/EW_P22.py) does not establish its availability. Retain actual-device checks for Nordic UART discovery/exchange, role cleanup, interrupted flash writes, restart/recovery, UTF-8 glyph rendering, physical controls and update compatibility. Keep #31 and outstanding wheel evidence #9 open; the software traces do not authorize deployment, sounding the horn or riding experiments.

The #34 review fixes are covered at the same application/render boundary: short horn feedback appears on Settings, alert editor, threshold keypad and connection screens; fresh actual settings repaint terminal preset results at the scheduled presentation cadence.
