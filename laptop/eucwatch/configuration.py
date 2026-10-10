"""Versioned complete saved configuration, excluding wheel/session state."""

import math
from copy import deepcopy
from typing import Any

VERSION = 2
DEFAULT_PRESETS = (("Jump", 0, 0, 0), ("Forest", 70, 0, 0),
                   ("Road", 30, 25, 10), ("Drag", 20, 70, 5))
ALERTS = ("pwm", "speed", "battery", "lost")


def validate_preset_name(name: Any) -> None:
    if (not isinstance(name, str) or not name.strip() or len(name) > 24
            or any(ord(c) < 32 for c in name)):
        raise ValueError("Preset name must contain 1–24 readable characters")


def default_configuration() -> dict[str, Any]:
    return {
        "version": VERSION,
        "revision": 0,
        "presets": [
            {"id": slot, "name": name, "configured": True,
             "pedal_sensitivity": pedal, "dynamic_assist": assist,
             "pedal_dip_compensation": dip, "dip_included": False}
            for slot, (name, pedal, assist, dip) in enumerate(DEFAULT_PRESETS, 1)
        ],
        "alerts": {
            **{name: {"enabled": False, "threshold": None} for name in ALERTS[:-1]},
            "lost": {"enabled": True},
        },
    }


def validate_alerts(alerts: Any) -> dict[str, Any]:
    if not isinstance(alerts, dict) or set(alerts) != set(ALERTS):
        raise ValueError("All four alert settings are required")
    for name, setting in alerts.items():
        required = {"enabled"} if name == "lost" else {"enabled", "threshold"}
        if (
            not isinstance(setting, dict)
            or set(setting) != required
            or type(setting["enabled"]) is not bool
        ):
            raise ValueError(f"Invalid {name} alert setting")
        if name == "lost":
            continue
        threshold = setting["threshold"]
        if threshold is None:
            if setting["enabled"]:
                raise ValueError(f"A threshold is required to enable {name}")
        elif (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(threshold)
            or not 0 <= threshold <= (3276.7 if name == "speed" else 100)
        ):
            raise ValueError(
                f"Invalid {name} threshold (0–{'3276.7 km/h' if name == 'speed' else '100%'})"
            )
    return deepcopy(alerts)


def validate_configuration(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict) or set(config) != {
        "version",
        "revision",
        "presets",
        "alerts",
    }:
        raise ValueError("A complete configuration is required")
    if type(config["version"]) is not int or config["version"] not in (1, VERSION):
        raise ValueError("Unsupported configuration version; review required")
    if type(config["revision"]) is not int or config["revision"] < 0:
        raise ValueError("Invalid configuration revision")
    validate_alerts(config["alerts"])
    presets = config["presets"]
    if not isinstance(presets, list) or len(presets) != 4:
        raise ValueError("Exactly four fixed preset slots are required")
    for slot, preset in enumerate(presets, 1):
        if (
            not isinstance(preset, dict)
            or preset.get("id") != slot
            or type(preset.get("id")) is not int
        ):
            raise ValueError("Preset slot identity must be 1 through 4 in order")
        if type(preset.get("configured")) is not bool:
            raise ValueError("Preset configured state must be explicit")
        validate_preset_name(preset.get("name"))
        required = {"id", "name", "configured"}
        if preset["configured"]:
            required |= {"pedal_sensitivity", "dynamic_assist"}
        optional = {"pedal_dip_compensation"} if preset["configured"] else set()
        if config["version"] == VERSION:
            if not preset["configured"] or type(preset.get("dip_included")) is not bool:
                raise ValueError("Configured preset with explicit dip inclusion is required")
            required |= {"pedal_dip_compensation", "dip_included"}
            optional = set()
        if not required <= set(preset) or set(preset) - required - optional:
            raise ValueError("Invalid preset fields")
        for field in ("pedal_sensitivity", "dynamic_assist", "pedal_dip_compensation"):
            if field in preset and (
                type(preset[field]) is not int or not 0 <= preset[field] <= 100
            ):
                raise ValueError(f"{field} must be a whole percentage from 0 to 100")
    normalized = deepcopy(config)
    if config["version"] == 1:
        defaults = default_configuration()["presets"]
        for index, preset in enumerate(normalized["presets"]):
            if not preset["configured"]:
                normalized["presets"][index] = defaults[index]
            else:
                preset["dip_included"] = "pedal_dip_compensation" in preset
                preset.setdefault("pedal_dip_compensation", defaults[index]["pedal_dip_compensation"])
        normalized["version"] = VERSION
    return normalized
