"""The alert editor: the alert draft, its page and the threshold entry. Only Save replaces the saved alerts."""
import math
from copy import deepcopy
from decimal import Decimal
from typing import Any

from .configuration import ALERTS, THRESHOLD_LIMITS, validate_alerts, validate_configuration

LABELS = {"pwm": "High PWM", "speed": "High speed", "battery": "Low wheel battery",
          "lost": "Lost telemetry"}
UNITS = {"pwm": "%", "speed": "km/h", "battery": "%", "lost": ""}
# alerts_begin is Application's: it copies the saved alerts into a new draft.
ACTIONS = ("alerts_update", "alerts_page", "alerts_adjust", "alerts_save", "alerts_cancel",
           "threshold_begin", "threshold_key", "threshold_done", "threshold_cancel")
KEYS = ("1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "0", "backspace")
ENTRY_LENGTH = 8


def number_text(value: Any) -> str:
    """Spell a draft threshold the way JavaScript's String() does, as the browser did.

    A draft holds whatever alerts_update was given until Save validates it.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if not isinstance(value, (int, float)):
        return str(value)
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Infinity" if value > 0 else "-Infinity"
    if abs(value) < 1e21 and (type(value) is int or value.is_integer()):
        return str(int(value))
    if 1e-6 <= abs(value) < 1e21:
        return format(Decimal(repr(value)), "f")
    mantissa, exponent = repr(float(value)).split("e")
    return f"{mantissa.removesuffix('.0')}e{int(exponent):+d}"


class AlertEditor:
    def __init__(self):
        self.draft: dict[str, Any] | None = None
        self.page = 0
        self.entry: dict[str, Any] | None = None
        self.reason = ""

    def open(self, alerts: dict[str, Any]) -> None:
        self.draft = deepcopy(alerts)
        self.page = 0
        self.entry = None
        self.reason = ""

    def close(self) -> None:
        self.draft = None
        self.page = 0
        self.entry = None
        self.reason = ""

    def action(self, name: str, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        """Apply one editor action; alerts_save returns the validated replacement to store."""
        try:
            if name == "alerts_update":
                self.update(payload.pop("alert", None), payload)
            elif name == "alerts_page":
                self.set_page(payload.get("page"))
            elif name == "alerts_adjust":
                self.adjust(payload.get("alert"), payload.get("delta"))
            elif name == "alerts_save":
                return self.validated(config)
            elif name == "alerts_cancel":
                self.close()
            elif name == "threshold_begin":
                self.begin_entry(payload.get("alert"))
            elif name == "threshold_key":
                self.key(payload.get("key"))
            elif name == "threshold_done":
                self.done()
            elif name == "threshold_cancel":
                self.cancel_entry()
        except ValueError as exc:
            # A refused draft action explains itself on the editor; keypad actions
            # leave an earlier explanation in place, as the browser editor did.
            if name.startswith("alerts_") and self.draft is not None:
                self.reason = str(exc)
            raise
        return None

    def validated(self, config: dict[str, Any]) -> dict[str, Any]:
        if self.draft is None:
            raise ValueError("No alert draft is open")
        self.reason = ""
        proposed = deepcopy(config)
        proposed["alerts"] = validate_alerts(self.draft)
        proposed["revision"] += 1
        return validate_configuration(proposed)

    def update(self, alert: Any, changes: dict[str, Any]) -> None:
        if self.draft is None:
            raise ValueError("Open the alert editor before editing")
        if (
            alert not in self.draft
            or not changes
            or set(changes) - ({"enabled"} if alert == "lost" else {"enabled", "threshold"})
        ):
            raise ValueError("Invalid alert draft field")
        self.draft[alert].update(changes)
        self.reason = ""

    def set_page(self, page: Any) -> None:
        if self.draft is None or type(page) is not int or not 0 <= page <= 3:
            raise ValueError("Invalid alert page")
        self.page = page
        self.reason = ""

    def adjust(self, alert: Any, delta: Any) -> None:
        if (
            self.draft is None
            or alert not in THRESHOLD_LIMITS
            or type(delta) is not int
            or delta not in (-1, 1)
        ):
            raise ValueError("Invalid threshold adjustment")
        threshold = self.draft[alert]["threshold"]
        if threshold is not None and (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(threshold)
        ):
            raise ValueError("Invalid threshold adjustment")
        changed = 0 if threshold is None else threshold + delta
        self.draft[alert]["threshold"] = max(0, min(THRESHOLD_LIMITS[alert], changed))
        self.reason = ""

    def begin_entry(self, alert: Any) -> None:
        if self.draft is None or alert not in THRESHOLD_LIMITS:
            raise ValueError("Select a measurement alert threshold")
        threshold = self.draft[alert]["threshold"]
        self.entry = {"alert": alert, "text": "" if threshold is None else number_text(threshold)}

    def key(self, key: Any) -> None:
        if self.entry is None:
            raise ValueError("No threshold input is open")
        if key not in KEYS:
            raise ValueError("Invalid threshold key")
        text = self.entry["text"]
        if key == "backspace":
            self.entry["text"] = text[:-1]
        elif len(text) < ENTRY_LENGTH and not (key == "." and "." in text):
            self.entry["text"] = text + key

    def done(self) -> None:
        if self.entry is None or self.draft is None:
            raise ValueError("No threshold input is open")
        # An entry without a digit ("" or ".") leaves the alert without a threshold.
        text = self.entry["text"]
        value = float(text) if text.strip(".") else None
        if value is not None and value.is_integer():
            value = int(value)
        self.draft[self.entry["alert"]]["threshold"] = value
        self.entry = None
        self.reason = ""

    def cancel_entry(self) -> None:
        if self.entry is None:
            raise ValueError("No threshold input is open")
        self.entry = None

    def _entry_view(self) -> dict[str, Any] | None:
        if self.entry is None:
            return None
        alert = self.entry["alert"]
        return {"alert": alert, "label": LABELS[alert], "unit": UNITS[alert],
                "text": self.entry["text"],
                "display": f"{self.entry['text'] or '—'} {UNITS[alert]}"}

    def view(self) -> dict[str, Any] | None:
        if self.draft is None:
            return None
        alert = ALERTS[self.page]
        setting = self.draft[alert]
        threshold = setting.get("threshold")
        measurement = alert != "lost"
        return {
            "page": self.page,
            "previous_page": (self.page + 3) % 4,
            "next_page": (self.page + 1) % 4,
            "alert": alert,
            "label": LABELS[alert],
            "unit": UNITS[alert],
            "enabled": setting["enabled"],
            "toggle_label": "Enabled" if setting["enabled"] else "Disabled",
            "threshold": None if threshold is None else number_text(threshold),
            "threshold_label": None if not measurement else "Not set" if threshold is None
            else f"{number_text(threshold)} {UNITS[alert]}",
            "note": None if measurement else "1 short pulse",
            "reason": self.reason,
            "entry": self._entry_view(),
            "keys": [{"key": key, "label": "<" if key == "backspace" else key} for key in KEYS],
        }
