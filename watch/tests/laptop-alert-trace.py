"""Accepted laptop Application seam; raw notifications and controlled time only."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "laptop"))
from eucwatch import Application, ManualClock
from eucwatch.persistence import MemoryStore

clock = ManualClock()
store = MemoryStore()
app = Application(clock=clock, store=store)
previous = 0
observed = []
for operation in json.load(sys.stdin):
    clock.advance(operation["at_s"] - previous)
    previous = operation["at_s"]
    rejected = False
    try:
        if operation["type"] == "raw":
            app.receive(app.session, bytes.fromhex(operation["hex"]))
        elif operation["type"] == "action":
            app.action(operation["action"], **operation.get("payload", {}))
        elif operation["type"] == "restart":
            app = Application(clock=clock, store=store)
        else:
            app.tick()
    except ValueError:
        rejected = True
    state = app.view()
    observed.append({"rejected": rejected, "alerts": state["config"]["alerts"],
                     "revision": state["config"]["revision"], "draft": state["alerts_draft"],
                     "fresh": state["fresh"], "vibration": {**{key: state["vibration"][key]
                     for key in ("events", "current", "queued")}, "event_count": len(state["vibration"]["events"])}})
json.dump(observed, sys.stdout)
