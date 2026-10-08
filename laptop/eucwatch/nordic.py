"""Explicit, bounded ordinary-user Nordic UART configuration transport."""

import asyncio
import math
from contextlib import suppress

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

from .transfer_protocol import (
    MAX_MESSAGE_BYTES,
    NUS_NOTIFY,
    NUS_SERVICE,
    NUS_WRITE,
    decode,
)


class NusTransport:
    def __init__(
        self, application, live, *, scanner=None, client_factory=None, timeout=5.0
    ):
        if (
            isinstance(timeout, bool)
            or not math.isfinite(timeout)
            or not 0 < timeout <= 30
        ):
            raise ValueError("Nordic UART timeout must be between zero and 30 seconds")
        self.application, self.live = application, live
        self.scanner, self.client_factory = (
            scanner or BleakScanner,
            client_factory or BleakClient,
        )
        self.timeout = timeout
        self.devices = {}
        self.selected = None
        self.client = None
        self.characteristic = None
        self.response_mode = None
        self.session = None
        self.generation = 0
        self.closed = False
        self.link = "idle"
        self.error = None
        self.buffer = bytearray()
        self.pending = None
        self.lock = asyncio.Lock()
        self.cleanup_lock = asyncio.Lock()

    def _require_transfer(self):
        state = self.application.view()
        if (
            self.closed
            or state["mode"] != "transfer"
            or not state["transfer"]["active"]
            or state["recovery"]
        ):
            raise ValueError(
                "Open stopped configuration transfer before Nordic UART access"
            )
        worker = self.live.worker
        if (
            self.live.client is not None
            or self.live.desired
            or (worker is not None and not worker.done())
        ):
            raise ValueError(
                "Complete the wheel client disconnect before Nordic UART access"
            )
        return state["session"]

    def _owned(self, generation, session):
        return (
            generation == self.generation
            and session == self.session
            and self.application.view()["session"] == session
            and self.application.mode == "transfer"
            and self.application.transfer.active
        )

    def _fault(self, reason):
        self.error = str(reason)
        self.link = "failed"
        self.generation += 1
        self.session = None
        self.buffer.clear()
        if self.pending is not None and not self.pending.done():
            self.pending.set_exception(OSError(self.error))

    async def discover(self):
        self._require_transfer()
        if self.client is not None:
            raise ValueError("Disconnect the watch before discovery")
        self.link = "discovering"
        try:
            async with asyncio.timeout(self.timeout):
                results = await self.scanner.discover(
                    timeout=self.timeout, return_adv=True
                )
            self._require_transfer()
            self.devices = {
                device.address: (
                    device,
                    {
                        "address": device.address,
                        "name": advertisement.local_name
                        or device.name
                        or "Unnamed watch",
                        "rssi": advertisement.rssi,
                        "service_uuids": list(advertisement.service_uuids),
                    },
                )
                for device, advertisement in results.values()
                if NUS_SERVICE in [uuid.lower() for uuid in advertisement.service_uuids]
            }
            self.link, self.error = "discovered", None
            return self.status()["devices"]
        except (BleakError, OSError, ValueError) as exc:
            self._fault(f"Watch discovery failed: {exc}")
            raise OSError(self.error) from exc

    async def connect(self, address):
        session = self._require_transfer()
        if address not in self.devices:
            raise ValueError("Select a watch from explicit discovery")
        await self.disconnect()
        if self.client is not None:
            raise OSError("Previous watch disconnect remains uncertain")
        self._require_transfer()
        self.generation += 1
        generation = self.generation
        self.session, self.selected = session, address
        self.link = "connecting"
        client = self.client_factory(
            self.devices[address][0],
            timeout=self.timeout,
            disconnected_callback=lambda value: self._disconnected(
                value, generation, session
            ),
        )
        self.client = client
        try:
            async with asyncio.timeout(self.timeout):
                await client.connect()
                self._require_transfer()
                if not self._owned(generation, session):
                    raise ValueError(
                        "Watch connection belongs to an ended transfer session"
                    )
                service = client.services.get_service(NUS_SERVICE)
                write = client.services.get_characteristic(NUS_WRITE)
                notify = client.services.get_characteristic(NUS_NOTIFY)
                if (
                    service is None
                    or write is None
                    or notify is None
                    or write.service_uuid.lower() != NUS_SERVICE
                    or notify.service_uuid.lower() != NUS_SERVICE
                    or "notify" not in notify.properties
                ):
                    raise ValueError(
                        "Selected watch lacks Nordic UART service/characteristics"
                    )
                if "write-without-response" in write.properties:
                    self.response_mode = False
                elif "write" in write.properties:
                    self.response_mode = True
                else:
                    raise ValueError(
                        "Nordic UART input has no supported write property"
                    )
                self.characteristic = write
                await client.start_notify(
                    notify,
                    lambda value, raw: self._receive(
                        client, generation, session, bytes(raw)
                    ),
                    bluez={"use_start_notify": True},
                )
                if not self._owned(generation, session):
                    raise ValueError(
                        "Watch subscription belongs to an ended transfer session"
                    )
            self.link, self.error = "subscribed", None
            return self.status()
        except (BleakError, OSError, ValueError, asyncio.CancelledError) as exc:
            self._fault(f"Watch connection failed: {exc}")
            await self.disconnect()
            raise

    def _disconnected(self, client, generation, session):
        if client is self.client and self._owned(generation, session):
            self._fault(
                "Watch disconnected; reconnect explicitly before another request"
            )

    def _receive(self, client, generation, session, raw):
        if client is not self.client or not self._owned(generation, session):
            return
        if self.pending is None or self.pending.done():
            self._fault("Unsolicited watch response; reconnect before another request")
            return
        if len(self.buffer) + len(raw) > MAX_MESSAGE_BYTES:
            self._fault("Watch response exceeds 512 bytes")
            return
        self.buffer.extend(raw)
        if b"\n" in self.buffer:
            line = bytes(self.buffer)
            try:
                decode(line)
            except ValueError as exc:
                self._fault(exc)
                return
            self.buffer.clear()
            self.pending.set_result(line)

    async def exchange(self, message):
        decode(message)
        async with self.lock:
            session = self._require_transfer()
            client, generation = self.client, self.generation
            characteristic = self.characteristic
            if (
                client is None
                or characteristic is None
                or not client.is_connected
                or self.link != "subscribed"
                or not self._owned(generation, session)
            ):
                raise OSError(
                    "Connect a fresh watch session before requesting configuration"
                )
            self.pending = asyncio.get_running_loop().create_future()
            try:
                async with asyncio.timeout(self.timeout):
                    for offset in range(0, len(message), 20):
                        self._require_transfer()
                        if not self._owned(generation, session):
                            raise OSError("Transfer session ended before write")
                        await client.write_gatt_char(
                            characteristic,
                            message[offset : offset + 20],
                            response=self.response_mode,
                        )
                    return await self.pending
            except (BleakError, OSError, ValueError, asyncio.CancelledError) as exc:
                self._fault(f"Watch exchange failed; reconnect explicitly: {exc}")
                await self.disconnect()
                raise
            finally:
                if self.pending is not None and not self.pending.done():
                    self.pending.cancel()
                elif self.pending is not None and not self.pending.cancelled():
                    self.pending.exception()
                self.pending = None

    def tick(self):
        if self.session is not None and not self._owned(self.generation, self.session):
            self._fault(
                "Application transfer session ended; watch connection must close"
            )

    async def disconnect(self):
        self.generation += 1
        self.session = None
        self.buffer.clear()
        if self.pending is not None and not self.pending.done():
            self.pending.set_exception(OSError("Watch transfer disconnected"))
        cleanup = asyncio.create_task(self._disconnect_client())
        cancelled = False
        while True:
            try:
                await asyncio.shield(cleanup)
                break
            except asyncio.CancelledError:
                if cleanup.cancelled():
                    self.error, self.link = (
                        "Watch cleanup cancelled; connection state unknown",
                        "failed",
                    )
                    raise
                cancelled = True
        if cancelled:
            raise asyncio.CancelledError

    async def _disconnect_client(self):
        async with self.cleanup_lock:
            await self._disconnect_current()

    async def _disconnect_current(self):
        client = self.client
        if client is not None:
            try:
                async with asyncio.timeout(self.timeout):
                    with suppress(BleakError, OSError):
                        await client.stop_notify(NUS_NOTIFY)
                    await client.disconnect()
                    if client.is_connected:
                        raise OSError("Watch remains connected after disconnect")
                self.client = None
            except (BleakError, OSError) as exc:
                self.error, self.link = (
                    f"Watch cleanup failed; connection state unknown: {exc}",
                    "failed",
                )
                return
        self.link = "disconnected"

    async def close(self):
        self.closed = True
        await self.disconnect()

    def status(self):
        return {
            "devices": [dict(row) for _, row in self.devices.values()],
            "selected": self.selected,
            "link": self.link,
            "error": self.error,
            "session": self.session,
            "closed": self.closed,
            "connected": self.client is not None and self.client.is_connected,
            "provenance": "Ordinary-user Nordic UART configuration transport; physical exchange unaccepted",
        }
