"""Watch-sized alert acceptance through pointer input and the actual backend."""
import json
import asyncio
from pathlib import Path

from eucwatch import Application
from support import main, served_laptop, write_evidence


async def exercise(page, app, clock):
    inputs = []

    label = page.label

    async def pointer(start, end):
        inputs.append({'start': start, 'end': end})
        await page.pointer(start, end)

    async def tap(x, y):
        await pointer((x, y), (x, y))

    async def snapshot(name):
        output = Path('docs/acceptance/evidence/touch-layout')
        output.mkdir(parents=True, exist_ok=True)
        await page.snapshot(output / (name + '.png'))

    initial = app.view()['config']
    await pointer((120, 10), (120, 110))
    await label('Settings.')
    await snapshot('settings')
    await tap(120, 140)
    await label('Alert editor 1 of 4')
    await snapshot('alerts')
    await tap(120, 88)
    await label('; enabled;')
    await tap(176, 217)
    await label('Error:')
    await snapshot('alerts-validation')
    assert app.view()['config'] == initial
    assert app.view()['alerts_draft']['pwm'] == {'enabled': True, 'threshold': None}

    # All value entry is on the watch; the desktop editor is not used.
    await tap(120, 135)
    await label('Watch threshold keypad.')
    await snapshot('alert-keypad')
    await tap(49, 140)  # 7
    await label('threshold 7 %')
    await tap(119, 173)  # 0
    await label('threshold 70 %')
    await tap(176, 217)  # Set value updates the alert draft only.
    await label('Alert editor 1 of 4')
    await label('threshold 70 %')
    assert app.view()['alerts_draft']['pwm'] == {'enabled': True, 'threshold': 70}
    assert app.view()['config'] == initial
    await tap(120, 217)  # The visible gap must not save or discard the draft.
    await asyncio.sleep(.15)
    await label('Alert editor 1 of 4')
    assert app.view()['config'] == initial
    assert app.view()['alerts_draft']['pwm'] == {'enabled': True, 'threshold': 70}
    await tap(220, 200)  # Upper edge of the enlarged Save button.
    await label('Settings.')
    expected = json.loads(json.dumps(initial))
    expected['revision'] += 1
    expected['alerts']['pwm'] = {'enabled': True, 'threshold': 70}
    assert app.view()['config'] == expected
    assert Application(store=app.store).view()['config'] == expected

    await tap(120, 140)
    await label('Alert editor 1 of 4')
    await tap(120, 135)
    await label('Watch threshold keypad.')
    await tap(49, 140)  # Unsaved 707 is discarded by keypad Cancel.
    await label('threshold 707 %')
    await tap(64, 217)
    await label('Alert editor 1 of 4')
    assert app.view()['alerts_draft']['pwm']['threshold'] == 70

    patterns = []
    for index, (name, durations, times) in enumerate([
        ('pwm', [.15, .15, .15], [0, .15, .3, .45, .6, .75]),
        ('speed', [.15, .15], [0, .15, .3, .45]),
        ('battery', [.5], [0, .5]),
        ('lost', [.15], [0, .15]),
    ]):
        await label(f'Alert editor {index + 1} of 4')
        before = len(app.view()['vibration']['events'])
        await tap(120, 178)
        await page.wait("document.querySelector('#vibration-status').textContent.includes(' test')")
        clock.advance(1)
        inputs.append({'advance_seconds': 1})
        await page.wait("document.querySelector('#vibration-status').textContent.includes('idle')")
        events = app.view()['vibration']['events'][before:]
        assert all(row['alert'] == name and row['test'] for row in events)
        assert [row['duration_s'] for row in events if row['phase'] == 'start'] == durations
        assert [row['phase'] for row in events] == ['start', 'stop'] * len(durations)
        offsets = [row['at_s'] - events[0]['at_s'] for row in events]
        assert all(abs(actual - wanted) < 1e-9 for actual, wanted in zip(offsets, times, strict=True))
        assert app.view()['config'] == expected
        patterns.append({'alert': name, 'expected_durations_s': durations,
                         'expected_offsets_s': times, 'observed': events})
        await tap(220, 20)
    await label('Alert editor 1 of 4')
    await tap(120, 88)
    await label('; disabled;')
    await tap(64, 217)  # Whole alert editor Cancel preserves the saved PWM setting.
    await label('Settings.')
    assert app.view()['config'] == expected
    assert app.view()['alerts_draft'] is None
    assert app.view()['command_events'] == []
    await pointer((120, 215), (120, 20))
    await page.screen('dashboard')
    return {'issue': 31, 'provenance': 'actual Canvas pointers / aiohttp / FileStore / controlled time; simulated vibration',
            'expected': 'watch-only validation, keypad entry/Cancel, whole Save/Cancel, restart persistence, four Test patterns, zero wheel commands',
            'observed': 'passed', 'inputs': inputs, 'patterns': patterns, 'saved': expected,
            'wheel_commands': [], 'physical_vibration': 'pending #38'}


async def run():
    async with served_laptop() as laptop:
        result = await exercise(laptop.page, laptop.app, laptop.clock)
    write_evidence(laptop.output / 'alerts.json', result)
    print('alerts: passed')


if __name__ == '__main__':
    main(run)
