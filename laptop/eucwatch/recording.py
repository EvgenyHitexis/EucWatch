"""Bounded, ordered raw evidence capture; replay never owns a transport."""

import asyncio
import hashlib
import json
import math
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4


class Recorder:
    """Nonblocking ingress with explicit async draining by the backend owner.

    Once evidence is lost or cannot be written, capture stops and the error
    remains visible. Previously queued evidence may still be drained.
    """

    def __init__(self, path: Path | None = None, *, max_queue: int = 256,
                 max_event_bytes: int = 65536,
                 writer: Callable[[Path,list[str]],None] | None = None):
        if max_queue < 1 or max_event_bytes < 1:
            raise ValueError("Recording bounds must be positive")
        if path is None:
            data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = data / "eucwatch/recordings" / f"{stamp}-{uuid4().hex}.jsonl"
        self.path = Path(path)
        self.max_queue = max_queue
        self.max_event_bytes = max_event_bytes
        self.queue: deque[str] = deque()
        self.sequence = 0
        self.written = 0
        self.rejected = 0
        self.error: str | None = None
        self.closed = False
        self.lock = asyncio.Lock()
        self.writer = writer

    def record(self, event: str | dict[str, Any], **fields: Any) -> bool:
        if self.closed or self.error is not None:
            self.rejected += 1
            return False
        if isinstance(event, dict):
            fields = {**event, **fields}
            event = fields.pop("event", "notification")
        row = {**fields, "event": event, "schema": 1,
               "sequence": self.sequence,
               "receipt_wall_utc": datetime.now(timezone.utc).isoformat()}
        self.sequence += 1
        try:
            line = json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n"
            if len(line.encode("utf-8")) > self.max_event_bytes:
                raise ValueError("Recording event exceeds the size limit")
            if len(self.queue) >= self.max_queue:
                raise ValueError("Recording queue overflow; capture stopped")
        except (TypeError, ValueError) as exc:
            self.error = str(exc)
            self.rejected += 1
            return False
        self.queue.append(line)
        return True

    def _append(self, lines: list[str]) -> None:
        if self.writer is not None:
            self.writer(self.path, lines)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as output:
            output.writelines(lines)
            output.flush()

    async def drain(self) -> None:
        async with self.lock:
            if not self.queue:
                return
            lines = list(self.queue)
            self.queue.clear()
            cancelled = False
            worker = asyncio.create_task(asyncio.to_thread(self._append, lines))
            try:
                while True:
                    try:
                        await asyncio.shield(worker)
                        break
                    except asyncio.CancelledError:
                        cancelled = True
                        if worker.cancelled():
                            self.error = 'Recording writer was cancelled; capture stopped'
                            self.rejected += len(lines)
                            raise
            except (OSError, UnicodeError) as exc:
                self.error = f"Recording storage failed: {exc}"
                self.rejected += len(lines)
            else:
                self.written += len(lines)
            if cancelled:
                raise asyncio.CancelledError

    async def close(self) -> None:
        self.closed = True
        await self.drain()

    def status(self) -> dict[str, Any]:
        return {"path": str(self.path), "queued": len(self.queue),
                "written": self.written, "rejected": self.rejected,
                "error": self.error, "closed": self.closed}


class Replay:
    """A validated sequence of evidence, with no transport or output adapter."""

    def __init__(self, rows: list[dict[str, Any]], digest: str, name: str):
        self._rows = tuple(rows)
        self.position = 0
        self.sha256 = digest
        self.name = name

    @classmethod
    def load(cls, path: Path, *, max_bytes: int = 16 * 1024 * 1024,
             max_events: int = 100000) -> "Replay":
        with Path(path).open("rb") as recording:
            data = recording.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("Recording exceeds the file size limit")
        return cls.from_text(data.decode("utf-8"), name=Path(path).name,
                             max_bytes=max_bytes, max_events=max_events)

    @classmethod
    def from_text(cls, content: str, *, name: str = "imported recording",
                  max_bytes: int = 16 * 1024 * 1024,
                  max_events: int = 100000) -> "Replay":
        encoded = content.encode("utf-8")
        if len(encoded) > max_bytes:
            raise ValueError("Recording exceeds the file size limit")
        rows = []
        previous_time = -1.0
        previous_sequence = -1
        for line in content.splitlines():
            if not line.strip():
                continue
            if len(rows) >= max_events:
                raise ValueError("Recording exceeds the event count limit")
            if len(line.encode("utf-8")) > 65536:
                raise ValueError("Recording event exceeds the size limit")
            try:
                row = json.loads(line)
            except (ValueError, RecursionError) as exc:
                raise ValueError("Invalid recording JSON") from exc
            if not isinstance(row, dict) or type(row.get("schema")) is not int or row["schema"] != 1:
                raise ValueError("Unsupported recording schema")
            event = row.setdefault("event", "notification")
            if event not in ("notification", "transport", "intent", "submission", "result"):
                raise ValueError("Unknown recording event")
            sequence = row.get("sequence")
            if type(sequence) is not int or sequence <= previous_sequence:
                raise ValueError("Recording sequence must increase in file order")
            receipt = row.get("receipt_elapsed_s")
            if (type(receipt) not in (int, float) or not math.isfinite(receipt)
                    or receipt < 0 or receipt < previous_time):
                raise ValueError("Recording receipt time must be finite and ordered")
            behavior = row.get("behavior_elapsed_s", receipt)
            if type(behavior) not in (int, float) or not math.isfinite(behavior) or behavior < 0:
                raise ValueError("Recording behavior time must be finite and nonnegative")
            session = row.get("session")
            if (type(session) not in (int, str) or isinstance(session, str) and
                    (not session or len(session) > 256) or isinstance(session, int) and session < 0):
                raise ValueError("Invalid recording session")
            source = row.get("source")
            if not isinstance(source, str) or not source or len(source) > 256:
                raise ValueError("Recording source provenance is required")
            if event == "notification":
                raw = row.get("raw_hex")
                characteristic = row.get("characteristic")
                if (not isinstance(raw, str) or len(raw) % 2 or
                        any(char not in "0123456789abcdefABCDEF" for char in raw)):
                    raise ValueError("Invalid raw notification bytes")
                if not isinstance(characteristic, str) or not characteristic or len(characteristic) > 256:
                    raise ValueError("Invalid notification characteristic")
            if event == "transport" and row.get("transition") not in (
                    "connected", "disconnected", "stopped", "resume"):
                raise ValueError("Unknown transport transition")
            previous_time = receipt
            previous_sequence = sequence
            rows.append(row)
        if not rows:
            raise ValueError("Recording contains no events")
        return cls(rows, hashlib.sha256(encoded).hexdigest(), name)

    @property
    def rows(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(row) for row in self._rows)

    def next_event(self) -> dict[str, Any] | None:
        if self.position >= len(self._rows):
            return None
        row = dict(self._rows[self.position])
        row.setdefault("event", "notification")
        self.position += 1
        return row

    def status(self) -> dict[str, Any]:
        sources = list(dict.fromkeys(row.get("source", "unknown") for row in self._rows))
        return {"name": self.name, "sha256": self.sha256,
                "source": ", ".join(sources), "total": len(self._rows),
                "position": self.position, "finished": self.position == len(self._rows)}
