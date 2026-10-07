"""Versioned protocol-input scenarios; behavior and clocks remain in Application."""

import json
import math
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol

from .application import Application
from .simulator import Simulator

MAX_BYTES = 32 * 1024
MAX_STEPS = 64
DEFAULT_STEPS = [{"action": "advance", "seconds": 0.2},
                 {"action": "advance", "seconds": 0.2},
                 {"action": "advance", "seconds": 1.0}]


def validate(content: Any) -> dict[str, Any]:
    if not isinstance(content, dict) or set(content) != {"version", "name", "seed", "clock", "input", "simulator", "steps"}:
        raise ValueError("A complete version-one scenario is required")
    if type(content["version"]) is not int or content["version"] != 1:
        raise ValueError("Unsupported scenario version")
    if type(content["seed"]) is not int or content["seed"] != 0 or content["clock"] != "controlled" or content["input"] != "protocol-shaped":
        raise ValueError("Scenarios use fixed seed 0, controlled time and protocol-shaped input")
    name = content["name"]
    if not isinstance(name, str) or not name.strip() or len(name) > 80 or any(ord(char) < 32 for char in name):
        raise ValueError("A readable scenario name of 1–80 characters is required")
    simulator = Simulator()
    if not isinstance(content["simulator"], dict) or set(content["simulator"]) != set(simulator.values):
        raise ValueError("Complete simulator settings required")
    simulator.configure(content["simulator"])
    steps = content["steps"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError("A scenario needs 1–64 explicit steps")
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("Invalid scenario step")
        action = step.get("action")
        if action == "advance":
            seconds = step.get("seconds")
            if (set(step) != {"action", "seconds"} or isinstance(seconds, bool)
                    or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 <= seconds <= 3600):
                raise ValueError("Scenario advance requires 0–3600 seconds")
        elif action == "simulator_configure":
            simulator.configure({key: value for key, value in step.items() if key != "action"})
        elif action in ("simulator_emit", "disconnect", "connect"):
            if set(step) != {"action"}:
                raise ValueError("Unexpected fields on scenario action")
        else:
            raise ValueError("Scenario action is not a supported telemetry/time/session intent")
    result = deepcopy(content)
    encoded = json.dumps(result, ensure_ascii=False, allow_nan=False).encode()
    if len(encoded) > MAX_BYTES:
        raise ValueError("Scenario exceeds 32 KiB")
    return result


def decode(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or len(text.encode()) > MAX_BYTES:
        raise ValueError("Scenario exceeds 32 KiB or is not text")
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for name, value in pairs:
            if name in result:
                raise ValueError("Duplicate scenario field")
            result[name] = value
        return result
    try:
        return validate(json.loads(text, object_pairs_hook=object_pairs))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError(f"Invalid scenario: {exc}") from exc


class ScenarioStore(Protocol):
    def load(self) -> dict[str, Any] | None: ...
    def save(self, definition: dict[str, Any]) -> None: ...


class MemoryScenarioStore:
    def __init__(self):
        self.definition: dict[str, Any] | None = None

    def load(self) -> dict[str, Any] | None:
        return deepcopy(self.definition)

    def save(self, definition: dict[str, Any]) -> None:
        self.definition = validate(definition)


class FileScenarioStore:
    def __init__(self, path: Path | None = None):
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        self.path = path or base / "eucwatch/scenarios/current.json"

    def load(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        with self.path.open("rb") as handle:
            data = handle.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("Scenario exceeds 32 KiB")
        return decode(data.decode())

    def save(self, definition: dict[str, Any]) -> None:
        content = json.dumps(validate(definition), ensure_ascii=False, allow_nan=False).encode()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".scenario-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class ScenarioRunner:
    def __init__(self, definition: dict[str, Any]):
        self.definition = validate(definition)
        self.position = 0
        self.active = False
        self.session: int | None = None
        self.error: str | None = None

    def start(self, application: Application) -> None:
        if application.view()["transfer"]["active"]:
            raise ValueError("Return from configuration transfer before starting a scenario")
        application.action("stop")
        application.action("simulator_configure", **self.definition["simulator"])
        state = application.action("simulator_start", controlled=True)
        self.session = state["session"]
        self.position = 0
        self.active = True
        self.error = None

    def step(self, application: Application) -> None:
        state = application.view()
        if not self.active or state["mode"] != "simulator" or not state["controlled"] or state["session"] != self.session:
            self.active = False
            self.error = "Scenario ended or application mode/session changed; start explicitly again"
            raise ValueError(self.error)
        step = self.definition["steps"][self.position]
        try:
            result = application.action(step["action"], **{key: value for key, value in step.items() if key != "action"})
        except ValueError as exc:
            self.active = False
            self.error = str(exc)
            raise
        self.session = result["session"]
        self.position += 1
        self.active = self.position < len(self.definition["steps"])


class ScenarioLibrary:
    def __init__(self, store: ScenarioStore | None = None):
        self.store = store or MemoryScenarioStore()
        self.definition: dict[str, Any] | None = None
        self.preview: dict[str, Any] | None = None
        self.runner: ScenarioRunner | None = None
        self.error: str | None = None
        self.persistence_error: str | None = None
        try:
            content = self.store.load()
            if content is not None:
                self.definition = validate(content)
        except (OSError, ValueError, UnicodeError) as exc:
            self.persistence_error = f"Saved scenario could not be loaded: {exc}"

    def review(self, text: str) -> dict[str, Any]:
        try:
            self.preview = decode(text)
        except ValueError as exc:
            self.error = str(exc)
            raise
        self.error = None
        return deepcopy(self.preview)

    def save_current(self, values: dict[str, Any], name: str, steps: Any = None) -> None:
        definition = validate({"version": 1, "name": name, "seed": 0, "clock": "controlled", "input": "protocol-shaped",
                               "simulator": values, "steps": DEFAULT_STEPS if steps is None else steps})
        try:
            self.store.save(definition)
        except (OSError, ValueError) as exc:
            self.persistence_error = f"Scenario save failed; read saved content before retry: {exc}"
            return
        self.definition = definition
        self.preview = None
        self.persistence_error = None

    def export(self) -> str:
        definition = self.preview or self.definition
        if definition is None:
            raise ValueError("Save or review a scenario before export")
        text = json.dumps(validate(definition), ensure_ascii=False, allow_nan=False) + "\n"
        if len(text.encode()) > MAX_BYTES:
            raise ValueError("Scenario export exceeds 32 KiB")
        return text

    def start(self, application: Application) -> None:
        definition = self.preview or self.definition
        if definition is None:
            raise ValueError("Save or review a scenario before starting")
        self.runner = ScenarioRunner(definition)
        self.runner.start(application)
        self.error = None

    def step(self, application: Application) -> None:
        if self.runner is None:
            raise ValueError("Start a reviewed or saved scenario explicitly")
        self.runner.step(application)

    def view(self) -> dict[str, Any]:
        definition = self.runner.definition if self.runner else self.preview or self.definition
        injections = []
        if definition:
            settings = [definition["simulator"]] + [step for step in definition["steps"] if step["action"] == "simulator_configure"]
            defaults = Simulator().values
            injections = sorted({key for setting in settings for key, value in setting.items()
                                 if key.startswith("control_") and value != defaults.get(key)})
        return {"definition": deepcopy(self.definition), "preview": deepcopy(self.preview),
                "position": self.runner.position if self.runner else 0,
                "total": len(definition["steps"]) if definition else 0,
                "active": bool(self.runner and self.runner.active),
                "error": self.runner.error if self.runner and self.runner.error else self.error,
                "persistence_error": self.persistence_error,
                "provenance": "Fixed inputs, seed 0, controlled clock, protocol-shaped simulator; no random generator",
                "higher_level_injections": injections}
