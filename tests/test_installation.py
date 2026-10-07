"""Installation intents and observable exact-byte Storage effects; no radio."""

import json
import hashlib
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path

from eucwatch.installation import Bundle, Installer, Preconditions, PrivateBackup, build_bundle


class Device:
    def __init__(self):
        self.files = {".bootrst": b"working historical startup", "old-app": b"historical app"}
        self.writes = []
        self.capacity = 1_000_000
        self.fail_at = None
        self.corrupt = None
        self.lose_ack = False

    def runtime(self):
        return {"BOARD": "P22", "VERSION": "2v14"}

    def free_bytes(self):
        return self.capacity

    def list_files(self):
        return list(self.files)

    def read(self, name):
        return self.files.get(name)

    def write(self, name, content):
        self.writes.append(name)
        if self.fail_at == name:
            raise OSError("Controlled interrupted transfer")
        self.files[name] = content + b"bad" if self.corrupt == name else bytes(content)
        if self.lose_ack and name == "sw-active.json":
            raise OSError("Controlled lost acknowledgement")

    def erase(self, name):
        self.writes.append("erase:" + name)
        self.files.pop(name, None)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name)
        (self.source / "main.js").write_text("exports.start=function(){return require('sw-app');};")
        (self.source / "app.js").write_text("exports.create=function(){return 1;};")
        (self.source / "boot.js").write_text("/* independent startup */")
        self.bundle = build_bundle(self.source, "abc123")
        self.device = Device()
        self.backup = PrivateBackup.from_bytes(self.device.files)
        self.permissions = Preconditions(laptop_accepted=True, deployment_authorized=True, complete_application=True)

    def test_complete_version_staged_verified_before_first_startup_and_pointer_last(self):
        installer = Installer(self.device)
        plan = installer.plan(self.bundle, self.backup, self.permissions, first_install=True)
        self.assertEqual(self.device.writes, [])
        self.assertGreater(plan["required_bytes"], 0)
        installer.stage(self.bundle, self.backup, self.permissions, first_install=True)
        self.assertEqual(self.device.read(".bootrst"), b"working historical startup")
        self.assertIsNone(self.device.read("sw-active.json"))
        outcome = installer.activate(self.bundle, self.backup, self.permissions, first_install=True)
        self.assertEqual(outcome["status"], "verified")
        self.assertEqual(self.device.writes[-2:], [".bootrst", "sw-active.json"])
        self.assertEqual(json.loads(self.device.read("sw-active.json"))["main"], "sw-abc123-main")
        self.assertIn(b"require('sw-abc123-app')", self.device.read("sw-abc123-main"))
        self.assertEqual(self.device.read("old-app"), b"historical app")

    def test_capacity_incomplete_corrupt_and_interrupted_staging_preserve_working_startup(self):
        installer = Installer(self.device)
        self.device.capacity = 1
        with self.assertRaisesRegex(ValueError, "Insufficient"):
            installer.stage(self.bundle, self.backup, self.permissions, first_install=True)
        self.assertEqual(self.device.writes, [])
        self.device.capacity = 1_000_000
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            installer.activate(self.bundle, self.backup, self.permissions, first_install=True)
        self.device.corrupt = "sw-abc123-main"
        with self.assertRaisesRegex(ValueError, "checksum"):
            installer.stage(self.bundle, self.backup, self.permissions, first_install=True)
        self.device.corrupt = None
        self.device.files.pop("sw-abc123-main")
        self.device.fail_at = "sw-abc123-main"
        with self.assertRaises(OSError):
            installer.stage(self.bundle, self.backup, self.permissions, first_install=True)
        self.assertIsNone(self.device.read("sw-active.json"))
        self.assertEqual(self.device.read(".bootrst"), b"working historical startup")

    def test_updates_preserve_verified_independent_startup_and_unknown_ack_is_read_back(self):
        installer = Installer(self.device)
        installer.stage(self.bundle, self.backup, self.permissions, first_install=True)
        self.device.lose_ack = True
        outcome = installer.activate(self.bundle, self.backup, self.permissions, first_install=True)
        self.assertEqual(outcome["status"], "unknown")
        self.assertEqual(installer.reconcile(self.bundle)["status"], "verified")
        self.device.lose_ack = False
        newer = build_bundle(self.source, "def456")
        writes_before = len(self.device.writes)
        with self.assertRaisesRegex(ValueError, "recovery"):
            installer.stage(newer, self.backup, self.permissions)
        self.assertEqual(len(self.device.writes), writes_before)
        permissions = Preconditions(laptop_accepted=True, deployment_authorized=True, complete_application=True,
                                    recovery_sha256=self.bundle.manifest()["files"][1]["sha256"])
        installer.stage(newer, self.backup, permissions)
        installer.activate(newer, self.backup, permissions)
        self.assertNotIn(".bootrst", self.device.writes[writes_before:])
        self.assertEqual(json.loads(self.device.read("sw-active.json"))["version"], "def456")

    def test_private_export_backup_validates_hashes_inventory_flags_and_never_changes_bytes(self):
        private = self.source / "private"
        private.mkdir()
        (private / "files").mkdir()
        content = b"\xff\x00\x80tokenised\xfe"
        (private / "files/0000.bin").write_bytes(content)
        manifest = {"schema": 1, "complete": True, "inventory_stable": True,
                    "firmware": {"BOARD": "P22", "VERSION": "2v14"}, "storage_files": [],
                    "initial_inventory": {"all": [".bootrst"], "normal": [".bootrst"], "stream": []},
                    "final_inventory": {"all": [".bootrst"], "normal": [".bootrst"], "stream": []},
                    "files": [{"name": ".bootrst", "kind": "normal", "path": "files/0000.bin", "bytes": len(content),
                               "sha256": hashlib.sha256(content).hexdigest(), "crc32": f"{zlib.crc32(content):08x}"}]}
        (private / "manifest.json").write_text(json.dumps(manifest))
        backup = PrivateBackup.load(private)
        self.assertEqual(dict(backup.files)[".bootrst"], content)
        manifest["storage_files"] = [{"name": "ride-log"}]
        (private / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "StorageFile"):
            PrivateBackup.load(private)
        manifest["storage_files"] = []
        (private / "manifest.json").write_text(json.dumps(manifest))
        (private / "files/0000.bin").write_bytes(content + b"wrong")
        with self.assertRaisesRegex(ValueError, "checksum"):
            PrivateBackup.load(private)

    def test_historical_restoration_is_exact_binary_with_startup_last_and_requires_console(self):
        historical = PrivateBackup.from_bytes({".bootrst": b"\xff\x80startup\x00", "old-app": b"\x00\xfeapp\xff"})
        installer = Installer(self.device)
        with self.assertRaisesRegex(ValueError, "console"):
            installer.restore_historical(historical, self.permissions)
        self.assertEqual(self.device.writes, [])
        permissions = Preconditions(laptop_accepted=True, deployment_authorized=True, complete_application=True,
                                    console_recovery_verified=True)
        result = installer.restore_historical(historical, permissions)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.device.writes[-1], ".bootrst")
        self.assertEqual(self.device.read(".bootrst"), b"\xff\x80startup\x00")
        self.assertEqual(self.device.read("old-app"), b"\x00\xfeapp\xff")

    def test_legacy_removal_needs_verified_custom_controls_and_matching_reviewed_hashes(self):
        installer = Installer(self.device)
        installer.stage(self.bundle, self.backup, self.permissions, first_install=True)
        installer.activate(self.bundle, self.backup, self.permissions, first_install=True)
        reviewed = {"old-app": hashlib.sha256(b"historical app").hexdigest()}
        with self.assertRaisesRegex(ValueError, "controls"):
            installer.remove_legacy(self.bundle, reviewed, self.permissions)
        self.assertEqual(self.device.read("old-app"), b"historical app")
        permissions = Preconditions(laptop_accepted=True, deployment_authorized=True, complete_application=True,
                                    custom_startup_controls_verified=True)
        with self.assertRaisesRegex(ValueError, "changed"):
            installer.remove_legacy(self.bundle, {"old-app": "wrong"}, permissions)
        with self.assertRaisesRegex(ValueError, "protected"):
            installer.remove_legacy(self.bundle, {".bootrst": "wrong"}, permissions)
        installer.remove_legacy(self.bundle, reviewed, permissions)
        self.assertIsNone(self.device.read("old-app"))
        self.assertEqual(self.device.writes[-1], "erase:old-app")

    def test_local_bundle_can_restore_known_good_version_and_rejects_changed_archive(self):
        directory = self.source / "bundle"
        self.bundle.write(directory)
        retained = Bundle.load(directory)
        installer = Installer(self.device)
        installer.stage(retained, self.backup, self.permissions, first_install=True)
        installer.activate(retained, self.backup, self.permissions, first_install=True)
        self.assertEqual(installer.reconcile(retained)["status"], "verified")
        (directory / "sw-abc123-main.bin").write_bytes(b"incomplete")
        with self.assertRaisesRegex(ValueError, "checksum"):
            Bundle.load(directory)

    def test_actual_recovery_startup_bypasses_failed_and_stalled_application(self):
        boot = Path(__file__).resolve().parents[1] / "watch/boot.js"
        script = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync(process.argv[1],'utf8');
function scenario(stall){
 const files={'sw-active.json':JSON.stringify({main:'sw-test-main'})};let imports=0,uart=false;
 const storage={read:k=>files[k],readJSON:k=>files[k]?JSON.parse(files[k]):undefined,write:(k,v)=>files[k]=v,erase:k=>delete files[k]};
 function context(){return{require:name=>{if(name==='Storage')return storage;imports++;return{start:()=>{if(stall)while(true){};throw Error('Controlled application failure');}};},
 D15:{write:()=>{}},BTN1:{read:()=>false},E:{enableWatchdog:(seconds,automatic)=>assert.deepEqual([seconds,automatic],[30,false]),kickWatchdog:()=>{}},
 setInterval:()=>1,NRF:{setServices:(services,options)=>{uart=options.uart;},setAdvertising:()=>{}},global:{},print:()=>{},reset:()=>{},process:{env:{VERSION:'2v14'}}};}
 const first=context();if(stall)assert.throws(()=>vm.runInNewContext(source,first,{timeout:30}),/timed out/);else vm.runInNewContext(source,first);
 assert.equal(imports,1);assert.ok(files['sw-starting']);
 const next=context();vm.runInNewContext(source,next,{timeout:100});assert.equal(imports,1);assert.equal(uart,true);assert.ok(next.global.ShermanRecovery);
}
scenario(false);scenario(true);console.log('failed and stalled startup recover independently');
"""
        result = subprocess.run(["node", "-e", script, str(boot)], text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("recover independently", result.stdout)

    def test_reusing_a_version_with_different_bytes_cannot_modify_an_active_application(self):
        installer = Installer(self.device)
        installer.stage(self.bundle, self.backup, self.permissions, first_install=True)
        installer.activate(self.bundle, self.backup, self.permissions, first_install=True)
        (self.source / "app.js").write_text("exports.create=function(){return 2;};")
        changed = build_bundle(self.source, "abc123")
        before = list(self.device.writes)
        with self.assertRaisesRegex(ValueError, "version"):
            installer.stage(changed, self.backup, self.permissions, first_install=True)
        self.assertEqual(self.device.writes, before)
        self.assertEqual(installer.reconcile(self.bundle)["status"], "verified")



if __name__ == "__main__":
    unittest.main()
