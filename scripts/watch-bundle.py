#!/usr/bin/env python3
"""Build, verify and rehearse watch bundles locally. There is no deployment path."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "laptop"))
from eucwatch.installation import Bundle, Installer, Preconditions, PrivateBackup, build_bundle  # noqa: E402


class RehearsalStorage:
    """Explicit synthetic ordinary-file device; no Bluetooth imports or access."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.files = {".bootrst": b"synthetic old startup"}
        self.effects = []

    def runtime(self):
        return {"BOARD": "P22", "VERSION": "2v14"}

    def free_bytes(self):
        return self.capacity

    def list_files(self):
        return list(self.files)

    def read(self, name):
        return self.files.get(name)

    def write(self, name, content):
        self.files[name] = bytes(content)
        self.effects.append(name)

    def erase(self, name):
        self.files.pop(name, None)
        self.effects.append("erase:" + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Create a new local exact-byte bundle directory")
    build.add_argument("--source", type=Path, default=ROOT / "watch")
    build.add_argument("--version", required=True)
    build.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify", help="Verify retained local bundle checksums")
    verify.add_argument("bundle", type=Path)
    backup = commands.add_parser("verify-backup", help="Verify private exported backup without printing filenames/content")
    backup.add_argument("directory", type=Path)
    rehearsal = commands.add_parser("rehearse", help="Plan, stage and activate using synthetic Storage only")
    rehearsal.add_argument("bundle", type=Path)
    rehearsal.add_argument("--free-bytes", type=int, default=1_000_000)
    args = parser.parse_args()
    if args.command == "verify-backup":
        retained = PrivateBackup.load(args.directory)
        result = {"status": "local-backup-verified", "files": len(retained.files),
                  "bytes": sum(len(content) for _name, content in retained.files),
                  "manifest_sha256": hashlib.sha256((args.directory / "manifest.json").read_bytes()).hexdigest(),
                  "device_revalidation": "required before authorized deployment", "firmware_backup": False}
    else:
        if args.command == "build":
            bundle = build_bundle(args.source, args.version)
            bundle.write(args.output)
        else:
            bundle = Bundle.load(args.bundle)
        result = {"status": "local-bundle-verified", "version": bundle.version,
                  "files": len(bundle.files), "bytes": sum(len(content) for _name, content in bundle.files),
                  "deployment": "not performed; full application, laptop acceptance and separate authorization required"}
        if args.command == "rehearse":
            device = RehearsalStorage(args.free_bytes)
            retained = PrivateBackup.from_bytes(device.files)
            # These permissions apply solely to the explicit synthetic adapter.
            permissions = Preconditions(laptop_accepted=True, deployment_authorized=True, complete_application=True)
            installer = Installer(device)
            plan = installer.plan(bundle, retained, permissions, first_install=True)
            installer.stage(bundle, retained, permissions, first_install=True)
            assert device.read(".bootrst") == b"synthetic old startup"
            outcome = installer.activate(bundle, retained, permissions, first_install=True)
            result.update({"provenance": "synthetic Storage/runtime/authorization only", "plan": plan,
                           "outcome": outcome, "writes": device.effects, "hardware": "none"})
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("Preparation refused: " + str(exc), file=sys.stderr)
        raise SystemExit(1) from None
