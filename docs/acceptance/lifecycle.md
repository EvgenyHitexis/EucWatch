# Browser/backend lifecycle evidence

Launch with `./scripts/launch.sh`; close with Ctrl-C in the launching terminal.
The backend owns elapsed time, parsing, alerts, commands and raw recording even
when no browser is polling. Saved configuration survives offline relaunch;
commands, drafts and wheel confirmation do not. Each launch creates a fresh
credential. One controller owns actions; reload reuses its session token.

A visible controller refreshes its lease through state polling. Ten seconds
without a heartbeat releases ownership and any held button; another window can
acquire control. Browser blur/hiding/page closure also releases the modeled
button. The separate two-second input lease prevents an abandoned press becoming
prolonged-hold recovery. Expired controllers are rejected, and every browser
intent carries the observed application session epoch. Duplicate identities
never repeat effects, including after their cached response is evicted.

Sequential polling discards superseded responses. A separate five-Hz rendering
loop presents state fetched after actions even when an older poll is delayed.
Read-only windows disable controls; backend loss displays unavailable feedback.
Host boottime detects synthetic resume, invalidating raw assembly, freshness,
pending submissions and retained confirmation without delivering overdue commands
or historical measurement pulses. Returning to telemetry requires fresh data.

`tests/test_lifecycle.py` verifies stale intents, duplicate eviction, controller
expiry, saved restart and synthetic resume through the application/HTTP boundary.
`tests/browser_lifecycle.py` drives actual Chrome reload, delayed response,
competing windows, hidden/frozen page, closure, backend outage and relaunch.
It uses an accelerated 0.7-second ownership lease and synthetic local content.
Expected/observed provenance is retained in
[lifecycle-browser.json](evidence/lifecycle-browser.json).
Physical laptop suspend testing was explicitly omitted by the owner.

Review correction: resume detection now checks the independent host clock even
when simulator/replay behavior uses paused virtual time. Controlled-mode and
replay regressions preserve virtual elapsed time while invalidating telemetry and
pending intent. The actual Canvas pending-preset flow confirms a host resume
cannot deliver overdue submissions or permit late old frames to recover state:
[resume-browser.json](evidence/resume-browser.json).

Supporting reproducible scenario files and their actual browser evidence are
documented in [scenarios.md](scenarios.md). This software evidence contributes to
#31; required live observations and explicit owner review remain incomplete.
