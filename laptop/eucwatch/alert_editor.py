"""The alert editor: the alert draft, its page and the threshold entry. Only Save replaces the saved alerts.

It follows watch/alert-editor.js rule for rule; docs/acceptance/scenarios/alert-editor-keys.json drives both.
"""
import math
import re
from copy import deepcopy
from decimal import Decimal
from typing import Any

from .configuration import ALERT_DEFINITIONS, ALERTS, validate_alerts, validate_configuration

# alerts_begin is Application's: it decides when editing may open and copies the saved alerts into a new draft.
ACTIONS = ("alerts_update", "alerts_page", "alerts_adjust", "alerts_save", "alerts_cancel",
           "threshold_begin", "threshold_key", "threshold_done", "threshold_cancel")
KEYS = ("1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "0", "backspace")
ENTRY_LENGTH = 8
OUT_OF_RANGE = "Threshold outside supported range"
# The keypad header is narrow: under the alert's name it shows this short form of any reason, as watch/render.js does.
REFUSED_SHORT = "Invalid threshold"
# The entry texts Set value reads as a number, as JavaScript's Number() reads them; any other text is no number.
_NUMBER = re.compile(r"(\d+\.?\d*|\.\d+)(e[+-]?\d+)?")


def number_text(value: Any) -> str:
    """Spell a draft threshold the way JavaScript's String() does, as the watch does.

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


def _measured(alert: Any) -> bool:
    return isinstance(alert, str) and alert in ALERT_DEFINITIONS and ALERT_DEFINITIONS[alert].limit is not None


class AlertEditor:
    """One alert draft at a time.

    - open(alerts) starts a draft of those alerts on page 0; close() discards the draft and the entry.
    - is_open(): whether a draft is open; entry_open(): whether a threshold entry is open.
    - action(name, payload, config): one name from ACTIONS. A refused action raises ValueError and
      leaves the reason alone, except that a refused Save or Set value sets it. Every other accepted
      action clears the reason; an accepted Save leaves it to the caller's close(). Returns None,
      {'leave': True} for Cancel (the draft is already discarded), or {'save': replacement}, the
      validated replacement configuration, for the caller to persist.
    - view(): the alert draft, the alert editor view (None without a draft) and every alert's
      label, unit and limit, keyed as the Application publishes them.
    """

    def __init__(self):
        self._draft: dict[str, Any] | None = None
        self._page = 0
        self._entry: dict[str, Any] | None = None
        self._reason = ""

    def open(self, alerts: dict[str, Any]) -> None:
        self._draft = deepcopy(alerts)
        self._page = 0
        self._entry = None
        self._reason = ""

    def close(self) -> None:
        self._draft = None
        self._page = 0
        self._entry = None
        self._reason = ""

    def is_open(self) -> bool:
        return self._draft is not None

    def entry_open(self) -> bool:
        return self._entry is not None

    def action(self, name: str, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        if name == "alerts_save":
            return {"save": self._save(config)}
        if name == "alerts_cancel":
            self.close()
            return {"leave": True}
        if name == "alerts_update":
            self._update(payload)
        elif name == "alerts_page":
            self._set_page(payload.get("page"))
        elif name == "alerts_adjust":
            self._adjust(payload.get("alert"), payload.get("delta"))
        elif name == "threshold_begin":
            self._begin_entry(payload.get("alert"))
        elif name == "threshold_key":
            self._key(payload.get("key"))
        elif name == "threshold_done":
            self._done()
        elif name == "threshold_cancel":
            self._entry = None
        else:
            raise ValueError(f"Unknown action: {name}")
        self._reason = ""
        return None

    def _save(self, config: dict[str, Any]) -> dict[str, Any]:
        if self._draft is None:
            raise ValueError("No alert draft is open")
        proposed = deepcopy(config)
        try:
            proposed["alerts"] = validate_alerts(self._draft)
            proposed["revision"] += 1
            return validate_configuration(proposed)
        except ValueError as exc:
            self._reason = str(exc)
            raise

    def _update(self, payload: dict[str, Any]) -> None:
        alert = payload.get("alert")
        if self._draft is None or not isinstance(alert, str) or alert not in self._draft:
            raise ValueError("Open a valid alert draft before editing")
        changes = {key: value for key, value in payload.items() if key != "alert"}
        if not changes or set(changes) - ({"enabled"} if alert == "lost" else {"enabled", "threshold"}):
            raise ValueError("Invalid alert draft field")
        self._draft[alert].update(changes)

    def _set_page(self, page: Any) -> None:
        if self._draft is None or type(page) is not int or not 0 <= page <= 3:
            raise ValueError("Invalid alert page")
        self._page = page

    def _adjust(self, alert: Any, delta: Any) -> None:
        if self._draft is None or not _measured(alert) or type(delta) is not int or delta not in (-1, 1):
            raise ValueError("Invalid threshold adjustment")
        threshold = self._draft[alert]["threshold"]
        if threshold is not None and (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(threshold)
        ):
            raise ValueError("Invalid threshold adjustment")
        changed = 0 if threshold is None else threshold + delta
        self._draft[alert]["threshold"] = max(0, min(ALERT_DEFINITIONS[alert].limit, changed))

    def _begin_entry(self, alert: Any) -> None:
        if self._draft is None or not _measured(alert):
            raise ValueError("Select a measurement alert threshold")
        threshold = self._draft[alert]["threshold"]
        self._entry = {"alert": alert, "text": "" if threshold is None else number_text(threshold)}

    def _key(self, key: Any) -> None:
        if self._entry is None:
            raise ValueError("No threshold entry is open")
        if key not in KEYS:
            raise ValueError("Invalid threshold key")
        text = self._entry["text"]
        if key == "backspace":
            self._entry["text"] = text[:-1]
        elif len(text) < ENTRY_LENGTH and not (key == "." and "." in text):
            self._entry["text"] = text + key

    def _done(self) -> None:
        if self._entry is None or self._draft is None:
            raise ValueError("No threshold entry is open")
        alert, text = self._entry["alert"], self._entry["text"]
        value: int | float | None = None
        if text:
            # A lone "." or any other text that is not a number is refused like a value out of range.
            number = float(text) if _NUMBER.fullmatch(text) else math.nan
            if not math.isfinite(number) or not 0 <= number <= ALERT_DEFINITIONS[alert].limit:
                self._reason = OUT_OF_RANGE
                raise ValueError(OUT_OF_RANGE)
            value = int(number) if number.is_integer() else number
        self._draft[alert]["threshold"] = value
        self._entry = None

    def _entry_view(self) -> dict[str, Any] | None:
        if self._entry is None:
            return None
        alert = self._entry["alert"]
        label, unit, _ = ALERT_DEFINITIONS[alert]
        return {"alert": alert, "label": label, "unit": unit, "text": self._entry["text"],
                "display": f"{self._entry['text'] or '—'} {unit}",
                "notice": REFUSED_SHORT if self._reason else ""}

    def _editor_view(self) -> dict[str, Any] | None:
        if self._draft is None:
            return None
        alert = ALERTS[self._page]
        label, unit, limit = ALERT_DEFINITIONS[alert]
        setting = self._draft[alert]
        threshold = setting.get("threshold")
        measurement = limit is not None
        return {
            "page": self._page,
            "previous_page": (self._page + 3) % 4,
            "next_page": (self._page + 1) % 4,
            "alert": alert,
            "label": label,
            "unit": unit,
            "enabled": setting["enabled"],
            "toggle_label": "Enabled" if setting["enabled"] else "Disabled",
            "threshold": None if threshold is None else number_text(threshold),
            "threshold_label": None if not measurement else "Not set" if threshold is None
            else f"{number_text(threshold)} {unit}",
            "note": None if measurement else "1 short pulse",
            "reason": self._reason,
            "entry": self._entry_view(),
            "keys": [{"key": key, "label": "<" if key == "backspace" else key} for key in KEYS],
        }

    def view(self) -> dict[str, Any]:
        return {
            "alerts_draft": deepcopy(self._draft),
            "alert_editor": self._editor_view(),
            "alert_definitions": {name: definition._asdict() for name, definition in ALERT_DEFINITIONS.items()},
        }
