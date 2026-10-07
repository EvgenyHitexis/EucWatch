"""Explicit ordinary-user Bleak telemetry; no wheel-writing capability."""

import asyncio
import math
from contextlib import suppress
from typing import Any

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

from .application import Application

SERVICE = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC = "0000ffe1-0000-1000-8000-00805f9b34fb"


class LiveSession:
    def __init__(
        self,
        application: Application,
        *,
        scanner: Any = None,
        client_factory: Any = None,
        discovery_timeout: float = 5,
        transport_timeout: float = 10,
        reconnect_attempts: int = 3,
        reconnect_delay: float = 1,
    ):
        self.application = application
        self.scanner = scanner or BleakScanner
        self.client_factory = client_factory or BleakClient
        self.discovery_timeout = discovery_timeout
        self.transport_timeout = transport_timeout
        self.reconnect_attempts = reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.devices: dict[str, tuple[Any, dict[str, Any]]] = {}
        self.selected: str | None = None
        self.link = "idle"
        self.error: str | None = None
        self.closed = False
        if (
            not all(
                math.isfinite(value) and value > 0
                for value in (discovery_timeout, transport_timeout)
            )
            or type(reconnect_attempts) is not int
            or reconnect_attempts < 0
            or not math.isfinite(reconnect_delay)
            or reconnect_delay < 0
        ):
            raise ValueError("Live transport limits must be finite and bounded")
        self.client: Any = None
        self.session: int | None = None
        self.worker: asyncio.Task[None] | None = None
        self.lost = asyncio.Event()
        self.desired = False
        self.notifications = 0
        self.valid_frames = 0
        self.rejected_frames = 0
        self.disconnects = 0
        self.reconnections = 0
        self.first_notification: float | None = None
        self.last_notification: float | None = None
        self.last_frame: float | None = None
        self.maximum_notification_gap = 0.0
        self.maximum_frame_gap = 0.0
        self.firmware: str | None = None

    async def discover(self) -> list[dict[str, Any]]:
        if self.closed:
            raise ValueError("Live session is closed")
        if self.worker is not None and not self.worker.done():
            raise ValueError("Disconnect the selected wheel before discovery")
        self.error = None
        self.link = "discovering"
        try:
            async with asyncio.timeout(self.discovery_timeout + 1):
                results = await self.scanner.discover(
                    timeout=self.discovery_timeout, return_adv=True
                )
            self.devices = {
                device.address: (
                    device,
                    {
                        "address": device.address,
                        "name": advertisement.local_name
                        or device.name
                        or "Unnamed device",
                        "rssi": advertisement.rssi,
                        "service_uuids": list(advertisement.service_uuids),
                    },
                )
                for device, advertisement in results.values()
            }
            self.link = "discovered"
        except (BleakError, OSError, ValueError) as exc:
            self.link = "failed"
            self.error = f"Bluetooth discovery failed: {type(exc).__name__}: {exc}"
        return self.status()["devices"]

    async def connect(self, address: str) -> dict[str, Any]:
        if self.closed:
            raise ValueError("Live session is closed")
        if address not in self.devices:
            raise ValueError("Select a device from explicit discovery")
        await self.disconnect()
        if self.client is not None:
            return self.status()
        self.selected = address
        self.error = None
        self.desired = True
        ready: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self.worker = asyncio.create_task(self._run(self.devices[address][0], ready))
        try:
            return await ready
        except asyncio.CancelledError:
            await self.disconnect()
            raise

    def _receive(self, session: int, raw: bytes) -> None:
        before = self.application.view()
        # All callbacks, including late ones, reach raw recording at ingress.
        self.application.receive(session, raw)
        state = self.application.view()
        if self.session != session or not self.desired:
            return
        if state["mode"] != "live" or state["session"] != session:
            self._source_lost(session, "Application session changed")
            return
        now = self.application.host_clock.read()[0]
        self.notifications += 1
        if self.first_notification is None:
            self.first_notification = now
        if self.last_notification is not None:
            self.maximum_notification_gap = max(
                self.maximum_notification_gap, now - self.last_notification
            )
        self.last_notification = now
        valid = (
            state["diagnostics"]["valid_frames"] - before["diagnostics"]["valid_frames"]
        )
        rejected = (
            state["diagnostics"]["rejected_frames"]
            - before["diagnostics"]["rejected_frames"]
        )
        self.valid_frames += max(0, valid)
        self.rejected_frames += max(0, rejected)
        if valid > 0:
            if self.last_frame is not None:
                self.maximum_frame_gap = max(
                    self.maximum_frame_gap, now - self.last_frame
                )
            self.last_frame = now
            self.firmware = state["telemetry"]["firmware"]

    def _source_lost(self, session: int, reason: str) -> None:
        if session != self.session or not self.desired:
            return
        state = self.application.view()
        if state["mode"] == "live":
            # Resume also replaces the application's token before transport notices.
            self.application.action(
                "live_disconnected", session=state["session"], reason=reason
            )
            self.error = reason
            self.link = "reconnecting"
            self.disconnects += 1
        else:
            self.desired = False
        self.session = None
        self.lost.set()

    def _ensure_owned(self, session: int) -> None:
        state = self.application.view()
        if (
            not self.desired
            or self.session != session
            or state["mode"] != "live"
            or state["session"] != session
        ):
            raise ValueError(
                "Connection attempt belongs to an ended application session"
            )

    async def _cleanup_client(self, client: Any) -> bool:
        # Cancellation must not abandon a partially connected BlueZ client.
        cleanup = asyncio.create_task(self._disconnect_client(client))
        cancelled = False
        while True:
            try:
                result = await asyncio.shield(cleanup)
                break
            except asyncio.CancelledError:
                cancelled = True
        if cancelled:
            raise asyncio.CancelledError
        return result

    async def _disconnect_client(self, client: Any) -> bool:
        try:
            async with asyncio.timeout(self.transport_timeout):
                await client.disconnect()
            if client.is_connected:
                raise ValueError("Bluetooth client remains connected after disconnect")
        except (BleakError, OSError, ValueError) as exc:
            self.error = f"Bluetooth cleanup failed: {type(exc).__name__}: {exc}"
            self.link = "failed"
            self.desired = False
            return False
        return True

    async def _run(self, device: Any, ready: asyncio.Future[dict[str, Any]]) -> None:
        failures = 0
        attempted = False
        try:
            while self.desired:
                if attempted and self.application.view()["mode"] != "live":
                    break
                attempted = True
                client = None
                self.lost = asyncio.Event()
                try:
                    token = self.application.action("live_start")["session"]
                    self.session = token
                    self.firmware = None
                    self.link = "connecting"
                    client = self.client_factory(
                        device,
                        timeout=self.transport_timeout,
                        disconnected_callback=lambda _client, session=token: (
                            self._source_lost(session, "Bluetooth source disconnected")
                        ),
                    )
                    self.client = client
                    async with asyncio.timeout(self.transport_timeout):
                        await client.connect()
                    self._ensure_owned(token)
                    service = client.services.get_service(SERVICE)
                    characteristic = client.services.get_characteristic(CHARACTERISTIC)
                    if (
                        service is None
                        or characteristic is None
                        or characteristic.service_uuid.lower() != SERVICE
                        or "notify" not in characteristic.properties
                    ):
                        raise ValueError(
                            "Selected device lacks FFE0/FFE1 notification support"
                        )
                    self.application.action("live_connected", session=token)
                    self.link = "subscribing"
                    async with asyncio.timeout(self.transport_timeout):
                        await client.start_notify(
                            characteristic,
                            lambda _characteristic, data, session=token: self._receive(
                                session, bytes(data)
                            ),
                            bluez={"use_start_notify": True},
                        )
                    self._ensure_owned(token)
                    self.link = "subscribed"
                    self.error = None
                    failures = 0
                    if not ready.done():
                        ready.set_result(self.status())
                    else:
                        self.reconnections += 1
                    await self.lost.wait()
                except (BleakError, OSError, ValueError) as exc:
                    self.error = (
                        f"Bluetooth connection failed: {type(exc).__name__}: {exc}"
                    )
                    self.link = "failed"
                    failures += 1
                    if not ready.done() or failures >= self.reconnect_attempts:
                        self.desired = False
                finally:
                    state = self.application.view()
                    if (
                        self.session is not None
                        and state["mode"] == "live"
                        and state["session"] == self.session
                    ):
                        self.application.action(
                            "live_disconnected",
                            session=self.session,
                            reason=self.error or "Live session stopped",
                        )
                    self.session = None
                    if client is not None and await self._cleanup_client(client):
                        self.client = None
                if not ready.done():
                    ready.set_result(self.status())
                if self.reconnect_attempts == 0:
                    self.desired = False
                if self.desired:
                    self.link = "reconnecting"
                    await asyncio.sleep(self.reconnect_delay * 2 ** min(failures, 3))
        finally:
            if not self.desired and self.link != "failed":
                self.link = "disconnected"
            if not ready.done():
                ready.set_result(self.status())

    def tick(self) -> None:
        """Called by the backend owner to notice mode changes and host resume."""
        if self.session is not None:
            state = self.application.view()
            if state["mode"] != "live" or state["session"] != self.session:
                self._source_lost(self.session, "Application session changed")

    async def disconnect(self) -> None:
        self.desired = False
        state = self.application.view()
        if (
            self.session is not None
            and state["mode"] == "live"
            and state["session"] == self.session
        ):
            self.application.action(
                "live_disconnected", session=self.session, reason="Explicit disconnect"
            )
        self.session = None
        running = self.worker is not None and not self.worker.done()
        if self.worker is not None:
            self.worker.cancel()
            with suppress(asyncio.CancelledError):
                await self.worker
            self.worker = None
        if self.client is not None and (
            not self.client.is_connected
            or (not running and await self._cleanup_client(self.client))
        ):
            self.client = None
        if self.client is None:
            self.link = "disconnected"

    async def close(self) -> None:
        self.closed = True
        await self.disconnect()

    def status(self) -> dict[str, Any]:
        duration = (
            None
            if self.first_notification is None or self.last_notification is None
            else self.last_notification - self.first_notification
        )
        return {
            "devices": [dict(details) for _, details in self.devices.values()],
            "selected": self.selected,
            "link": self.link,
            "error": self.error,
            "closed": self.closed,
            "active": self.desired,
            "session": self.session,
            "notifications": self.notifications,
            "valid_frames": self.valid_frames,
            "rejected_frames": self.rejected_frames,
            "disconnects": self.disconnects,
            "reconnections": self.reconnections,
            "firmware": self.firmware,
            "notification_rate_hz": None
            if not duration
            else (self.notifications - 1) / duration,
            "maximum_notification_gap_s": self.maximum_notification_gap,
            "maximum_frame_gap_s": self.maximum_frame_gap,
            "last_notification_elapsed_s": self.last_notification,
            "last_frame_elapsed_s": self.last_frame,
            "provenance": "Live Bleak/BlueZ transport; "
            + (
                "Sherman L identity verified by CRC-valid telemetry"
                if self.firmware
                else "identity awaits CRC-valid Sherman L telemetry"
            ),
        }
