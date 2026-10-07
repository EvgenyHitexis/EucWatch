"""Read-only P22 Storage exporter. Requires an existing enabled BLE console.

Input identity JSON contains an address; all output belongs in a private
directory outside git. This tool never restores, resets, or writes Storage.
Nordic UART writes below carry console read expressions, not stored code.
"""

import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import time
import zlib

from bleak import BleakClient, BleakScanner

RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
CHUNK = 768


class Console:
    def __init__(self, client):
        self.client = client
        self.received = bytearray()

    def notification(self, _characteristic, data):
        self.received.extend(data)

    async def read(self, expression):
        marker = "P22READ_" + secrets.token_hex(5) + ":"
        command = ("\x10print(" + json.dumps(marker) + "+JSON.stringify(" + expression + "));\n").encode()
        self.received.clear()
        for offset in range(0, len(command), 20):
            await self.client.write_gatt_char(RX, command[offset:offset + 20], response=False)
            await asyncio.sleep(0.025)
        async with asyncio.timeout(15):
            while True:
                for line in self.received.decode(errors="replace").splitlines():
                    if marker in line:
                        try:
                            return json.loads(line.split(marker, 1)[1])
                        except json.JSONDecodeError:
                            pass
                await asyncio.sleep(0.025)

    async def inventory(self):
        # Avoid materializing three whole file lists together on a 64 KiB watch.
        result = {}
        for kind, expression in (
            ("all", 'require("Storage").list()'),
            ("normal", 'require("Storage").list(undefined,{sf:false})'),
            ("stream", 'require("Storage").list(undefined,{sf:true})'),
        ):
            count = await self.read(expression + ".length")
            result[kind] = []
            for start in range(0, count, 8):
                result[kind].extend(await self.read(expression + f".slice({start},{start + 8})"))
            if len(result[kind]) != count:
                raise RuntimeError("Storage inventory changed while enumerating")
        return result


def save_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=True) + "\n")


async def export(args):
    os.umask(0o077)
    repo = Path(__file__).resolve().parents[2]
    if args.output.resolve().is_relative_to(repo):
        raise ValueError("Private watch backups must be outside the repository")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.chmod(0o700)
    (args.output / "files").mkdir(mode=0o700, exist_ok=True)
    identity = json.loads(args.identity.read_text())
    device = await BleakScanner.find_device_by_address(identity["address"], timeout=15)
    if device is None:
        raise RuntimeError("Known watch is not advertising; no hardware change attempted")
    manifest = {"schema": 1, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "complete": False, "files": [], "storage_files": []}
    async with BleakClient(device, timeout=20) as client:
        console = Console(client)
        await client.start_notify(TX, console.notification)
        # Existing eucWatch handler recognizes Ctrl-C as console selection.
        await client.write_gatt_char(RX, b"\x03", response=False)
        await asyncio.sleep(1)
        manifest["firmware"] = await console.read("process.env")
        if manifest["firmware"].get("BOARD") != "P22" or manifest["firmware"].get("VERSION") != "2v14":
            raise RuntimeError("Watch identity differs from expected P22/2v14")
        manifest["initial_memory"] = await console.read("process.memory()")
        manifest["initial_inventory"] = await console.inventory()
        manifest["graphics"] = await console.read(
            '(function(g){return {width:g.getWidth(),height:g.getHeight(),bpp:g.getBPP(),'
            'bufferBytes:g.buffer?g.buffer.byteLength:null}})(w.gfx)')
        manifest["driver_runtime"] = await console.read(
            '({batteryFunction:w.batt.toString(),buzzerKeys:Object.keys(buzzer),'
            'pins:ew.pin,activeHardware:{acc:ew.def.acctype,touch:ew.def.touchtype,'
            'touchReset:ew.def.rstP,touchSleep:ew.def.rstR,bpp:ew.def.bpp,cli:ew.def.cli}})')
        manifest["crc_api"] = await console.read(
            '({available:typeof E.CRC32==="function",test:typeof E.CRC32==="function"?E.CRC32("123456789"):null})')
        crc_supported = (manifest["crc_api"]["test"] is not None
                         and (manifest["crc_api"]["test"] & 0xffffffff) == zlib.crc32(b"123456789"))
        save_json(args.output / "manifest.json", manifest)
        print(json.dumps({"connected": True, "normal_files": len(manifest["initial_inventory"]["normal"]),
                          "storage_files": len(manifest["initial_inventory"]["stream"]),
                          "graphics": manifest["graphics"], "crc_api_verified": crc_supported}), flush=True)

        async def read_file(name, kind):
            encoded = json.dumps(name, ensure_ascii=True)
            length = await console.read('(function(s){return s===undefined?null:s.length})(require("Storage").read(' + encoded + '))')
            if length is None:
                return None
            content = bytearray()
            for offset in range(0, length, CHUNK):
                value = await console.read(f'btoa(require("Storage").read({encoded},{offset},{CHUNK}))')
                part = base64.b64decode(value, validate=True)
                if len(part) != min(CHUNK, length - offset):
                    raise RuntimeError("Unexpected file read length; snapshot not complete")
                content.extend(part)
            remote_crc = None
            if crc_supported:
                remote_crc = await console.read(f'E.CRC32(require("Storage").read({encoded}))')
                if (remote_crc & 0xffffffff) != zlib.crc32(content):
                    raise RuntimeError("File changed during export or transfer differs from remote CRC")
            else:
                # No compatible native checksum: independently reread exact chunks.
                for offset in range(0, length, CHUNK):
                    value = await console.read(f'btoa(require("Storage").read({encoded},{offset},{CHUNK}))')
                    if base64.b64decode(value, validate=True) != content[offset:offset + CHUNK]:
                        raise RuntimeError("File differs on verification read")
            path = f"files/{len(manifest['files']):04d}.bin"
            (args.output / path).write_bytes(content)
            entry = {"name": name, "kind": kind, "path": path, "bytes": len(content),
                     "sha256": hashlib.sha256(content).hexdigest(),
                     "crc32": f"{zlib.crc32(content):08x}",
                     "verified": "remote-crc32" if crc_supported else "second-read"}
            manifest["files"].append(entry)
            save_json(args.output / "manifest.json", manifest)
            return entry

        for index, name in enumerate(manifest["initial_inventory"]["normal"]):
            if await read_file(name, "normal") is None:
                raise RuntimeError("An inventoried file disappeared during export")
            if (index + 1) % 10 == 0:
                print(f"Exported and verified {index + 1} ordinary files", flush=True)

        for name in manifest["initial_inventory"]["stream"]:
            # Raw numbered chunks preserve their padding and physical bytes.
            # Restore MUST use StorageFile.open('w') + write(logical contents),
            # not Storage.write of these raw names (which would lose flags).
            chunks = []
            for number in range(1, 256):
                entry = await read_file(name + chr(number), "storage-file-chunk")
                if entry is None:
                    break
                chunks.append(entry["path"])
            manifest["storage_files"].append({"name": name, "raw_chunk_paths": chunks})
            save_json(args.output / "manifest.json", manifest)
        manifest["final_inventory"] = await console.inventory()
        manifest["inventory_stable"] = manifest["initial_inventory"] == manifest["final_inventory"]
        manifest["final_memory"] = await console.read("process.memory()")
        await client.stop_notify(TX)
    manifest["complete"] = manifest["inventory_stable"]
    manifest["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    manifest["restore_constraints"] = [
        "Application Storage backup only; not firmware, bootloader, SoftDevice, bonding data or full flash image.",
        "Restore to matching retained P22/Espruino runtime with boot/startup inactive; validate hashes first.",
        "Normal files use exact binary contents; restore entry points last under a separately reviewed procedure.",
        "StorageFile chunks require flag-aware logical reconstruction; never write raw chunks as normal files.",
        "The live application was not paused. Per-file verification and inventory stability do not prove an atomic whole-device snapshot.",
    ]
    save_json(args.output / "manifest.json", manifest)
    print(json.dumps({"disconnected": True, "complete": manifest["complete"],
        "exported_files": len(manifest["files"]),
        "exported_bytes": sum(f["bytes"] for f in manifest["files"])}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(export(parser.parse_args()))
