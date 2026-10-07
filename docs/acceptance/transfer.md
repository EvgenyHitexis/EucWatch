# Configuration transfer software evidence

Run `./scripts/setup.sh`, then `./scripts/launch.sh` from the repository root.
Start a controlled simulator, set speed to zero and send readings. Swipe down
from the dashboard top and tap **Transfer configuration**. The watch view
labels the simulated endpoint and wheel disconnection. The laptop panel shows
saved watch content/revision, proposed changes and explicit choices for differing
alert fields. Cancel preserves saved watch content; Refresh preview permits
another review. Transfer stages a complete validated candidate through bounded
JSONL/CRC32 chunks, verifies the staged SHA-256 and reads committed content back
before reporting success. Return to riding requires a new valid telemetry frame.

Expected and observed software results are in
[transfer-browser.json](evidence/transfer-browser.json). The actual built Canvas,
HTML and aiohttp flow refuses moving entry, accepts fresh stopped entry, exercises
watch Cancel and Transfer, compares saved copies and verifies no wheel commands.
`tests/test_transfer.py` covers corrupt chunks, stale previews, durable restart,
storage failures and abandoned command attempts. `tests/test_http_transfer.py`
uses controlled Bleak-compatible clients to verify stopped validation precedes
disconnect and Return selects a new telemetry session; late old callbacks are inert.

The endpoint is simulated. No physical BLE configuration transfer, wheel command
or horn operation was performed. Conflict reconciliation and interruption/unknown
outcome scenarios are developed separately in #29; actual watch durability and
Nordic UART integration are #35. Hardware acceptance remains #31/#37/#38.

## Reconciliation and interruption (#29)

The confirmed shared base now preserves one-sided edits, combines changes to
different fields, and accepts identical changes. Only differing changes to the
same alert field require a choice. Absent-base differences still require review;
presets originate on the laptop. Saved copies are re-read before submission and
again at validated staging before activation. A changed preview is refreshed for
review, preserving concurrent saved edits rather than overwriting them.

The simulated watch edit and staging/acknowledgement/readback failure controls
are explicitly labelled higher-level injections. Interrupted pre-activation
staging retains previous content. A durable bounded transaction marker is saved
before activation. Lost acknowledgement or partial persistence produces an
unknown outcome; preview/retry/Cancel stay unavailable until explicit active
content/revision readback. Successful reconciliation verifies the complete result
and updates both saved copies and shared base before clearing that marker.
Restart loads pending uncertainty without restoring commands or confirmation.

`tests/test_reconciliation.py` covers merge cases, invalid choices, simultaneous
saved edits, staging interruption, marker failure, lost acknowledgements,
readback failure, durable restart and partial laptop/shared saves. The actual
Canvas/HTML flow exercises both-side edits, stale preview refresh, a same-field
choice, unknown-outcome presentation and explicit verified readback:
[reconciliation-browser.json](evidence/reconciliation-browser.json).
Software checks passed; no physical transfer was performed.
