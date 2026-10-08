# Review of watch controls and configuration transfer

Reviewed on 2026-10-08 against specification
[#17](https://github.com/EvgenyHitexis/EucWatch/issues/17) and implementation
[#34](https://github.com/EvgenyHitexis/EucWatch/issues/34) /
[#35](https://github.com/EvgenyHitexis/EucWatch/issues/35).
Fixed point: `21d74310004f487322dcf157d7d1901e9a7069db`.
The review includes controls commit `5560c3a`, pending transfer implementation,
its new adapters/tests and the two corrections below. Unrelated private captures,
research work and the imported community archive are excluded.

## Standards

The independent standards review found no documented violations. Vocabulary
matches `CONTEXT.md`; no relevant ADR exists. Tooling checks are reported
separately in the acceptance register.

Two possible smells remain as nonblocking judgement calls: synchronous and
asynchronous workflows repeat the decision for accepting an uncertain commit
after readback; the HTTP coordinator directly sets transfer failure state after
an uncertain BLE disconnect. The existing shared reconciliation state and
transfer object offer places to consolidate these if later changes require it.

## Spec

Two reproduced defects were corrected and independently re-reviewed:

- After loading a backup because the active copy was corrupt, activation could
  overwrite the sole good backup before verifying the new active copy. A partial
  backup write then lost all valid saved content. `watch/store.js` now preserves
  that backup while replacing the active copy. The actual endpoint/Storage test
  covers successful replacement and another interrupted activation after recovery.
- Upload recomputed the expected watch digest with Python JSON formatting. A
  valid `1e-7` threshold returned by the watch became Python `1e-07`, rejecting
  subsequent transfers as stale. The shared protocol workflow now verifies a
  fresh remote snapshot, compares its complete content with the reviewed copy,
  and uses the digest of those exact bytes. The Python-to-watch byte bridge
  reproduces the failure and verifies replacement after the correction.

No further confirmed missing requirements, scope creep or incorrect lifecycle
behavior was found. Actual-device checks are explicitly retained for #31/#38;
offline success does not establish physical acceptance.

Standards: zero hard violations, two possible smells. Spec: two defects fixed,
zero unresolved confirmed defects.
