"""Python protocol interoperates with original watch code and native Storage seam."""
import unittest
from copy import deepcopy

from eucwatch.async_transfer import AsyncConfigurationProtocol, AsyncConfigurationTransfer
from eucwatch.configuration import default_configuration
from eucwatch.persistence import MemoryStore
from watch_wire import WatchWire


class WatchWireTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.wire=await WatchWire().start()
        self.protocol=AsyncConfigurationProtocol(self.wire.exchange)

    async def asyncTearDown(self):
        await self.wire.close()

    async def test_actual_utf8_content_staging_restart_and_partial_activation(self):
        original=await self.protocol.read()
        candidate=deepcopy(original)
        candidate['revision']=1
        candidate['presets'][0].update(name='é'*24,configured=True,pedal_sensitivity=31,dynamic_assist=26)
        await self.protocol.upload(candidate,original)
        self.assertEqual(await self.protocol.read(),candidate)
        await self.wire.call(restart=True)
        self.assertEqual(await self.protocol.read(),candidate)
        damaged=deepcopy(candidate);damaged['revision']=2
        await self.wire.call(fail='sw-config.json',partial=True)
        with self.assertRaisesRegex(ValueError,'write|readback|save|Storage'):
            await self.protocol.upload(damaged,candidate)
        await self.wire.call(restart=True)
        self.assertEqual(await self.protocol.read(),candidate)

    async def test_actual_workflow_shared_base_and_explicit_conflict(self):
        config=default_configuration();config['alerts']['pwm']={'enabled':True,'threshold':70}
        laptop=MemoryStore();laptop.save(config)
        shared=MemoryStore();journal=MemoryStore()
        transfer=AsyncConfigurationTransfer(laptop,shared,self.protocol,endpoint_label='Actual JS watch / offline wire',journal_store=journal)
        transfer.begin(config,'idle',False)
        await transfer.areview(config)
        for conflict in transfer.preview['conflicts']:
            transfer.choose(conflict['path'],'laptop')
        committed=await transfer.asend(config)
        self.assertEqual(laptop.load(),committed)
        self.assertEqual(shared.load(),committed)
        self.assertEqual(await self.protocol.read(),committed)
        self.assertFalse(transfer.active)
        await self.wire.call(restart=True)
        watch=deepcopy(committed);watch['alerts']['pwm']['threshold']=75
        await self.wire.call(configuration=watch)
        local=deepcopy(committed);local['alerts']['pwm']['threshold']=80;laptop.save(local)
        transfer=AsyncConfigurationTransfer(laptop,shared,self.protocol,endpoint_label='Actual JS watch / offline wire',journal_store=journal)
        transfer.begin(local,'idle',False);await transfer.areview(local)
        self.assertIsNone(transfer.preview['candidate'])
        transfer.choose('alerts.pwm.threshold','watch')
        saved=await transfer.asend(local)
        self.assertEqual(saved['alerts']['pwm']['threshold'],75)
        self.assertEqual(laptop.load(),await self.protocol.read())

    async def test_transfer_uses_watch_bytes_for_expected_digest(self):
        original = await self.protocol.read()
        candidate = deepcopy(original)
        candidate['revision'] = 1
        candidate['alerts']['speed'] = {'enabled': True, 'threshold': 1e-7}
        await self.protocol.upload(candidate, original)
        expected = await self.protocol.read()
        self.assertEqual(expected, candidate)
        replacement = deepcopy(expected)
        replacement['revision'] = 2
        replacement['alerts']['lost']['enabled'] = False
        await self.protocol.upload(replacement, expected)
        self.assertEqual(await self.protocol.read(), replacement)
