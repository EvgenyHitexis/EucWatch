"""Async configuration wire and the shared saved-copy reconciliation workflow."""

import asyncio
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

from .configuration import default_configuration, validate_configuration
from .transfer import ReconciliationState
from .transfer_protocol import decode, encode, read_requests, upload_requests


class AsyncConfigurationProtocol:
    def __init__(self, exchange: Callable[[bytes], Awaitable[bytes]]):
        self.exchange = exchange

    async def request(self, op: str, **fields: Any) -> dict[str, Any]:
        row = decode(await self.exchange(encode({"op": op, **fields})))
        if row.get("ok") is not True or row.get("op") != op:
            raise ValueError(
                str(row.get("error", "Configuration protocol response mismatch"))
            )
        return row

    async def _drive(self, workflow):
        response = None
        while True:
            try:
                op, fields = workflow.send(response)
            except StopIteration as result:
                return result.value
            response = await self.request(op, **fields)

    async def read(self) -> dict[str, Any]:
        return await self._drive(read_requests())

    async def upload(self, config, expected, before_commit=None):
        await self._drive(upload_requests(config, expected, before_commit))

    async def finish(self):
        if (await self.request("finish")).get("returned") is not True:
            raise ValueError("Watch did not acknowledge return to riding")


class AsyncConfigurationTransfer(ReconciliationState):
    def __init__(
        self, laptop_store, shared_store, protocol, *, endpoint_label, journal_store
    ):
        super().__init__(
            laptop_store,
            shared_store,
            default_configuration(),
            journal_store=journal_store,
        )
        self.protocol = protocol
        self.endpoint_label = endpoint_label
        self.verified_saved = None

    def begin(self, config, mode, simulating):
        validate_configuration(config)
        self.active = True
        self.previous_mode, self.previous_simulating = mode, simulating
        if self.verified_saved is not None:
            self.status, self.error = (
                "return_failed",
                "Configuration already verified and saved; explicitly Return without resubmitting",
            )
        elif self.pending is None and self.journal_error is None:
            self.status, self.error = "ready", None
        else:
            self.status, self.error = (
                "unknown",
                "Outcome unknown; read saved watch content before deciding success or retry",
            )

    async def areview(self, config):
        self._require_active()
        if self.verified_saved is not None:
            raise ValueError(
                "Configuration is already saved; explicitly Return without resubmitting"
            )
        if self.pending is not None or self.journal_error is not None:
            raise ValueError(
                "Read back the unknown transfer before preparing another preview"
            )
        self.preview = None
        try:
            self._review_saved(config, await self.protocol.read())
        except (OSError, ValueError) as exc:
            self.status, self.error = (
                "failed",
                f"Saved watch configuration could not be read: {exc}",
            )

    async def asend(self, config):
        self._require_active()
        self.local_saved = None
        if self.pending is not None or self.journal_error is not None:
            raise ValueError("Outcome unknown; reconcile saved content before retrying")
        if self.verified_saved is not None:
            raise ValueError(
                "Configuration is already saved; explicitly Return without resubmitting"
            )
        preview = self.preview
        if preview is None or preview["candidate"] is None:
            raise ValueError(
                "Review and resolve the complete configuration before Transfer"
            )
        try:
            saved = self.laptop_store.load()
            current = validate_configuration(config if saved is None else saved)
            if current != preview["laptop"] or config != preview["laptop"]:
                self.local_saved = current
                await self.areview(current)
                self.status, self.error = (
                    "failed",
                    "Laptop saved content changed after preview; refreshed reconciliation requires review again",
                )
                return None
            watch = await self.protocol.read()
            if watch != preview["watch"]:
                self._review_saved(current, watch)
                self.status, self.error = (
                    "failed",
                    "Watch saved content changed after preview; refreshed reconciliation requires review again",
                )
                return None
            await self.protocol.upload(
                preview["candidate"],
                preview["watch"],
                lambda: self._prepare_pending(preview),
            )
            committed = await self.protocol.read()
            self.watch = committed
            if committed != preview["candidate"]:
                raise ValueError(
                    "Committed watch content/revision did not match the reviewed configuration"
                )
            return await self._acomplete(committed)
        except asyncio.CancelledError:
            self._read_local_saved()
            self.status = (
                "return_failed"
                if self.verified_saved is not None
                else "unknown"
                if self.pending is not None
                else "failed"
            )
            self.error = "Transfer interrupted; explicitly read saved content before deciding success or retry"
            raise
        except (OSError, ValueError) as exc:
            self._read_local_saved()
            if (
                self.pending is None
                and self.local_saved is not None
                and self.local_saved != preview["laptop"]
            ):
                await self.areview(self.local_saved)
            self.status = "unknown" if self.pending is not None else "failed"
            self.error = f"{'Outcome unknown' if self.pending is not None else 'Configuration transfer failed'}; read saved content before retry: {exc}"
            return None

    async def _acomplete(self, committed):
        # Keep transfer ownership during finish; the BLE adapter must reject any
        # real wheel session until its complete disconnect has been verified.
        self.laptop_store.save(committed)
        self.shared_store.save(committed)
        self.journal.save(None)
        self.base = deepcopy(committed)
        self.pending = None
        self.journal_error = None
        self.preview = None
        self.verified_saved = deepcopy(committed)
        self.local_saved = deepcopy(committed)
        await self.areturn()
        return committed

    async def areconcile(self, config):
        self._require_active()
        self.local_saved = None
        pending = self.pending
        if pending is None and self.journal_error is None:
            raise ValueError("No unknown transfer needs readback reconciliation")
        try:
            saved = self.laptop_store.load()
            if saved is not None:
                saved = validate_configuration(saved)
                if saved != config:
                    self.local_saved = saved
                config = saved
            actual = await self.protocol.read()
            self.watch = actual
            if (
                pending is not None
                and actual == pending["candidate"]
                and config in (pending["laptop"], pending["candidate"])
            ):
                return await self._acomplete(actual)
            self.journal.save(None)
        except asyncio.CancelledError:
            self._read_local_saved()
            self.status = (
                "return_failed" if self.verified_saved is not None else "unknown"
            )
            self.error = "Saved readback interrupted; explicitly reconnect and review the retained outcome"
            raise
        except (OSError, ValueError) as exc:
            self._read_local_saved()
            self.status, self.error = (
                "unknown",
                f"Outcome unknown; saved readback reconciliation failed: {exc}",
            )
            return None
        self.pending, self.journal_error = None, None
        self._review_saved(config, actual)
        self.error = "Saved content changed or activation was not confirmed; review the refreshed candidate before an explicit transfer"
        return None

    async def acancel(self):
        self._require_active()
        if self.pending is not None or self.journal_error is not None:
            raise ValueError(
                "Read active configuration before cancelling an unknown outcome"
            )
        try:
            if (await self.protocol.request("abort")).get("aborted") is not True:
                raise ValueError("Watch did not acknowledge cancellation")
            self.preview, self.error, self.status = None, None, "cancelled"
        except (OSError, ValueError) as exc:
            self.status, self.error = (
                "failed",
                f"Cancellation not acknowledged; explicit Return is available: {exc}",
            )

    async def areturn(self):
        self._require_active()
        try:
            await self.protocol.finish()
        except asyncio.CancelledError:
            self.status, self.error = (
                "return_failed",
                "Return interrupted; saved content remains usable and explicit Return is available",
            )
            raise
        except (OSError, ValueError) as exc:
            self.status, self.error = (
                "return_failed",
                f"Return acknowledgement unavailable; saved content remains usable: {exc}",
            )
            return False
        self.active = False
        self.preview = None
        self.status = "success" if self.verified_saved is not None else "returned"
        self.error = None
        return True

    def view(self):
        return {
            "active": self.active,
            "endpoint": self.endpoint_label,
            "status": self.status,
            "error": self.error,
            "watch_revision": self.watch["revision"],
            "watch_config": deepcopy(self.watch),
            "preview": deepcopy(self.preview),
            "scenario": None,
            "pending": None
            if self.pending is None
            else {
                "candidate_revision": self.pending["candidate"]["revision"],
                "laptop_revision": self.pending["laptop"]["revision"],
                "watch_revision": self.pending["watch"]["revision"],
            },
        }
