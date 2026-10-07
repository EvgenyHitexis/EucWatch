"""One bounded writer using the already-owned wheel telemetry connection."""

import asyncio
import math
from copy import deepcopy
from contextlib import suppress
from typing import Any

from bleak.exc import BleakError

from .application import Application
from .control import SUBMISSION_LIMIT, command
from .horn import PACKET
from .live import CHARACTERISTIC, SERVICE, LiveSession


class LiveControl:
    def __init__(self, live: LiveSession, application: Application, *, write_timeout: float = 3.0):
        if isinstance(write_timeout, bool) or not math.isfinite(write_timeout) or not 0 < write_timeout <= 3:
            raise ValueError("Live writes require a positive timeout of at most three seconds")
        self.live = live
        self.application = application
        self.write_timeout = write_timeout
        self.closed = False
        self.worker: asyncio.Task[None] | None = None
        self.current: tuple[dict[str, Any], Any] | None = None
        self.queued: tuple[dict[str, Any], Any] | None = None

    def _guard(self, row: dict[str, Any], client: Any) -> Any:
        state = self.application.view()
        if (self.closed or self.live.closed or not self.live.desired
                or client is None or client is not self.live.client or not client.is_connected
                or self.live.link != "subscribed" or self.live.session != row.get("session")
                or state["mode"] != "live" or state["session"] != row.get("session")
                or not state["fresh"] or state["recovery"]):
            raise ValueError("Live command connection is unavailable or stale")
        if row.get("kind") == "horn":
            if (not state["awake"] or self.application.control.pending
                    or self.application.horn.pending.get(row.get("request")) != row["session"]
                    or row.get("packet_hex") != PACKET.hex()):
                raise ValueError("Horn request is no longer eligible; request discarded")
        else:
            attempt = state["preset_attempt"]
            if (not attempt or not attempt["pending"] or attempt["status"] != "submitting"
                    or (row.get("attempt"), row.get("session"), row.get("index"))
                    != (attempt["id"], attempt["session"], attempt["awaiting"])):
                raise ValueError("Preset submission belongs to an ended attempt")
            name = list(attempt["fields"])[row["index"]]
            if (row.get("field") != name or row.get("value") != attempt["fields"][name]["requested"]
                    or row.get("packet_hex") != command(name, attempt["fields"][name]["requested"]).hex()):
                raise ValueError("Preset command differs from the exact requested setting")
        characteristic = client.services.get_characteristic(CHARACTERISTIC)
        if (characteristic is None or characteristic.service_uuid.lower() != SERVICE
                or "write-without-response" not in characteristic.properties
                or type(getattr(characteristic, "max_write_without_response_size", None)) is not int
                or characteristic.max_write_without_response_size < 20):
            raise ValueError("FFE1 requires explicit write-without-response support for 20-byte chunks")
        return characteristic

    def submit(self, row: dict[str, Any]) -> None:
        client = self.live.client
        try:
            self._guard(row, client)
        except (BleakError, OSError) as exc:
            raise ValueError(f"Live command unavailable: {type(exc).__name__}: {exc}") from exc
        if self.worker is not None and not self.worker.done() and self.worker.cancelling():
            raise ValueError("Live command writer is stopping; request discarded")
        if self.queued is not None or self.current is not None:
            raise ValueError("Live command writer is busy; request discarded")
        self.queued = (deepcopy(row), client)
        if self.worker is None or self.worker.done():
            self.worker = asyncio.create_task(self._run())

    def _result(self, row: dict[str, Any], success: bool, error: str = "") -> None:
        state = self.application.view()
        if state["mode"] != "live" or state["session"] != row["session"]:
            return
        if row.get("kind") == "horn":
            self.application.action("horn_result", request=row["request"], session=row["session"], success=success, error=error)
        else:
            self.application.action("command_result", attempt=row["attempt"], session=row["session"], index=row["index"], success=success, error=error)

    async def _run(self) -> None:
        try:
            while self.queued is not None:
                self.current, self.queued = self.queued, None
                row, client = self.current
                error = ""
                try:
                    packet = bytes.fromhex(row["packet_hex"])
                    for offset in range(0, len(packet), 20):
                        characteristic = self._guard(row, client)
                        timeout = self.write_timeout
                        if row.get("kind") != "horn":
                            attempt = self.application.view()["preset_attempt"]
                            timeout = min(timeout, SUBMISSION_LIMIT - (self.application.elapsed() - attempt["requested_s"]))
                        if timeout <= 0:
                            raise ValueError("Preset submission timeout")
                        async with asyncio.timeout(timeout):
                            await client.write_gatt_char(characteristic, packet[offset:offset + 20], response=False)
                        self._guard(row, client)
                except (BleakError, OSError, ValueError) as exc:
                    error = f"Live command failed: {type(exc).__name__}: {exc}"
                except asyncio.CancelledError:
                    self.current = None
                    self._result(row, False, "Live command cancelled; no retry")
                    raise
                self.current = None
                self._result(row, not error, error)
        finally:
            self.current = None

    def tick(self) -> None:
        intent = self.current or self.queued
        if intent is None:
            return
        row, client = intent
        try:
            self._guard(row, client)
        except (BleakError, OSError, ValueError) as exc:
            abandoned = self.queued
            self.queued = None
            if self.worker is not None:
                self.worker.cancel()
            if abandoned is not None:
                self._result(abandoned[0], False, str(exc))

    async def close(self) -> None:
        self.closed = True
        abandoned = self.queued
        self.queued = None
        if abandoned is not None:
            self._result(abandoned[0], False, "Live command writer closed; no retry")
        if self.worker is not None:
            self.worker.cancel()
            with suppress(asyncio.CancelledError):
                await self.worker
            self.worker = None
