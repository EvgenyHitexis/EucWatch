"""Serialized preset requests confirmed by fresh settings, never receipts alone."""

from collections.abc import Callable
from copy import deepcopy
from typing import Any
import zlib

FIELDS = {"pedal_sensitivity": (0x0F, 10, 50),
          "dynamic_assist": (0x1F, 26, 66),
          "pedal_dip_compensation": (0x21, 28, 68)}
SUBMISSION_LIMIT = 5.0
CONFIRMATION_LIMIT = 10.0


def command(field: str, value: int) -> bytes:
    identifier, offset, _readback = FIELDS[field]
    if type(value) is not int or not 0 <= value <= 100:
        raise ValueError("Setting must be a whole percentage from 0 to 100")
    payload = bytearray([0x80] * (offset + 1))
    payload[:7] = b"LdAp" + bytes((identifier, 1, 2))
    payload[offset] = value
    return bytes(payload) + zlib.crc32(payload).to_bytes(4, "big")


class PresetControl:
    def __init__(self, send: Callable[[dict[str, Any]], None],
                 event: Callable[[dict[str, Any]], None]):
        self.send = send
        self.event = event
        self.attempt: dict[str, Any] | None = None
        self.confirmed: dict[str, Any] | None = None
        self.actual: dict[str, int | None] | None = None
        self.actual_session: int | None = None
        self.next_id = 1

    @property
    def pending(self) -> bool:
        return self.attempt is not None and self.attempt["pending"]

    def start(self, preset: dict[str, Any], revision: int, session: int, now: float, *, kind: str = "preset") -> None:
        self.confirmed = None
        fields = {name: {"requested": preset[name], "actual": None, "state": "unknown",
                         "submitted_s": None, "matches": 0}
                  for name in FIELDS if name in preset and
                  (name != "pedal_dip_compensation" or preset.get("dip_included", kind == "editor"))}
        self.attempt = {"kind": kind, "id": self.next_id, "slot": preset["id"], "name": preset["name"],
                        "revision": revision, "session": session, "status": "submitting",
                        "pending": True, "requested_s": now, "submitted_s": None,
                        "finished_s": None, "reason": "", "fields": fields,
                        "readbacks": [], "matching_frames": 0, "next_index": 0,
                        "awaiting": None}
        self.next_id += 1
        self._dispatch(now)

    def _dispatch(self, now: float) -> None:
        attempt = self.attempt
        assert attempt is not None
        index = attempt["next_index"]
        name = list(attempt["fields"])[index]
        value = attempt["fields"][name]["requested"]
        attempt["awaiting"] = index
        row = {"attempt": attempt["id"], "session": attempt["session"],
               "index": index, "field": name, "value": value,
               "packet_hex": command(name, value).hex(), "at_s": now}
        self.event({"event": "submission", **row})
        self.send(row)

    def result(self, attempt_id: int, session: int, index: int,
               success: bool, now: float, error: str = "") -> None:
        attempt = self.attempt
        if not self.pending or attempt is None or (attempt_id, session, index) != (attempt["id"], attempt["session"], attempt["awaiting"]):
            return
        self.event({"event": "result", "attempt": attempt_id, "session": session,
                    "index": index, "success": success, "at_s": now, "error": error})
        if not success:
            self.finish(now, error or "Transport submission failed")
            return
        name = list(attempt["fields"])[index]
        attempt["fields"][name]["submitted_s"] = now
        attempt["next_index"] += 1
        attempt["awaiting"] = None
        if attempt["next_index"] == len(attempt["fields"]):
            attempt["status"] = "confirming"
            attempt["submitted_s"] = now
        else:
            self._dispatch(now)

    def tick(self, now: float, *, fresh: bool, session: int, revision: int) -> None:
        if self.actual_session != session:
            self.actual = None
        if self.confirmed is not None and (not fresh or session != self.confirmed["session"] or revision != self.confirmed["revision"]):
            self.confirmed = None
        attempt = self.attempt
        if not self.pending or attempt is None:
            return
        reason = None
        if session != attempt["session"]:
            reason = "Wheel session ended"
        elif revision != attempt["revision"]:
            reason = "Saved configuration changed"
        elif not fresh:
            reason = "Telemetry is stale or disconnected"
        elif attempt["submitted_s"] is None and now - attempt["requested_s"] >= SUBMISSION_LIMIT - 1e-9:
            reason = "Submission timeout"
        elif attempt["submitted_s"] is not None and now - attempt["submitted_s"] >= CONFIRMATION_LIMIT - 1e-9:
            reason = "Confirmation timeout"
        if reason:
            self.finish(now, reason)

    def observe(self, values: dict[str, int | None], now: float, session: int) -> None:
        self.actual = deepcopy(values)
        self.actual_session = session
        if self.confirmed and any(values.get(name) != value for name, value in self.confirmed["values"].items()):
            self.confirmed = None
        attempt = self.attempt
        if not self.pending or attempt is None or session != attempt["session"] or now <= attempt["requested_s"]:
            return
        attempt["readbacks"].append(now)
        del attempt["readbacks"][:-64]
        for name, field in attempt["fields"].items():
            actual = values.get(name)
            field["actual"] = actual
            if field["submitted_s"] is None or now <= field["submitted_s"] or actual is None:
                field["matches"] = 0
                field["state"] = "unknown"
            elif actual != field["requested"]:
                field["matches"] = 0
                field["state"] = "mismatched"
            else:
                field["matches"] += 1
                field["state"] = "confirmed" if field["matches"] >= 2 else "unknown"
        if attempt["submitted_s"] is None or now <= attempt["submitted_s"]:
            return
        if all(values.get(name) == field["requested"] for name, field in attempt["fields"].items()):
            attempt["matching_frames"] += 1
        else:
            attempt["matching_frames"] = 0
        if attempt["matching_frames"] >= 2:
            attempt["status"] = "Confirmed"
            attempt["pending"] = False
            attempt["finished_s"] = now
            self.confirmed = {"kind": attempt["kind"], "slot": attempt["slot"], "name": attempt["name"],
                              "revision": attempt["revision"], "session": session,
                              "values": {name: field["requested"] for name, field in attempt["fields"].items()}}

    def finish(self, now: float, reason: str) -> None:
        if not self.pending or self.attempt is None:
            return
        attempt = self.attempt
        partial = any(field["state"] == "confirmed" for field in attempt["fields"].values())
        attempt["status"] = "Partially applied" if partial else "Not confirmed"
        attempt["pending"] = False
        attempt["reason"] = reason
        attempt["finished_s"] = now
        attempt["awaiting"] = None
        self.confirmed = None

    def view(self) -> dict[str, Any] | None:
        return deepcopy(self.attempt)
