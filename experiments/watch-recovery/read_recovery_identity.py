"""Bounded read-only P22 chip/SoftDevice metadata; no DFU or reset commands.

Use only after a Storage backup; pass the same private identity JSON. Registers
are the nRF52832 FICR/UICR and Nordic SDK12 SoftDevice info whitelist cited in
docs/research/p22-backup-recovery.md. Does not read unique chip identifiers.
"""

import argparse
import asyncio
import json
import hashlib
import os
from pathlib import Path

from bleak import BleakClient, BleakScanner
from export_storage import Console, RX, TX, save_json


async def main(args):
    os.umask(0o077)
    manifest = json.loads((args.backup / "manifest.json").read_text())
    if not manifest["complete"]:
        raise RuntimeError("Storage export is not complete")
    for entry in manifest["files"]:
        contents = (args.backup / entry["path"]).read_bytes()
        if len(contents) != entry["bytes"] or hashlib.sha256(contents).hexdigest() != entry["sha256"]:
            raise RuntimeError("Local backup integrity check failed")
    address = json.loads(args.identity.read_text())["address"]
    device = await BleakScanner.find_device_by_address(address, timeout=15)
    if device is None:
        raise RuntimeError("Known watch not advertising")
    async with BleakClient(device, timeout=20) as client:
        console = Console(client)
        await client.start_notify(TX, console.notification)
        await client.write_gatt_char(RX, b"\x03", response=False)
        await asyncio.sleep(1)
        identity = await console.read('({board:process.env.BOARD,version:process.version})')
        if identity != {"board": "P22", "version": "2v14"}:
            raise RuntimeError("Unexpected watch firmware identity")
        result = {"runtime": identity}
        result["registers"] = await console.read(
            '({part:peek32(0x10000100),variant:peek32(0x10000104),'
            'package:peek32(0x10000108),ramKiB:peek32(0x1000010C),'
            'flashKiB:peek32(0x10000110),bootloaderAddress:peek32(0x10001014),'
            'mbrParameterPage:peek32(0x10001018),sdInfoSize:peek8(0x3000),'
            'applicationAddress:peek32(0x3008),softdeviceFirmwareId:peek16(0x300C)})')
        registers = result["registers"]
        if registers["part"] != 0x52832 or registers["ramKiB"] != 64 or registers["flashKiB"] != 512:
            raise RuntimeError("Chip metadata differs; no further memory reads")
        size = registers["sdInfoSize"]
        if 0x10 < size <= 0x40:
            registers["softdeviceId"] = await console.read('peek32(0x3010)')
        if 0x14 < size <= 0x40:
            registers["softdeviceVersion"] = await console.read('peek32(0x3014)')
        start = registers["applicationAddress"]
        boot = registers["bootloaderAddress"]
        if (0x4000 <= start < boot <= 512 * 1024 - 4096
                and start % 4096 == 0 and start + 256 <= boot):
            result["application_prefix_256_crc32"] = f'{(await console.read(f"E.CRC32(peek8({start},256))")) & 0xffffffff:08x}'
        result["stored_hardware"] = await console.read(
            '(function(s){return {bpp:s.bpp,cli:s.cli,touch:s.touchtype,rstP:s.rstP,'
            'rstR:s.rstR,acc:s.acctype}})(require("Storage").readJSON("ew.json",1))')
        result["active_hardware"] = await console.read(
            '({bpp:ew.def.bpp,cli:ew.def.cli,touch:ew.def.touchtype,rstP:ew.def.rstP,'
            'rstR:ew.def.rstR,acc:ew.def.acctype})')
        # A later independent CRC sweep detects changes since each export read.
        checked = 0
        for start in range(0, len(manifest["files"]), 8):
            entries = manifest["files"][start:start + 8]
            names = json.dumps([entry["name"] for entry in entries], ensure_ascii=True)
            values = await console.read(names + '.map(function(n){var s=require("Storage").read(n);return s===undefined?null:[s.length,E.CRC32(s)]})')
            for entry, value in zip(entries, values, strict=True):
                if value is None or value[0] != entry["bytes"] or f'{value[1] & 0xffffffff:08x}' != entry["crc32"]:
                    raise RuntimeError("Watch file changed since backup; new snapshot needed")
                checked += 1
        result["backup_reverification"] = {"files": checked, "local_sha256_all_match": True,
                                           "remote_length_crc32_all_match": True}
        await client.stop_notify(TX)
    save_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    asyncio.run(main(parser.parse_args()))
