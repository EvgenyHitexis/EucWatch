"""Narrow configuration stores; atomic local replacement and valid recovery."""

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol

from .configuration import default_configuration, validate_configuration

MAX_CONFIG_BYTES = 32 * 1024


class ConfigStore(Protocol):
    warning: str | None

    def load(self) -> dict[str, Any] | None: ...
    def save(self, config: dict[str, Any]) -> None: ...


class MemoryStore:
    """An explicit in-memory persistence adapter for deterministic scenarios."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.content = deepcopy(config)
        self.warning: str | None = None

    def load(self) -> dict[str, Any] | None:
        return None if self.content is None else validate_configuration(self.content)

    def save(self, config: dict[str, Any]) -> None:
        self.content = validate_configuration(config)
        self.warning = None


class FileStore:
    def __init__(self, path: Path | None = None):
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        self.path = path or base / "eucwatch" / "configuration.json"
        self.backup = self.path.with_suffix(".last-good.json")
        self.warning: str | None = None
        self.current: dict[str, Any] | None = None

    def _read(self, path: Path) -> dict[str, Any]:
        with path.open("rb") as handle:
            data = handle.read(MAX_CONFIG_BYTES + 1)
        if len(data) > MAX_CONFIG_BYTES:
            raise ValueError("Configuration exceeds the supported size")
        return validate_configuration(json.loads(data))

    def load(self) -> dict[str, Any] | None:
        self.warning = None
        if not self.path.exists() and not self.backup.exists():
            self.current = None
            return None
        try:
            self.current = self._read(self.path)
        except (OSError, ValueError, UnicodeError) as exc:
            try:
                self.current = self._read(self.backup)
            except (OSError, ValueError, UnicodeError):
                raise ValueError(
                    f"Saved configuration cannot be loaded; review required: {exc}"
                ) from exc
            self.warning = f"Recovered last-known-good configuration: {exc}"
        return deepcopy(self.current)

    def _replace(self, path: Path, data: bytes) -> None:
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if Path(temporary).read_bytes() != data:
                raise OSError("Staged configuration readback failed")
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def save(self, config: dict[str, Any]) -> None:
        validated = validate_configuration(config)
        data = (
            json.dumps(validated, ensure_ascii=False, allow_nan=False, sort_keys=True)
            + "\n"
        ).encode()
        if len(data) > MAX_CONFIG_BYTES:
            raise ValueError("Configuration exceeds the supported size")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.current is not None:
            previous = (
                json.dumps(
                    self.current, ensure_ascii=False, allow_nan=False, sort_keys=True
                )
                + "\n"
            ).encode()
            self._replace(self.backup, previous)
        else:
            # The first persisted copy needs a validated recovery companion too.
            self._replace(self.backup, (json.dumps(default_configuration()) + "\n").encode())
        self._replace(self.path, data)
        if self._read(self.path) != validated:
            raise ValueError("Active configuration readback failed")
        directory = os.open(self.path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        self.current = validated
        self.warning = None
