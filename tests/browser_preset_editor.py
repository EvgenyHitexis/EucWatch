"""Reusable real Canvas actions + raw frame responses; no physical wheel operation."""
import asyncio
import base64
import hashlib
import json
from pathlib import Path

from eucwatch import Application, ManualClock
from test_control import settings_frame


async def exercise(cdp, session, app, output):
    output.mkdir(parents=True, exist_ok=True)
    actions = []
    frames = []
    timeline = []
    async def tap(x, y):
        row = {"input": "tap", "x": x, "y": y}
        actions.append(row)
        timeline.append(row)
        await cdp.pointer('#watch', (x, y), (x, y), session)
        await asyncio.sleep(.03)
    async def wait(text):
        await cdp.wait(f"document.querySelector('canvas').getAttribute('aria-label').includes({json.dumps(text)})", session)
    def receive(sensitivity, assist, dip):
        app.clock.advance(.1)
        frame = settings_frame(sensitivity, assist, dip)
        row = {"input": "notification", "advance_s": .1, "session": app.session, "at_s": app.elapsed(), "raw_hex": frame.hex()}
        frames.append(row)
        timeline.append(row)
        app.receive(app.session, frame)
    async def swipe(start, end):
        timeline.append({"input": "swipe", "start": start, "end": end})
        await cdp.pointer('#watch', start, end, session)
    async def snapshot(name):
        data = await cdp.evaluate("document.querySelector('canvas').toDataURL('image/png').split(',')[1]", session)
        (output / f'{name}.png').write_bytes(base64.b64decode(data))
    async def name_input(name):
        await tap(120, 80); await wait('name keypad')
        await tap(148, 196)  # Clear existing name.
        alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        page = 0
        for letter in name:
            target = alphabet.index(letter) // 12
            while page != target:
                await tap(220, 20); page = (page + 1) % 3
            index = alphabet.index(letter) % 12
            await tap(49 + index % 3 * 70, 73 + index // 3 * 31)
        await wait(f'Input {name}')
        await tap(176, 226)
        await wait(f'Name: {name}')
    async def numeric(value):
        await tap(120, 80); await wait('keypad')
        keys = '123456789'
        for digit in str(value):
            index = 10 if digit == '0' else keys.index(digit)
            await tap(49 + index % 3 * 70, 73 + index // 3 * 31)
        await tap(176, 226)
        await cdp.wait("document.querySelector('#preset-outcome').textContent.includes('Applying')", session)

    await cdp.wait("!document.querySelector('#start').disabled", session)
    await cdp.evaluate("document.querySelector('#controlled').checked=true; document.querySelector('#start').click()", session)
    await cdp.wait("document.querySelector('#mode').textContent==='SIMULATOR'", session)
    app.action("simulator_configure", traffic="paused")
    timeline.append({"input": "simulator_configure", "traffic": "paused"})
    observed = []
    for slot in range(1, 5):
        await swipe((120, 10), (120, 110))
        await wait('Settings.')
        await tap(120, 196); await wait('Settings Presets.')
        before = app.view()['config']
        count = len(app.view()['command_events'])
        await tap(80, 55 + (slot - 1) * 44)
        await wait('Waiting for fresh wheel settings')
        assert app.view()['preset_draft'] is None
        assert len(app.view()['command_events']) == count
        actual = [40 + slot, 50 + slot, 60 + slot]
        receive(*actual)
        await wait(f'Preset editor slot {slot}. Name')
        assert app.view()['preset_draft']['pedal_sensitivity'] == actual[0]
        name = 'RAIN' if slot == 2 else f'ROAD{slot}'
        await name_input(name)
        assert len(app.view()['command_events']) == count
        await tap(220, 20); await wait('Pedal sensitivity:')
        # Unfinished numeric input and Cancel are local.
        await tap(120, 80); await wait('keypad'); await tap(49, 73)
        await tap(64, 226); await wait('Pedal sensitivity:')
        assert len(app.view()['command_events']) == count
        for index, value in ((0, 30), (1, 20), (2, 11)):
            if index:
                await tap(220, 20)
                await wait('Dynamic assist:' if index == 1 else 'Pedal dip compensation:')
            if index == 2:
                await tap(120, 126)
                await wait('Pedal dip compensation: ' + str(actual[2]))
            await numeric(value)
            assert app.view()['preset_attempt']['kind'] == 'editor'
            actual[index] = value
            receive(*actual)
            assert app.view()['preset_attempt']['pending']
            receive(*actual)
            await wait('confirmed')
            assert app.view()['preset_attempt']['status'] == 'Confirmed'
            assert app.view()['confirmed_preset'] is None
            assert app.view()['config']['presets'][slot-1][['pedal_sensitivity','dynamic_assist','pedal_dip_compensation'][index]] == value
            await snapshot(f'slot-{slot}-field-{index+1}')
        await tap(120, 126)  # Omission never changes wheel dip.
        await wait('Pedal dip compensation: omitted')
        assert app.view()['actual_settings']['pedal_dip_compensation'] == 11
        saved = app.view()['config']
        await tap(207, 221); await wait(f'Clear slot {slot}?')
        await tap(64, 190); await wait(f'Preset editor slot {slot}.')
        assert app.view()['config'] == saved
        assert [s for s in saved['presets'] if s['id'] != slot] == [s for s in before['presets'] if s['id'] != slot]
        await tap(44, 221); await wait('Settings Presets.')
        await tap(200, 55 + (slot-1)*44); await wait(f'Clear slot {slot}?')
        await tap(64, 190); await wait('Settings Presets.')
        assert app.view()['config'] == saved
        await tap(80, 55 + (slot-1)*44); await wait('Waiting for fresh wheel settings')
        receive(*actual); await wait(f'Preset editor slot {slot}. Name')
        await tap(207, 221); await wait(f'Clear slot {slot}?')
        await tap(176, 190); await wait('unconfigured')
        assert not app.view()['config']['presets'][slot-1]['configured']
        await tap(80, 55 + (slot-1)*44); await wait('Waiting for fresh wheel settings')
        receive(*actual); await wait(f'Preset editor slot {slot}. Name')
        await tap(131, 221); await wait('Name:')
        assert app.view()['config']['presets'][slot-1]['configured']
        await tap(44, 221); await wait('Settings Presets.')
        await swipe((20, 120), (215, 120)); await wait('Settings.')
        await swipe((20, 120), (215, 120))
        await cdp.wait("document.querySelector('canvas').dataset.screen==='dashboard'", session)
        observed.append({"slot": slot, "external_seed": [40+slot, 50+slot, 60+slot], "saved": saved['presets'][slot-1],
                         "expected": "fresh seed; local name; three serialized writes confirmed by two new frames; omission; clear cancel/commit; recreate; other slots unchanged",
                         "observed": "passed"})
    # Rendering of bounded unavailable readback and failed local persistence.
    await swipe((120, 10), (120, 110)); await wait('Settings.')
    await tap(120, 196); await wait('Settings Presets.')
    await tap(80, 55); await wait('Waiting for fresh wheel settings')
    app.clock.advance(5)
    timeline.append({"input": "advance", "seconds": 5})
    await wait('Settings unavailable')
    await snapshot('unavailable-readback')
    await tap(120, 218); await wait('Settings Presets.')
    await tap(80, 55); await wait('Waiting for fresh wheel settings')
    receive(30, 20, 11); await wait('Preset editor slot 1. Name')
    from eucwatch.persistence import MemoryStore
    class FailedSave(MemoryStore):
        def save(self, config):
            raise OSError("Controlled disk full")
    saved_store = app.store
    saved_config = app.view()['config']
    app.store = FailedSave()
    await tap(220, 20); await wait('Pedal sensitivity:')
    await numeric(31)
    receive(31, 20, 11); receive(31, 20, 11)
    await wait('Controlled disk full')
    await cdp.wait("document.querySelector('#preset-outcome').textContent.includes('Confirmed')", session)
    await snapshot('save-failure-after-wheel-change')
    assert app.view()['config'] == saved_config
    assert app.view()['actual_settings']['pedal_sensitivity'] == 31
    assert app.view()['preset_attempt']['status'] == 'Confirmed'
    app.store = saved_store
    commands = len(app.view()['command_events'])
    await tap(131, 221)  # Retry only local storage, never the wheel command.
    await cdp.wait("!document.querySelector('canvas').getAttribute('aria-label').includes('Controlled disk full')", session)
    assert len(app.view()['command_events']) == commands
    await tap(44, 221); await wait('Settings Presets.')
    await swipe((20, 120), (215, 120)); await wait('Settings.')
    await swipe((20, 120), (215, 120))
    await cdp.wait("document.querySelector('canvas').dataset.screen==='dashboard'", session)
    assert Application(clock=ManualClock(), store=app.store).view()['config'] == app.view()['config']
    count = len(app.view()['command_events'])
    await cdp.call('Page.reload', session=session)
    await cdp.wait("document.querySelector('#backend-status')?.textContent==='Application ready'", session)
    assert len(app.view()['command_events']) == count
    result = {"issue": 41, "provenance": "built 240x240 Canvas / real Chrome inputs / aiohttp / controlled clock / raw CRC-valid simulated responses",
              "observed": observed, "actions": actions, "frames": frames, "timeline": timeline,
              "unavailable_and_save_failure": "passed; bounded unavailable view, failed save after confirmed wheel change, local retry emits no command", "restart_and_reload": "passed; saved slots retained, no command replay",
              "live_wheel_evidence": "pending", "owner_review": "pending", "watch_deployment": "not performed",
              "source_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in map(Path, ['frontend/src/main.ts', 'frontend/src/preset-editor.ts', 'laptop/eucwatch/application.py', 'laptop/eucwatch/presets.py', 'laptop/eucwatch/control.py'])}}
    (output / 'preset-editor-browser.json').write_text(json.dumps(result, indent=2) + '\n')
    app.action("simulator_configure", traffic="normal")
    return result
