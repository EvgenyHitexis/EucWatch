"""Fixed-slot editor drafts. Editing never receives a wheel transport.

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
            proposed.pop(field, None)
        else:
            proposed[field] = value
            if field in PERCENT_FIELDS:
                proposed["configured"] = True
    return proposed


def cleared(config: dict[str, Any], slot: Any) -> dict[str, Any]:
    preset = begin(config, slot)
    return {"id": preset["id"], "name": preset["name"], "configured": False}


def replacement(config: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    proposed = deepcopy(config)
    proposed["presets"][validate_slot(draft["id"]) - 1] = deepcopy(draft)
    proposed["revision"] += 1
    return validate_configuration(proposed)
