"""Application Storage preparation with injected adapters; no live device access."""

import hashlib
import json
import re
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class DeviceStorage(Protocol):
    """Ordinary files only. Implementations preserve exact bytes and allocation."""

    def runtime(self) -> dict[str, str]: ...
    def free_bytes(self) -> int: ...
    def list_files(self) -> list[str]: ...
    def read(self, name: str) -> bytes | None: ...
    def write(self, name: str, content: bytes) -> None: ...
    def erase(self, name: str) -> None: ...


def checksum(content: bytes) -> dict[str, Any]:
    return {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
            "crc32": f"{zlib.crc32(content):08x}"}


@dataclass(frozen=True)
class Bundle:
    version: str
    files: tuple[tuple[str, bytes], ...]
    recovery_name: str

    def manifest(self) -> dict[str, Any]:
        return {"schema": 1, "version": self.version, "runtime": {"BOARD": "P22", "VERSION": "2v14"},
                "main": f"sw-{self.version}-main", "recovery": self.recovery_name,
                "files": [{"name": name, **checksum(content)} for name, content in self.files]}

    def pointer(self) -> bytes:
        return json.dumps({"schema": 1, "version": self.version, "main": f"sw-{self.version}-main"}, sort_keys=True).encode()

    def recovery(self) -> bytes:
        return dict(self.files)[self.recovery_name]

    def write(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=False)
        for name, content in self.files:
            (directory / (name + ".bin")).write_bytes(content)
        (directory / "manifest.json").write_text(json.dumps(self.manifest(), indent=2) + "\n")

    @classmethod
    def load(cls, directory: Path) -> "Bundle":
        manifest = json.loads((directory / "manifest.json").read_text())
        version = manifest.get("version")
        if not isinstance(version, str) or not re.fullmatch(r"[a-z0-9]{1,8}", version):
            raise ValueError("Unsupported bundle version")
        if manifest.get("schema") != 1 or manifest.get("runtime") != {"BOARD": "P22", "VERSION": "2v14"}:
            raise ValueError("Unsupported bundle format/runtime")
        files = []
        for entry in manifest.get("files", []):
            name = entry.get("name", "")
            if not re.fullmatch(f"sw-{version}-[a-z-]+", name) or len(name.encode()) > 28:
                raise ValueError("Invalid versioned filename")
            content = (directory / (name + ".bin")).read_bytes()
            if checksum(content) != {key: entry.get(key) for key in ("bytes", "sha256", "crc32")}:
                raise ValueError("Bundle checksum mismatch")
            files.append((name, content))
        bundle = cls(version, tuple(files), f"sw-{version}-boot")
        if manifest != bundle.manifest() or len({name for name, _content in files}) != len(files):
            raise ValueError("Bundle manifest differs or repeats files")
        names = {name for name, _content in files}
        if not {f"sw-{version}-main", bundle.recovery_name}.issubset(names):
            raise ValueError("Bundle is incomplete")
        for _name, content in files:
            for dependency in re.findall(rb"require\(['\"](sw-[^'\"]+)['\"]\)", content):
                if dependency.decode() not in names:
                    raise ValueError("Bundle dependency missing")
        return bundle


def build_bundle(source: Path, version: str) -> Bundle:
    if not re.fullmatch(r"[a-z0-9]{1,8}", version):
        raise ValueError("Version must contain 1–8 lowercase letters or digits")
    files = []
    for path in sorted(source.glob("*.js")):
        name = f"sw-{version}-{path.stem}"
        if len(name.encode()) > 28:
            raise ValueError("Versioned Storage name exceeds 28 bytes")
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"require\((['\"])sw-([a-z-]+)\1\)",
                      lambda match: f"require({match[1]}sw-{version}-{match[2]}{match[1]})", text)
        files.append((name, text.encode()))
    notice = source / "THIRD_PARTY.md"
    if notice.exists():
        files.append((f"sw-{version}-notice", notice.read_bytes()))
    names = {name for name, _content in files}
    if not {f"sw-{version}-main", f"sw-{version}-boot"}.issubset(names):
        raise ValueError("Bundle needs main and independent boot source")
    for _name, content in files:
        for dependency in re.findall(rb"require\(['\"](sw-[^'\"]+)['\"]\)", content):
            if dependency.decode() not in names:
                raise ValueError("Bundle is missing a versioned module dependency")
    return Bundle(version, tuple(files), f"sw-{version}-boot")


@dataclass(frozen=True)
class PrivateBackup:
    files: tuple[tuple[str, bytes], ...]

    @classmethod
    def from_bytes(cls, files: dict[str, bytes]) -> "PrivateBackup":
        if any(not isinstance(name, str) or not name or len(name.encode()) > 28
               or any(ord(char) < 32 or ord(char) > 126 for char in name) for name in files):
            raise ValueError("Invalid ordinary Storage filename")
        if ".varimg" in files:
            raise ValueError("Saved interpreter images need a separate reviewed restoration procedure")
        return cls(tuple(sorted((name, bytes(content)) for name, content in files.items())))

    @classmethod
    def load(cls, directory: Path) -> "PrivateBackup":
        directory = directory.resolve()
        repository = Path(__file__).resolve().parents[2]
        if directory.is_relative_to(repository):
            raise ValueError("Private backup must remain outside the repository")
        manifest = json.loads((directory / "manifest.json").read_text())
        if manifest.get("schema") != 1 or manifest.get("complete") is not True or manifest.get("inventory_stable") is not True:
            raise ValueError("Private export is incomplete or inventory changed")
        firmware = manifest.get("firmware", {})
        if firmware.get("BOARD") != "P22" or firmware.get("VERSION") != "2v14":
            raise ValueError("Private backup runtime differs from P22/2v14")
        initial, final = manifest.get("initial_inventory", {}), manifest.get("final_inventory", {})
        if initial != final:
            raise ValueError("Private backup inventory differs")
        if manifest.get("storage_files") or initial.get("stream"):
            raise ValueError("StorageFile flags require logical reconstruction; raw chunk restoration refused")
        files = {}
        for entry in manifest.get("files", []):
            name = entry["name"]
            path = (directory / entry["path"]).resolve()
            if not path.is_relative_to(directory) or entry.get("kind") != "normal" or name in files:
                raise ValueError("Invalid ordinary-file backup entry or flags")
            content = path.read_bytes()
            if checksum(content) != {key: entry.get(key) for key in ("bytes", "sha256", "crc32")}:
                raise ValueError("Private backup checksum mismatch")
            files[name] = content
        if set(files) != set(initial.get("normal", [])) or set(files) != set(initial.get("all", [])):
            raise ValueError("Private backup inventory is incomplete")
        if ".bootrst" not in files:
            raise ValueError("Private backup has no recovery startup")
        return cls.from_bytes(files)


@dataclass(frozen=True)
class Preconditions:
    laptop_accepted: bool = False
    deployment_authorized: bool = False
    complete_application: bool = False
    recovery_sha256: str | None = None
    console_recovery_verified: bool = False
    custom_startup_controls_verified: bool = False


class Installer:
    def __init__(self, device: DeviceStorage):
        self.device = device

    def plan(self, bundle: Bundle, backup: PrivateBackup, permissions: Preconditions,
             *, first_install: bool = False) -> dict[str, Any]:
        if not all((permissions.laptop_accepted, permissions.deployment_authorized, permissions.complete_application)):
            raise ValueError("Laptop acceptance, complete application and separate deployment authorization required")
        runtime = self.device.runtime()
        if runtime.get("BOARD") != "P22" or runtime.get("VERSION") != "2v14":
            raise ValueError("Expected installed P22 Espruino 2v14 runtime")
        if not backup.files or ".bootrst" not in dict(backup.files):
            raise ValueError("Verified private backup with intact startup required")
        if not first_install:
            startup = self.device.read(".bootrst")
            if startup is None or checksum(startup)["sha256"] != permissions.recovery_sha256:
                raise ValueError("Verified independent recovery startup hash required for an update")
        for name, content in bundle.files:
            existing = self.device.read(name)
            if existing is not None and existing != content:
                raise ValueError("Existing version has different bytes; use a new version and review damaged staging")
        required = sum(((len(content) + 3) // 4 * 4 + 64)
                       for name, content in bundle.files if self.device.read(name) != content)
        required += len(bundle.pointer()) + 64
        if first_install:
            required += len(bundle.recovery()) + 64
        if self.device.free_bytes() < required:
            raise ValueError("Insufficient Storage; revise procedure before any deletion")
        return {"required_bytes": required, "available_bytes": self.device.free_bytes(),
                "first_install": first_install, "writes": [name for name, _content in bundle.files],
                "activation_last": "sw-active.json", "deletions": []}

    def stage(self, bundle: Bundle, backup: PrivateBackup, permissions: Preconditions,
              *, first_install: bool = False) -> None:
        self.plan(bundle, backup, permissions, first_install=first_install)
        for name, content in bundle.files:
            if self.device.read(name) == content:
                continue
            self.device.write(name, content)
            if self.device.read(name) != content:
                raise ValueError("Staged content checksum mismatch; startup remains unchanged")

    def activate(self, bundle: Bundle, backup: PrivateBackup, permissions: Preconditions,
                 *, first_install: bool = False) -> dict[str, str]:
        self.plan(bundle, backup, permissions, first_install=first_install)
        if any(self.device.read(name) != content for name, content in bundle.files):
            raise ValueError("Incomplete or changed staging; activation refused")
        if first_install:
            self.device.write(".bootrst", bundle.recovery())
            if self.device.read(".bootrst") != bundle.recovery():
                raise ValueError("Recovery startup checksum mismatch; activation refused")
        try:
            self.device.write("sw-active.json", bundle.pointer())
        except OSError:
            return {"status": "unknown", "reason": "Activation acknowledgement lost; read back before retry"}
        return self.reconcile(bundle)

    def reconcile(self, bundle: Bundle) -> dict[str, str]:
        try:
            active = self.device.read("sw-active.json")
            complete = all(self.device.read(name) == content for name, content in bundle.files)
        except OSError:
            return {"status": "unknown", "reason": "Active content could not be read"}
        if active == bundle.pointer() and complete:
            return {"status": "verified"}
        return {"status": "not-active" if active != bundle.pointer() else "invalid", "reason": "Review active pointer/content before retry"}

    def restore_historical(self, backup: PrivateBackup, permissions: Preconditions) -> dict[str, str]:
        if not permissions.deployment_authorized or not permissions.console_recovery_verified:
            raise ValueError("Separate restoration authorization and verified console with app stopped required")
        runtime = self.device.runtime()
        if runtime.get("BOARD") != "P22" or runtime.get("VERSION") != "2v14":
            raise ValueError("Historical restoration requires retained P22/2v14 runtime")
        if ".bootrst" not in dict(backup.files):
            raise ValueError("Historical backup startup missing")
        if set(self.device.list_files()) - {name for name, _content in backup.files}:
            raise ValueError("Unexpected inventory; review explicit removal before restoration")
        required = sum(len(content) + 64 for name, content in backup.files if self.device.read(name) != content)
        if self.device.free_bytes() < required:
            raise ValueError("Insufficient Storage; revise restoration procedure before deletion")
        ordered = sorted(backup.files, key=lambda entry: (entry[0].startswith(".boot"), entry[0] == ".bootrst", entry[0]))
        for name, content in ordered:
            self.device.write(name, content)
            if self.device.read(name) != content:
                raise ValueError("Historical checksum mismatch; do not restart")
        if set(self.device.list_files()) != {name for name, _content in backup.files}:
            raise ValueError("Historical inventory differs; do not restart")
        return {"status": "verified"}

    def remove_legacy(self, bundle: Bundle, reviewed: dict[str, str], permissions: Preconditions) -> None:
        if not permissions.deployment_authorized or not permissions.custom_startup_controls_verified:
            raise ValueError("Separate authorization and verified custom startup/controls required before removal")
        if self.reconcile(bundle)["status"] != "verified":
            raise ValueError("Active custom application must be verified before legacy removal")
        for name, expected in reviewed.items():
            if name.startswith("sw-") or name.startswith(".boot") or name == ".varimg":
                raise ValueError("Startup/custom files are protected from legacy removal")
            content = self.device.read(name)
            if content is None or checksum(content)["sha256"] != expected:
                raise ValueError("Reviewed legacy inventory changed; refresh review")
        for name in reviewed:
            content = self.device.read(name)
            if content is None or checksum(content)["sha256"] != reviewed[name]:
                raise ValueError("Legacy content changed during removal; remaining files preserved")
            self.device.erase(name)
            if self.device.read(name) is not None:
                raise ValueError("Legacy deletion could not be verified")
