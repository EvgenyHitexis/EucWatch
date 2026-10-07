"""Observe an owner-operated recovery round trip without initiating a reset.

The owner holds/releases/presses the watch button. This tool only scans the
known identity and reads its existing console; it never creates/erases the
developer-mode marker itself. Run one phase at a time.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
import time

from bleak import BleakClient, BleakScanner
from export_storage import Console, RX, TX, save_json


async def main(args):
    os.umask(0o077)
    address = json.loads(args.identity.read_text())["address"]
    expected_name = "Espruino-devmode" if args.phase == "developer" else "eucWatch"
    ready = asyncio.Event()
    observed = {}
    started = time.monotonic()
    last_name = None

    def detect(device, advertisement):
        nonlocal last_name
        if device.address.lower() != address.lower():
            return
        name = advertisement.local_name
        if name != last_name:
            print(json.dumps({"known_watch_name": name, "elapsed_s": round(time.monotonic()-started,1)}), flush=True)
            last_name = name
        # Names may be shortened to fit an advertisement. Identity is still
        # matched by the known private address and mode verified via console.
        if name == expected_name or (args.phase == "developer" and name and name.startswith("Espruino-dev")):
            observed.update(device=device, name=name, elapsed=time.monotonic() - started)
            ready.set()

    print("Observing known watch for " + expected_name, flush=True)
    async with BleakScanner(detect):
        await asyncio.wait_for(ready.wait(), timeout=120)
    # Let the owner release a held button and the runtime finish startup.
    await asyncio.sleep(4 if args.phase == "developer" else 2)
    async with BleakClient(observed["device"], timeout=20) as client:
        console = Console(client)
        await client.start_notify(TX, console.notification)
        await client.write_gatt_char(RX, b"\x03", response=False)
        await asyncio.sleep(1)
        state = await console.read(
            '({board:process.env.BOARD,version:process.version,runtimeTime:getTime(),'
            'devmode:require("Storage").read("devmode")||null,'
            'displayLoaded:typeof w!=="undefined",wheelAppLoaded:typeof euc!=="undefined",'
            'bootCrc:E.CRC32(require("Storage").read(".bootrst")),'
            'storedCli:(require("Storage").readJSON("ew.json",1)||{}).cli})')
        if state["board"] != "P22" or state["version"] != "2v14":
            raise RuntimeError("Unexpected runtime identity")
        expected_crc = next(f["crc32"] for f in json.loads((args.backup / "manifest.json").read_text())["files"] if f["name"] == ".bootrst")
        if f'{state["bootCrc"] & 0xffffffff:08x}' != expected_crc:
            raise RuntimeError("Startup file differs from backup")
        if args.phase == "developer":
            if state["devmode"] != "done" or state["displayLoaded"] or state["wheelAppLoaded"]:
                raise RuntimeError("Advertised mode does not match expected developer state")
        else:
            if state["devmode"] is not None or not state["displayLoaded"] or not state["wheelAppLoaded"]:
                raise RuntimeError("Expected working application did not return")
        await client.stop_notify(TX)
    result = {"phase": args.phase, "observed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "advertised_name": observed["name"], "discovery_elapsed_s": observed["elapsed"],
              "console_read_succeeded": True, "startup_crc_matches_backup": True,
              "state": state, "status": "pass", "disconnected": True}
    save_json(args.output, result)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=["developer", "working"], required=True)
    asyncio.run(main(parser.parse_args()))
