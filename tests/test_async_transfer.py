"""Async real-endpoint workflow through public saved state and byte protocol."""

import asyncio
import tempfile
import unittest
from pathlib import Path

from eucwatch.async_transfer import (
    AsyncConfigurationProtocol,
    AsyncConfigurationTransfer,
)
from eucwatch.configuration import default_configuration
from eucwatch.persistence import FileStore, MemoryStore
from eucwatch.transfer_protocol import SimulatedWatch, decode


class AsyncTransferTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_review_send_verifies_saved_copies_then_finishes(self):
        base = default_configuration()
        laptop, watch, shared, journal = [MemoryStore(base) for _ in range(4)]
        changed = default_configuration()
        changed["alerts"]["speed"] = {"enabled": True, "threshold": 25}
        changed["revision"] = 1
        laptop.save(changed)
        endpoint, operations = SimulatedWatch(watch), []

        async def exchange(message):
            operation = decode(message)["op"]
            operations.append(operation)
            if operation == "commit":
                self.assertIsNotNone(transfer.view()["pending"])
            if operation == "finish":
                self.assertEqual(laptop.load(), watch.load())
                self.assertEqual(shared.load(), watch.load())
            return endpoint.exchange(message)

        transfer = AsyncConfigurationTransfer(
            laptop,
            shared,
            AsyncConfigurationProtocol(exchange),
            endpoint_label="Selected P22",
            journal_store=journal,
        )
        transfer.begin(changed, "live", False)
        self.assertEqual(
            operations, [], "Entering transfer does not read or activate remotely"
        )
        await transfer.areview(changed)
        self.assertEqual(transfer.view()["preview"]["conflicts"], [])
        result = await transfer.asend(changed)
        self.assertEqual(result, watch.load())
        self.assertEqual(transfer.view()["status"], "success")
        self.assertFalse(transfer.view()["active"])
        self.assertEqual(operations[-1], "finish")
        self.assertEqual(transfer.view()["endpoint"], "Selected P22")

    async def test_restart_unknown_is_bound_to_selected_target_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            base = default_configuration()
            laptop, watch, shared = [MemoryStore(base) for _ in range(3)]
            target_one = FileStore(Path(directory) / "target-one.json")
            target_two = FileStore(Path(directory) / "target-two.json")
            endpoint = SimulatedWatch(watch)

            async def interrupted(message):
                result = endpoint.exchange(message)
                if decode(message)["op"] == "commit":
                    raise OSError("Acknowledgement lost")
                return result

            transfer = AsyncConfigurationTransfer(
                laptop,
                shared,
                AsyncConfigurationProtocol(interrupted),
                endpoint_label="Target one",
                journal_store=target_one,
            )
            transfer.begin(base, "live", False)
            await transfer.areview(base)
            await transfer.asend(base)
            self.assertEqual(transfer.view()["status"], "unknown")

            async def exchange(message):
                return endpoint.exchange(message)

            other = AsyncConfigurationTransfer(
                laptop,
                MemoryStore(),
                AsyncConfigurationProtocol(exchange),
                endpoint_label="Target two",
                journal_store=target_two,
            )
            self.assertIsNone(
                other.view()["pending"],
                "Another watch must not inherit target one's pending activation",
            )
            restarted = AsyncConfigurationTransfer(
                laptop,
                shared,
                AsyncConfigurationProtocol(exchange),
                endpoint_label="Target one",
                journal_store=target_one,
            )
            restarted.begin(base, "live", False)
            self.assertEqual(restarted.view()["status"], "unknown")
            self.assertEqual(await restarted.areconcile(base), watch.load())

    async def test_lost_commit_ack_is_unknown_and_explicit_readback_never_resubmits(
        self,
    ):
        base = default_configuration()
        laptop, watch, shared, journal = [MemoryStore(base) for _ in range(4)]
        endpoint, operations, lost = SimulatedWatch(watch), [], True

        async def exchange(message):
            operation = decode(message)["op"]
            operations.append(operation)
            result = endpoint.exchange(message)
            if operation == "commit" and lost:
                raise OSError("Lost commit acknowledgement")
            return result

        transfer = AsyncConfigurationTransfer(
            laptop,
            shared,
            AsyncConfigurationProtocol(exchange),
            endpoint_label="Target one",
            journal_store=journal,
        )
        transfer.begin(base, "live", False)
        await transfer.areview(base)
        self.assertIsNone(await transfer.asend(base))
        self.assertEqual(transfer.view()["status"], "unknown")
        with self.assertRaises(ValueError):
            await transfer.asend(base)
        with self.assertRaises(ValueError):
            await transfer.acancel()
        result = await transfer.areconcile(base)
        self.assertEqual(result, watch.load())
        self.assertEqual(operations.count("commit"), 1)
        self.assertEqual(laptop.load(), watch.load())
        self.assertEqual(shared.load(), watch.load())

    async def test_finish_ack_loss_retains_verified_saved_content_and_return_does_not_upload(
        self,
    ):
        base = default_configuration()
        laptop, watch, shared, journal = [MemoryStore(base) for _ in range(4)]
        endpoint, operations = SimulatedWatch(watch), []
        fail_return = True

        async def exchange(message):
            operation = decode(message)["op"]
            operations.append(operation)
            response = endpoint.exchange(message)
            if operation == "finish" and fail_return:
                raise OSError("Return acknowledgement lost")
            return response

        transfer = AsyncConfigurationTransfer(
            laptop,
            shared,
            AsyncConfigurationProtocol(exchange),
            endpoint_label="Target one",
            journal_store=journal,
        )
        transfer.begin(base, "live", False)
        await transfer.areview(base)
        result = await transfer.asend(base)
        self.assertEqual(result, watch.load())
        self.assertEqual(transfer.view()["status"], "return_failed")
        self.assertIsNone(transfer.view()["pending"])
        self.assertTrue(transfer.view()["active"])
        with self.assertRaises(ValueError):
            await transfer.areview(result)
        with self.assertRaises(ValueError):
            await transfer.asend(result)
        fail_return = False
        self.assertTrue(await transfer.areturn())
        self.assertEqual(operations.count("commit"), 1)
        self.assertEqual(transfer.view()["status"], "success")

    async def test_cancelled_commit_retains_unknown_journal_and_emits_no_retry(self):
        base = default_configuration()
        laptop, watch, shared, journal = [MemoryStore(base) for _ in range(4)]
        endpoint, committed = SimulatedWatch(watch), asyncio.Event()
        operations = []

        async def exchange(message):
            operation = decode(message)["op"]
            operations.append(operation)
            response = endpoint.exchange(message)
            if operation == "commit":
                committed.set()
                await asyncio.Event().wait()
            return response

        transfer = AsyncConfigurationTransfer(
            laptop,
            shared,
            AsyncConfigurationProtocol(exchange),
            endpoint_label="Target one",
            journal_store=journal,
        )
        transfer.begin(base, "live", False)
        await transfer.areview(base)
        pending = asyncio.create_task(transfer.asend(base))
        await committed.wait()
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        self.assertEqual(transfer.view()["status"], "unknown")
        self.assertIsNotNone(transfer.view()["pending"])
        self.assertEqual(operations.count("commit"), 1)
        self.assertEqual(laptop.load(), base)
        self.assertEqual(shared.load(), base)

    async def test_saved_laptop_edit_during_staging_refreshes_and_preserves_watch(self):
        base = default_configuration()
        laptop, watch, shared, journal = [MemoryStore(base) for _ in range(4)]
        endpoint, operations = SimulatedWatch(watch), []
        changed = default_configuration()
        changed["revision"] = 1
        changed["alerts"]["speed"] = {"enabled": True, "threshold": 25}

        async def exchange(message):
            operation = decode(message)["op"]
            operations.append(operation)
            if operation == "validate":
                laptop.save(changed)
            return endpoint.exchange(message)

        transfer = AsyncConfigurationTransfer(
            laptop,
            shared,
            AsyncConfigurationProtocol(exchange),
            endpoint_label="Target one",
            journal_store=journal,
        )
        transfer.begin(base, "live", False)
        await transfer.areview(base)
        self.assertIsNone(await transfer.asend(base))
        self.assertEqual(transfer.view()["status"], "failed")
        self.assertEqual(transfer.view()["preview"]["laptop"], changed)
        self.assertEqual(transfer.local_saved, changed)
        self.assertNotIn("commit", operations)
        self.assertEqual(watch.load(), base)
        self.assertEqual(shared.load(), base)

    async def test_watch_post_preview_changes_refresh_conflicts_and_partial_staging_keeps_active_copy(
        self,
    ):
        base = default_configuration()
        laptop, watch, shared, journal = [MemoryStore(base) for _ in range(4)]
        endpoint, operations = SimulatedWatch(watch), []
        interrupt = False

        async def exchange(message):
            row = decode(message)
            operations.append(row["op"])
            if interrupt and row["op"] == "chunk" and row["index"] == 1:
                raise OSError("Controlled interrupted stage")
            return endpoint.exchange(message)

        changed = default_configuration()
        changed["revision"] = 1
        changed["alerts"]["pwm"] = {"enabled": True, "threshold": 80}
        laptop.save(changed)
        transfer = AsyncConfigurationTransfer(
            laptop,
            shared,
            AsyncConfigurationProtocol(exchange),
            endpoint_label="Target one",
            journal_store=journal,
        )
        transfer.begin(changed, "live", False)
        await transfer.areview(changed)
        watch_changed = default_configuration()
        watch_changed["revision"] = 1
        watch_changed["alerts"]["pwm"] = {"enabled": True, "threshold": 90}
        watch.save(watch_changed)
        self.assertIsNone(await transfer.asend(changed))
        self.assertEqual(
            transfer.view()["preview"]["conflicts"],
            [{"path": "alerts.pwm.threshold", "laptop": 80, "watch": 90}],
        )
        self.assertNotIn("stage", operations)
        transfer.choose("alerts.pwm.threshold", "watch")
        interrupt = True
        self.assertIsNone(await transfer.asend(changed))
        self.assertEqual(transfer.view()["status"], "failed")
        self.assertIsNone(transfer.view()["pending"])
        self.assertEqual(watch.load(), watch_changed)
        self.assertEqual(laptop.load(), changed)
        self.assertEqual(shared.load(), base)
        await transfer.acancel()
        self.assertEqual(transfer.view()["status"], "cancelled")
        self.assertTrue(await transfer.areturn())
