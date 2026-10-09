"""Fixed-slot local definitions and freshly seeded wheel-owned editor state.

The application's percentage contract is 0–100 for the three included controls.
Source interpretation and the manufacturer's sensitivity range are documented
in https://github.com/EvgenyHitexis/EucWatch/issues/6. Stationary one-point
roundtrips do not establish the whole range on the owner's wheel; #9 remains the
hardware evidence gate. Optional dip omission is represented by an absent key.
"""

from copy import deepcopy
from typing import Any

from .configuration import validate_configuration

PERCENT_FIELDS = frozenset(("pedal_sensitivity", "dynamic_assist", "pedal_dip_compensation"))


def validate_slot(slot: Any) -> int:
    if type(slot) is not int or not 1 <= slot <= 4:
        raise ValueError("Choose one of the four fixed preset slots")
    return slot


def begin(config: dict[str, Any], slot: Any) -> dict[str, Any]:
    return deepcopy(config["presets"][validate_slot(slot) - 1])


def update(draft: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    if not changes or set(changes) - {"name", *PERCENT_FIELDS}:
        raise ValueError("Invalid preset draft field")
    proposed = deepcopy(draft)
    for field, value in changes.items():
        if field == "pedal_dip_compensation" and value is None:
            proposed["dip_included"] = False
        else:
            proposed[field] = value
            if field == "pedal_dip_compensation":
                proposed["dip_included"] = True
            if field in PERCENT_FIELDS:
                proposed["configured"] = True
    return proposed


def cleared(config: dict[str, Any], slot: Any) -> dict[str, Any]:
    preset = begin(config, slot)
    from .configuration import default_configuration
    return default_configuration()["presets"][preset["id"] - 1]


def replacement(config: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    proposed = deepcopy(config)
    proposed["presets"][validate_slot(draft["id"]) - 1] = deepcopy(draft)
    proposed["revision"] += 1
    return validate_configuration(proposed)


READBACK_LIMIT = 5.0


class PresetEditor:
    """One session-bound editor; opening never invents or writes riding values."""

    def __init__(self):
        self.request: dict[str, Any] | None = None
        self.draft: dict[str, Any] | None = None
        self.values: dict[str, int | None] | None = None

    def open(self, slot: Any, session: int, now: float) -> None:
        self.draft = None
        self.values = None
        self.request = {"slot": validate_slot(slot), "session": session,
                        "requested_s": now, "status": "waiting", "reason": "",
                        "seeded_s": None}

    def tick(self, now: float, session: int, connected: bool) -> None:
        request = self.request
        if request is None or request["status"] == "unavailable":
            return
        reason = ""
        if request["session"] != session or not connected:
            reason = "Wheel session ended; reopen for fresh settings"
        elif request["status"] == "waiting" and now - request["requested_s"] >= READBACK_LIMIT - 1e-9:
            reason = "Current wheel settings unavailable (readback timeout)"
        if reason:
            request.update(status="unavailable", reason=reason)
            self.draft = None
            self.values = None

    def observe(self, config: dict[str, Any], values: dict[str, int | None],
                session: int, now: float) -> None:
        request = self.request
        if request is None or request["session"] != session or request["status"] == "unavailable":
            return
        self.values = deepcopy(values)
        if request["status"] != "waiting" or any(values.get(name) is None for name in PERCENT_FIELDS):
            return
        saved = begin(config, request["slot"])
        self.draft = {"id": saved["id"], "name": saved["name"], "configured": True,
                      "pedal_sensitivity": values["pedal_sensitivity"],
                      "dynamic_assist": values["dynamic_assist"],
                      "pedal_dip_compensation": saved["pedal_dip_compensation"],
                      "dip_included": saved["dip_included"]}
        if saved["dip_included"]:
            self.draft["pedal_dip_compensation"] = values["pedal_dip_compensation"]
        request.update(status="ready", seeded_s=now)

    def close(self) -> None:
        self.request = None
        self.draft = None
        self.values = None

    def view(self) -> dict[str, Any] | None:
        return deepcopy(self.request)
