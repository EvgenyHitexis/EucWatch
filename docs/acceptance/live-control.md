# Live control software evidence

The application's live preset and horn actions use the already selected
telemetry connection. Discovered FFE1 must explicitly support writes without
response and at least 20-byte payloads. Writes use `response=False` and fixed
20-byte chunks; included settings are serialized, absent dip is omitted.
Each awaited write is bounded by three seconds and the remaining five-second
submission budget. Only two fresh consecutive all-field settings frames after
submission can confirm a preset, with the separate ten-second confirmation limit.
Ended attempts, stale data and replaced sessions stop unsent writes without retry.

`tests/test_live_control.py` exercises the real Application and LiveSession with
a controlled Bleak-compatible client. `tests/test_http_control.py` additionally
checks authenticated UI actions, duplicate request identities, rejection of
browser-supplied completion callbacks, and simulator/live adapter isolation.
The actual Chrome Canvas preset tap and physical-button model pass through
aiohttp to that selected fake connection; expected/observed results and exact
chunk lengths are retained in [live-control-browser.json](evidence/live-control-browser.json).

These checks submit no physical commands. Single-point packet fixtures establish
encoding provenance, not full device range support. Complete multi-setting
behavior, moving implementation acceptance, assist/dip persistence and the
supported audible horn variant remain unverified under #9/#31. Feedback says
“Horn request sent”, never claims audible success. No alternate horn variant,
stop packet, automatic playback or fallback is implemented.
