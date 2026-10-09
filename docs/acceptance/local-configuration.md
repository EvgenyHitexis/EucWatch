# Independent local configuration (#40)

The [resolved owner correction](https://github.com/EvgenyHitexis/EucWatch/issues/39#issuecomment-6082478274)
removes laptop/watch configuration synchronization, transfer and conflict review.
The laptop is the staging prototype; each environment retains its own four
preset slots and vibration preferences. This implements the removal slice in
[issue #40](https://github.com/EvgenyHitexis/EucWatch/issues/40). The direct
wheel-owned preset editor remains a separate implementation slice.

The laptop panel and both watch-sized and production-watch Settings have no
transfer entry. Former `transfer_*` and `nordic_*` laptop actions fail without
replacing saved content or ending the current wheel session. The watch rejects
retired actions and no longer loads or bundles `sw-transfer`: there is no JSONL
configuration receiver, staging/commit endpoint, or transfer advertising path.

Local schema 1, fixed slot identities, laptop XDG paths, watch `sw-config.json`
and their last-known-good copies are unchanged. Existing configuration needs no
re-entry. Old shared-base/journal files are ignored and left intact, including
pending outcomes from the retired workflow. They never activate configuration.
Native Storage staging still serves local saves. Validated laptop file
export/import/review/Cancel/restore remains available; this local backup review
does not reconcile another environment. Wheel readings and confirmation remain
excluded from saved configuration.

Recording/replay, simulator/scenario controls, direct wheel sessions, versioned
application installation/staged updates and independent recovery retain their
existing facilities. `boot.js` still enables the recovery Bluetooth console and
UART; application bundle staging/activation/readback is separate from the removed
configuration-exchange endpoint.

## Reproduction and results

Run from the repository root with the locked dependencies installed:

```sh
env PYTHONPATH=laptop:tests experiments/laptop-feasibility/.venv/bin/python -m unittest test_local_configuration
node watch/tests/local-configuration.cjs
EUCWATCH_BROWSER_CHECKS=1 ./scripts/check.sh
uvx ty check laptop --python experiments/laptop-feasibility/.venv/bin/python
```

On 2026-10-09, the full entry point passed 148 Python tests, the TypeScript/Vite
build, all seven watch suites and both Chrome flows. Python `ty` also passed.

The full entry point runs current Python checks, the TypeScript/Vite build,
seven offline watch suites and, when enabled, the complete Chrome journey and
browser lifecycle flow. Focused HTTP/browser results are regenerated under
`.test-output/`; the watch result is regenerated in `watch/evidence/`.

| Observable boundary | Expected | Observed / retained evidence |
| --- | --- | --- |
| Laptop HTTP API, retired client actions | Refuse every former transfer/review/reconcile/activation and Nordic intent; preserve local content and wheel session | Passed: [HTTP actions](evidence/local-configuration-actions.json) |
| Laptop local storage through HTTP | Load existing revision 17, fixed slot and PWM preference; persist local edit through restart; recover interrupted restore/corrupt active copy; ignore historical reconciliation content | Passed: [local retention](evidence/local-configuration-persistence.json) |
| Built laptop panel and Canvas Settings | No transfer/synchronization/conflict entries; former touch preserves Settings, saved content and wheel session; export/import/Cancel/restore remains usable | Passed: [Chrome journey](evidence/local-configuration-browser.json) |
| Production watch main/input/render/Storage in offline runtime | No Settings entry or receiver; reject retired actions; load existing revision 23; preserve independent Watch local slot and local alert edit through restart/interrupted save recovery | Passed: [watch expected/observed result](../../watch/evidence/local-configuration.json) |
| Independent recovery startup | Bluetooth console and UART remain available | Passed in the same offline watch result; fake radio/pins only |
| Retained recording, replay, controls, updates and recovery | Existing public behavior continues | Current full Python/watch/browser checks pass; installation tests use synthetic Storage only |

The focused retained artifacts include source SHA-256 fingerprints and explicit
provenance. Laptop tests use temporary files and synthetic wheel/clock inputs;
the watch harness executes production ES5 modules with fake radio, pins, native
drivers and Storage. No physical wheel command, watch installation or hardware
measurement was performed. These results complete this software removal slice,
not actual-device flash atomicity, radio reliability or deployment acceptance.

## Superseded gates and historical provenance

Configuration-transfer gates from #28/#29/#35 are superseded. `scripts/check.sh`
replaces `transfer`, `transfer-wire` and `browser_transfer` with the local checks
and revised complete browser journey. The former laptop protocol/merge/Nordic
tests and watch exchange bridge are removed with their application interfaces.

[Transfer](transfer.md), [watch transfer](watch-transfer.md) and the
[prior controls/transfer review](review-34-35.md) are marked historical.
Their original evidence JSON, source fingerprints and 2026-10-08 results remain
unchanged for provenance. They describe the previous product scope and do not
count as acceptance of independent local configuration. Earlier editor evidence
also retains its recorded scope; it does not establish the corrected direct
wheel-owned editor behavior.
