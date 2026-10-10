# #31 implementation review

Baseline: `0190ce6fc0cff52613186cc0771efb8b71609723`.
Implementation: `1a568b3` (`git diff 0190ce6...1a568b3`).
Standards and Spec were reviewed independently in parallel, then each reviewer
checked the corrections below. Unrelated research work and the owner's running
review session were outside the diff and were not touched by the reviewers.

## Standards

No documented-standard or ADR violations found. Evidence correctly distinguishes
simulated behavior from physical acceptance. The initial review verified all 95
source hashes and 43 artifact hashes.

- **P2, resolved — shutdown evidence could falsely pass.** The launcher smoke
  check caught `URLError` (including HTTP 500) and timeouts as evidence of a closed
  port. Its forced cleanup could then conceal a surviving backend. The check now
  requires TCP connection refusal. Successful connections keep waiting; timeouts
  fail. Forced cleanup remains independent of the assertion. The focused real
  launch/shutdown/relaunch check passed after the correction, and the reviewer
  confirmed the finding resolved.
- **Nonblocking Duplicated Code judgment, deferred.** The small flow-local
  watch-label wait wrappers repeat a DOM selector and escaping expression across
  browser flows. A shared helper is an optional refactor, not a documented-rule
  violation. Keeping this out of the acceptance correction avoids changing the
  otherwise verified flows. The reviewer agreed deferral is reasonable.

## Spec

- **P2, resolved — walkthrough navigation was discontinuous.** The requirement
  is to “Review complete watch-sized flows through the actual UI/backend
  boundary.” R3 left the user at preset selection, while R4 assumed the dashboard;
  R4 also asked for Test after Cancel had closed alerts. The guide now explicitly
  returns to the dashboard after R3, reopens alerts before Test, and returns to the
  dashboard before R5. It explains restart of the agent-managed review session.
  The reviewer confirmed no remaining material Spec findings.

No unrequested behavior or scope expansion found. The help correction matches
the confirmed value-editor behavior. Owner readiness is not recorded as owner
acceptance. Required live evidence and deferred horn/riding/deployment gates
remain incomplete in the acceptance register; these require owner participation.

Validation: the complete check passed before review (160 Python tests, frontend
typecheck/build, six Chrome flows, launcher smoke and thirteen offline watch
suites). The only executable review correction is in the launcher test; its
focused rerun passed. The [manifest](evidence/laptop-31/validation.json) records
both runs, the code versions and refreshed hashes. Documentation links and
`git diff --check` passed.

Remaining findings: Standards **1 nonblocking duplication suggestion**, no hard
violations or blocking findings; Spec **0 implementation/evidence findings**,
with owner/live acceptance still pending.
