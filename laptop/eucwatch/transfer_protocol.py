"""Version-one configuration protocol planned for Nordic UART.

JSONL messages are at most 512 bytes and data chunks at most 64 decoded bytes;
an eventual BLE adapter may fragment those lines to the discovered write size.
No console expression or wheel packet is part of this protocol. The simulated
endpoint exercises the same byte messages, staging and readback contracts.
"""

import base64
import hashlib
import json
import zlib
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from .configuration import default_configuration, validate_configuration
from .persistence import MAX_CONFIG_BYTES, ConfigStore

NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_WRITE = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_NOTIFY = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
MAX_MESSAGE_BYTES = 512
CHUNK_BYTES = 64


class ScenarioTransport:
    """Explicit fault controls for the simulated watch byte protocol only."""

    def __init__(self, endpoint: "SimulatedWatch"):
        self.endpoint = endpoint
        self.values = {"stage": "normal", "commit": "normal", "readback": "normal"}
        self.committed = False

    def configure(self, values: dict[str, Any]) -> None:
        allowed = {"stage": ("normal", "interrupt"), "commit": ("normal", "lost_ack"), "readback": ("normal", "fail")}
        if not values or set(values) - allowed.keys() or any(value not in allowed[key] for key, value in values.items()):
            raise ValueError("Invalid simulated configuration-transfer scenario")
        self.values.update(values)

    def exchange(self, message: bytes) -> bytes:
        row = decode(message)
        if row["op"] == "chunk" and self.values["stage"] == "interrupt" and row["index"] >= 1:
            raise OSError("Controlled staging interruption; prior active copy preserved")
        if row["op"] == "read" and self.values["readback"] == "fail" and self.committed:
            raise OSError("Controlled saved-content readback failure")
        response = self.endpoint.exchange(message)
        if row["op"] == "commit":
            self.committed = True
            if self.values["commit"] == "lost_ack":
                raise OSError("Controlled activation acknowledgement loss")
        return response


def content_bytes(config: dict[str, Any]) -> bytes:
    data = json.dumps(
        validate_configuration(config),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    if len(data) > MAX_CONFIG_BYTES:
        raise ValueError("Configuration exceeds 32 KiB")
    return data


def encode(row: dict[str, Any]) -> bytes:
    data = (
        json.dumps({"protocol": 1, **row}, allow_nan=False, separators=(",", ":"))
        + "\n"
    ).encode()
    if len(data) > MAX_MESSAGE_BYTES:
        raise ValueError("Configuration protocol message exceeds 512 bytes")
    return data


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate protocol field")
        result[key] = value
    return result


def decode(data: bytes) -> dict[str, Any]:
    if (
        not isinstance(data, bytes)
        or len(data) > MAX_MESSAGE_BYTES
        or not data.endswith(b"\n")
        or b"\n" in data[:-1]
    ):
        raise ValueError("A bounded JSONL configuration message is required")
    try:
        row = json.loads(data, object_pairs_hook=_object)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("Invalid configuration protocol JSON") from exc
    if (
        not isinstance(row, dict)
        or type(row.get("protocol")) is not int
        or row["protocol"] != 1
    ):
        raise ValueError("Unsupported configuration protocol")
    return row


def unpack(row: dict[str, Any]) -> bytes:
    try:
        data = base64.b64decode(row["data"], validate=True)
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("Invalid configuration chunk") from exc
    if (
        not 0 < len(data) <= CHUNK_BYTES
        or type(row.get("crc32")) is not int
        or zlib.crc32(data) != row["crc32"]
    ):
        raise ValueError("Configuration chunk CRC/size mismatch")
    return data


def chunk(data: bytes, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "data": base64.b64encode(data).decode(),
        "crc32": zlib.crc32(data),
    }


class SimulatedWatch:
    """One saved configuration and bounded staging, with no wheel capability."""

    def __init__(self, store: ConfigStore):
        self.store = store
        self.error: str | None = None
        self.active = default_configuration()
        try:
            loaded = store.load()
            if loaded is not None:
                self.active = validate_configuration(loaded)
            self.error = store.warning
        except (OSError, ValueError) as exc:
            self.error = f"Saved watch configuration requires review: {exc}"
        self.staging: dict[str, Any] | None = None
        self.snapshot = b""

    def exchange(self, message: bytes) -> bytes:
        row = decode(message)
        op = row.get("op")
        if op in ("read", "stage", "commit"):
            saved = self.store.load()
            self.active = (
                default_configuration()
                if saved is None
                else validate_configuration(saved)
            )
        if op == "read":
            self.snapshot = content_bytes(self.active)
            result = {
                "revision": self.active["revision"],
                "size": len(self.snapshot),
                "digest": hashlib.sha256(self.snapshot).hexdigest(),
            }
        elif op == "read_chunk":
            index = row.get("index")
            if type(index) is not int or index < 0:
                raise ValueError("Invalid configuration chunk index")
            data = self.snapshot[index * CHUNK_BYTES : (index + 1) * CHUNK_BYTES]
            if not data:
                raise ValueError("Configuration read chunk is unavailable")
            result = chunk(data, index)
        elif op == "stage":
            size, revision, digest = (
                row.get("size"),
                row.get("expected_revision"),
                row.get("digest"),
            )
            expected_digest = row.get("expected_digest")
            if (
                type(size) is not int
                or not 0 < size <= MAX_CONFIG_BYTES
                or type(revision) is not int
                or revision != self.active["revision"]
                or expected_digest
                != hashlib.sha256(content_bytes(self.active)).hexdigest()
                or not isinstance(digest, str)
                or len(digest) != 64
            ):
                raise ValueError("Invalid or stale configuration staging request")
            self.staging = {
                "size": size,
                "digest": digest,
                "expected_revision": revision,
                "expected_digest": expected_digest,
                "data": bytearray(),
                "next_index": 0,
                "candidate": None,
            }
            result = {"staged": False}
        elif op == "chunk":
            stage = self._stage()
            if type(row.get("index")) is not int or row["index"] != stage["next_index"]:
                raise ValueError("Configuration chunks must arrive in order")
            data = unpack(row)
            if len(stage["data"]) + len(data) > stage["size"]:
                raise ValueError("Configuration staging overflow")
            stage["data"].extend(data)
            stage["next_index"] += 1
            stage["candidate"] = None
            result = {"received": len(stage["data"])}
        elif op == "validate":
            stage = self._stage()
            data = bytes(stage["data"])
            if (
                len(data) != stage["size"]
                or hashlib.sha256(data).hexdigest() != stage["digest"]
            ):
                raise ValueError("Incomplete or corrupt staged configuration")
            candidate = validate_configuration(
                json.loads(data, object_pairs_hook=_object)
            )
            if candidate["revision"] <= stage["expected_revision"]:
                raise ValueError("Configuration activation requires a new revision")
            stage["candidate"] = candidate
            result = {"validated": True}
        elif op == "commit":
            stage = self._stage()
            if (
                stage["candidate"] is None
                or self.active["revision"] != stage["expected_revision"]
                or hashlib.sha256(content_bytes(self.active)).hexdigest()
                != stage["expected_digest"]
            ):
                raise ValueError(
                    "Configuration changed or was not validated before commit"
                )
            candidate = deepcopy(stage["candidate"])
            self.store.save(candidate)
            self.active = candidate
            self.staging = None
            result = {"revision": candidate["revision"]}
        elif op == "abort":
            self.staging = None
            result = {"aborted": True}
        else:
            raise ValueError("Unsupported configuration protocol operation")
        return encode({"ok": True, "op": op, **result})

    def _stage(self) -> dict[str, Any]:
        if self.staging is None:
            raise ValueError("No configuration transfer is staged")
        return self.staging


class ConfigurationProtocol:
    def __init__(self, exchange: Callable[[bytes], bytes]):
        self.exchange = exchange

    def request(self, op: str, **fields: Any) -> dict[str, Any]:
        row = decode(self.exchange(encode({"op": op, **fields})))
        if row.get("ok") is not True or row.get("op") != op:
            raise ValueError(
                str(row.get("error", "Configuration protocol response mismatch"))
            )
        return row

    def read(self) -> dict[str, Any]:
        info = self.request("read")
        size = info.get("size")
        if type(size) is not int or not 0 < size <= MAX_CONFIG_BYTES:
            raise ValueError("Invalid saved configuration size")
        data = bytearray()
        for index in range((size + CHUNK_BYTES - 1) // CHUNK_BYTES):
            row = self.request("read_chunk", index=index)
            if type(row.get("index")) is not int or row["index"] != index:
                raise ValueError("Configuration readback order mismatch")
            data.extend(unpack(row))
        if len(data) != size or hashlib.sha256(data).hexdigest() != info.get("digest"):
            raise ValueError("Saved configuration readback hash/size mismatch")
        config = validate_configuration(json.loads(data, object_pairs_hook=_object))
        if config["revision"] != info.get("revision"):
            raise ValueError("Saved configuration revision mismatch")
        return config

    def upload(self, config: dict[str, Any], expected: dict[str, Any], before_commit: Callable[[], None] | None = None) -> None:
        data = content_bytes(config)
        self.request(
            "stage",
            expected_revision=expected["revision"],
            size=len(data),
            expected_digest=hashlib.sha256(content_bytes(expected)).hexdigest(),
            digest=hashlib.sha256(data).hexdigest(),
        )
        for index, offset in enumerate(range(0, len(data), CHUNK_BYTES)):
            self.request("chunk", **chunk(data[offset : offset + CHUNK_BYTES], index))
        self.request("validate")
        if before_commit is not None:
            before_commit()
        self.request("commit")
