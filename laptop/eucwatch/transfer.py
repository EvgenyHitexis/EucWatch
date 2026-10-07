"""Explicit saved-configuration exchange with a labelled simulated watch."""

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from .configuration import validate_configuration
from .persistence import ConfigStore
from .transfer_protocol import ConfigurationProtocol, SimulatedWatch


def fields(content: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    result = {}
    for name, value in content.items():
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(value, dict):
            result.update(fields(value, path))
        elif isinstance(value, list):
            for index, item in enumerate(value, 1):
                result.update(fields(item, f"{path}.{index}"))
        else:
            result[path] = value
    return result


class ConfigurationTransfer:
    def __init__(
        self,
        laptop_store: ConfigStore,
        watch_store: ConfigStore,
        shared_store: ConfigStore,
        exchange: Callable[[bytes], bytes] | None = None,
    ):
        self.active = False
        self.status = "idle"
        self.error: str | None = None
        endpoint = SimulatedWatch(watch_store)
        self.protocol = ConfigurationProtocol(exchange or endpoint.exchange)
        self.laptop_store = laptop_store
        self.shared_store = shared_store
        self.watch = deepcopy(endpoint.active)
        self.error = endpoint.error
        self.base = None
        try:
            self.base = shared_store.load()
        except (OSError, ValueError) as exc:
            self.error = f"Shared configuration base requires review: {exc}"
        if self.error is not None:
            self.status = "failed"
        self.preview: dict[str, Any] | None = None
        self.previous_mode = "idle"
        self.previous_simulating = False

    def begin(self, config: dict[str, Any], mode: str, simulating: bool) -> None:
        self.active = True
        self.previous_mode = mode
        self.previous_simulating = simulating
        self.review(config)

    def review(self, config: dict[str, Any]) -> None:
        self._require_active()
        self.preview = None
        self.error = None
        try:
            self.watch = self.protocol.read()
        except (OSError, ValueError) as exc:
            self.status = "failed"
            self.error = f"Saved watch configuration could not be read: {exc}"
            return
        laptop = validate_configuration(config)
        left, right = (
            fields(laptop["alerts"], "alerts"),
            fields(self.watch["alerts"], "alerts"),
        )
        conflicts = [
            {"path": path, "laptop": value, "watch": right[path]}
            for path, value in left.items()
            if value != right[path]
        ]
        self.preview = {
            "laptop_revision": laptop["revision"],
            "watch_revision": self.watch["revision"],
            "laptop": laptop,
            "watch": deepcopy(self.watch),
            "candidate": None,
            "changes": [],
            "conflicts": conflicts,
            "choices": {entry["path"]: None for entry in conflicts},
        }
        self.status = "review"
        self._candidate()

    def _candidate(self) -> None:
        preview = self.preview
        assert preview is not None
        proposed = deepcopy(preview["laptop"])
        proposed["revision"] = (
            max(preview["laptop_revision"], preview["watch_revision"]) + 1
        )
        for path, side in preview["choices"].items():
            if side == "watch":
                _alerts, alert, field = path.split(".")
                proposed["alerts"][alert][field] = preview["watch"]["alerts"][alert][
                    field
                ]
        old, new = fields(preview["watch"]), fields(proposed)
        preview["changes"] = [
            {"path": path, "watch": old.get(path), "proposed": new.get(path)}
            for path in sorted(old.keys() | new.keys())
            if path != "revision" and old.get(path) != new.get(path)
        ]
        preview["candidate"] = None
        if any(side is None for side in preview["choices"].values()):
            return
        try:
            preview["candidate"] = validate_configuration(proposed)
            self.error = None
        except ValueError as exc:
            self.error = f"Chosen configuration is invalid: {exc}"

    def choose(self, path: Any, side: Any) -> None:
        self._require_active()
        if self.preview is None:
            raise ValueError("Review saved watch content before choosing values")
        if side not in ("laptop", "watch") or not isinstance(path, str):
            raise ValueError("Choose the laptop or watch value for an alert field")
        if path == "all":
            for field in self.preview["choices"]:
                self.preview["choices"][field] = side
        elif path in self.preview["choices"]:
            self.preview["choices"][path] = side
        else:
            raise ValueError("This field does not need a transfer choice")
        self._candidate()

    def send(self, config: dict[str, Any]) -> dict[str, Any] | None:
        self._require_active()
        preview = self.preview
        if preview is None or preview["candidate"] is None:
            raise ValueError(
                "Review and resolve the complete configuration before Transfer"
            )
        if config != preview["laptop"]:
            raise ValueError("Laptop saved content changed after preview; review again")
        try:
            if self.protocol.read() != preview["watch"]:
                raise ValueError(
                    "Watch saved content changed after preview; review again"
                )
            self.protocol.upload(preview["candidate"], preview["watch"])
            committed = self.protocol.read()
            self.watch = committed
            if committed != preview["candidate"]:
                raise ValueError(
                    "Committed watch content/revision did not match the reviewed configuration"
                )
            self.laptop_store.save(committed)
            self.shared_store.save(committed)
        except (OSError, ValueError) as exc:
            self.status = "failed"
            self.error = (
                f"Configuration transfer failed; read saved content before retry: {exc}"
            )
            return None
        self.base = deepcopy(committed)
        self.preview = None
        self.active = False
        self.status = "success"
        self.error = None
        return committed

    def cancel(self) -> None:
        self._require_active()
        self.protocol.request("abort")
        self.preview = None
        self.error = None
        self.status = "cancelled"

    def leave(self) -> None:
        self.active = False
        self.preview = None

    def _require_active(self) -> None:
        if not self.active:
            raise ValueError("Enter configuration transfer on the watch first")

    def view(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "endpoint": "Simulated watch",
            "status": self.status,
            "error": self.error,
            "watch_revision": self.watch["revision"],
            "watch_config": deepcopy(self.watch),
            "preview": deepcopy(self.preview),
        }
