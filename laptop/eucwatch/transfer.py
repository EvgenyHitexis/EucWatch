"""Explicit saved-configuration exchange with a labelled simulated watch."""

from collections.abc import Callable
from copy import deepcopy
from typing import Any
import json
import os
import tempfile

from .configuration import validate_configuration
from .persistence import ConfigStore, FileStore, MAX_CONFIG_BYTES
from .transfer_protocol import ConfigurationProtocol, SimulatedWatch, ScenarioTransport


class TransferJournal:
    """Bounded saved transaction evidence, separate from user configuration."""

    def __init__(self, store: ConfigStore):
        self.path = store.path.with_name("transfer_transaction.json") if isinstance(store, FileStore) else None
        self.content: dict[str, Any] | None = None

    def _validate(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict) or set(value) != {"schema", "pending"} or type(value["schema"]) is not int or value["schema"] != 1:
            raise ValueError("Unsupported transfer transaction journal")
        pending = value["pending"]
        if pending is None:
            return None
        if not isinstance(pending, dict) or set(pending) != {"candidate", "laptop", "watch"}:
            raise ValueError("Incomplete transfer transaction journal")
        return {name: validate_configuration(config) for name, config in pending.items()}

    def load(self) -> dict[str, Any] | None:
        if self.path is None:
            return deepcopy(self.content)
        backup = self.path.with_suffix(".last-good.json")
        if not self.path.exists() and not backup.exists():
            return None
        for path in (self.path, backup):
            try:
                with path.open("rb") as handle:
                    data = handle.read(3 * MAX_CONFIG_BYTES + 1025)
                if len(data) > 3 * MAX_CONFIG_BYTES + 1024:
                    raise ValueError("Transfer journal exceeds its bounded size")
                return self._validate(json.loads(data))
            except (OSError, ValueError, RecursionError):
                continue
        raise ValueError("Saved transfer transaction cannot be validated; read saved content for review")

    def save(self, pending: dict[str, Any] | None) -> None:
        normalized = self._validate({"schema": 1, "pending": pending})
        data = json.dumps({"schema": 1, "pending": normalized}, ensure_ascii=False, allow_nan=False, sort_keys=True).encode()
        if len(data) > 3 * MAX_CONFIG_BYTES + 1024:
            raise ValueError("Transfer journal exceeds its bounded size")
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            for path in (self.path.with_suffix(".last-good.json"), self.path):
                fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
                try:
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(data)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temporary, path)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
            directory = os.open(self.path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        self.content = normalized


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
        self.endpoint = endpoint
        self.simulated = exchange is None
        self.scenario = ScenarioTransport(endpoint)
        self.protocol = ConfigurationProtocol(exchange or self.scenario.exchange)
        self.laptop_store = laptop_store
        self.shared_store = shared_store
        self.watch = deepcopy(endpoint.active)
        self.error = endpoint.error
        self.base = None
        try:
            loaded_base = shared_store.load()
            self.base = None if loaded_base is None else validate_configuration(loaded_base)
        except (OSError, ValueError) as exc:
            self.error = f"Shared configuration base requires review: {exc}"
        if self.error is not None:
            self.status = "failed"
        self.preview: dict[str, Any] | None = None
        self.previous_mode = "idle"
        self.previous_simulating = False
        self.journal = TransferJournal(laptop_store)
        self.journal_error: str | None = None
        self.local_saved: dict[str, Any] | None = None
        try:
            self.pending = self.journal.load()
        except (OSError, ValueError) as exc:
            self.pending = None
            self.journal_error = str(exc)
        if self.pending is not None or self.journal_error:
            self.status = "unknown"
            self.error = "Outcome unknown; saved transaction requires explicit readback reconciliation"

    def configure_scenario(self, values: dict[str, Any]) -> None:
        if not self.simulated:
            raise ValueError("Fault scenarios require the default simulated endpoint")
        self.scenario.configure(values)

    def watch_edit(self, payload: dict[str, Any]) -> None:
        if not self.simulated:
            raise ValueError("Saved watch scenario editing requires the default simulated endpoint")
        alert = payload.get("alert")
        if alert not in ("pwm", "speed", "battery", "lost"):
            raise ValueError("Choose a simulated watch alert")
        values = {key: value for key, value in payload.items() if key != "alert"}
        if not values or set(values) - ({"enabled"} if alert == "lost" else {"enabled", "threshold"}):
            raise ValueError("Invalid simulated watch alert field")
        proposed = self.protocol.read()
        proposed["alerts"][alert].update(values)
        proposed["revision"] += 1
        self.endpoint.store.save(validate_configuration(proposed))
        self.watch = deepcopy(proposed)

    def begin(self, config: dict[str, Any], mode: str, simulating: bool) -> None:
        self.active = True
        self.previous_mode = mode
        self.previous_simulating = simulating
        if self.pending is None and self.journal_error is None:
            self.review(config)
        else:
            self.status = "unknown"
            self.error = "Outcome unknown; read saved watch content before deciding success or retry"

    def review(self, config: dict[str, Any]) -> None:
        self._require_active()
        if self.pending is not None or self.journal_error is not None:
            raise ValueError("Read back the unknown transfer before preparing another preview")
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
        baseline = None if self.base is None else fields(self.base["alerts"], "alerts")
        automatic = {}
        for path, value in left.items():
            if value == right[path] or baseline is None:
                continue
            if value == baseline[path]:
                automatic[path] = "watch"
            elif right[path] == baseline[path]:
                automatic[path] = "laptop"
        conflicts = [
            {"path": path, "laptop": value, "watch": right[path]}
            for path, value in left.items()
            if value != right[path] and path not in automatic
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
            "automatic": automatic,
            "base_revision": None if self.base is None else self.base["revision"],
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
        for path, side in {**preview["automatic"], **preview["choices"]}.items():
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
        self.local_saved = None
        if self.pending is not None or self.journal_error is not None:
            raise ValueError("Outcome unknown; reconcile saved content before retrying")
        preview = self.preview
        if preview is None or preview["candidate"] is None:
            raise ValueError(
                "Review and resolve the complete configuration before Transfer"
            )
        if config != preview["laptop"]:
            self.review(config)
            self.error = "Laptop saved content changed after preview; refreshed reconciliation requires review again"
            raise ValueError(self.error)
        try:
            saved_laptop = self.laptop_store.load()
            if saved_laptop is not None and saved_laptop != preview["laptop"]:
                self.local_saved = validate_configuration(saved_laptop)
                self.review(self.local_saved)
                self.status = "failed"
                self.error = "Laptop saved content changed after preview; refreshed reconciliation requires review again"
                return None
            if self.protocol.read() != preview["watch"]:
                self.review(config)
                self.status = "failed"
                self.error = "Watch saved content changed after preview; refreshed reconciliation requires review again"
                return None
            self.protocol.upload(preview["candidate"], preview["watch"], lambda: self._mark_pending(preview))
            committed = self.protocol.read()
            self.watch = committed
            if committed != preview["candidate"]:
                raise ValueError(
                    "Committed watch content/revision did not match the reviewed configuration"
                )
            return self._complete(committed)
        except (OSError, ValueError) as exc:
            self._read_local_saved()
            self.status = "unknown" if self.pending is not None else "failed"
            self.error = (
                f"{'Outcome unknown' if self.pending is not None else 'Configuration transfer failed'}; read saved content before retry: {exc}"
            )
            return None

    def _read_local_saved(self) -> None:
        try:
            saved = self.laptop_store.load()
            self.local_saved = None if saved is None else validate_configuration(saved)
        except (OSError, ValueError):
            self.local_saved = None

    def _mark_pending(self, preview: dict[str, Any]) -> None:
        saved_laptop = self.laptop_store.load()
        if saved_laptop is not None and saved_laptop != preview["laptop"]:
            self.local_saved = validate_configuration(saved_laptop)
            self.review(self.local_saved)
            raise ValueError("Laptop saved content changed during staging; refreshed reconciliation requires review again")
        pending = {"candidate": deepcopy(preview["candidate"]), "laptop": deepcopy(preview["laptop"]), "watch": deepcopy(preview["watch"])}
        self.journal.save(pending)
        self.pending = pending

    def _complete(self, committed: dict[str, Any]) -> dict[str, Any]:
        self.laptop_store.save(committed)
        self.shared_store.save(committed)
        self.journal.save(None)
        self.base = deepcopy(committed)
        self.pending = None
        self.preview = None
        self.active = False
        self.status = "success"
        self.error = None
        self.scenario.committed = False
        return committed

    def reconcile(self, config: dict[str, Any]) -> dict[str, Any] | None:
        self._require_active()
        self.local_saved = None
        pending = self.pending
        if pending is None and self.journal_error is None:
            raise ValueError("No unknown transfer needs readback reconciliation")
        try:
            saved_laptop = self.laptop_store.load()
            if saved_laptop is not None:
                saved_laptop = validate_configuration(saved_laptop)
                if saved_laptop != config:
                    self.local_saved = saved_laptop
                config = saved_laptop
            actual = self.protocol.read()
            self.watch = actual
            if pending is not None and actual == pending["candidate"] and config in (pending["laptop"], pending["candidate"]):
                return self._complete(actual)
            self.journal.save(None)
        except (OSError, ValueError) as exc:
            self._read_local_saved()
            self.status = "unknown"
            self.error = f"Outcome unknown; saved readback reconciliation failed: {exc}"
            return None
        self.pending = None
        self.journal_error = None
        self.scenario.committed = False
        self.review(config)
        self.error = "Saved content changed or activation was not confirmed; review the refreshed candidate before an explicit transfer"
        return None

    def cancel(self) -> None:
        self._require_active()
        if self.pending is not None or self.journal_error is not None:
            raise ValueError("Read active configuration before cancelling an unknown outcome")
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
            "scenario": deepcopy(self.scenario.values),
            "pending": None if self.pending is None else {"candidate_revision": self.pending["candidate"]["revision"], "laptop_revision": self.pending["laptop"]["revision"], "watch_revision": self.pending["watch"]["revision"]},
        }
