"""Agent-driven #31 walkthrough (touch-layout visual set, R4-R6) against the launched
review session on 127.0.0.1:8766, through headless Chrome and the repo's CDP driver.

phase A: visual set, R4, R5, R6 up to the browser reload.  phase B: after relaunch.
Usage: PYTHONPATH=laptop:tests python walk.py A|B <output-dir>
"""
import asyncio
import json
import sys
from pathlib import Path

from aiohttp import ClientSession
from support import chrome

URL = 'http://127.0.0.1:8766/'
FIXTURE = Path('experiments/laptop-feasibility/evidence/fixture-recording.jsonl').resolve()
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
log = []


async def state():
    async with ClientSession() as client, client.get(URL + 'api/state') as response:
        return await response.json()


def note(row, **data):
    entry = {'row': row, **data}
    log.append(entry)
    print(json.dumps(entry, default=str)[:400])


class Walk:
    def __init__(self, page):
        self.page, self.n = page, 0

    async def snap(self, name):
        self.n += 1
        path = OUT / f'{self.n:02d}-{name}.png'
        await self.page.snapshot(path)
        return path.name

    async def swipe(self, direction):
        start, end = {'down': ((120, 10), (120, 110)), 'up': ((120, 215), (120, 20)),
                      'left': ((215, 120), (20, 120)), 'right': ((20, 120), (215, 120))}[direction]
        await self.awake()
        await self.page.pointer(start, end)
        await asyncio.sleep(.15)

    async def tap(self, x, y):
        await self.awake()
        await self.page.tap(x, y)
        await asyncio.sleep(.15)

    async def awake(self):
        if not (await state())['awake']:
            await self.page.press_button()
            await asyncio.sleep(.3)
            assert (await state())['awake'], 'button did not wake the screen'

    async def advance(self, seconds):
        elapsed = float(await self.page.evaluate("document.querySelector('#watch').dataset.elapsed") or 0)
        await self.page.evaluate(f"document.querySelector('#advance-seconds').value={json.dumps(str(seconds))}")
        await self.page.wait("!document.querySelector('#advance').disabled")
        await self.page.evaluate("document.querySelector('#advance').click()")
        await self.page.wait(f"Number(document.querySelector('#watch').dataset.elapsed)>={elapsed + seconds - 1e-5}")

    async def readings(self, speed=25, voltage=148.05, pwm=45):
        await self.page.evaluate(f"""document.querySelector('#speed').value='{speed}';
            document.querySelector('#voltage').value='{voltage}';
            document.querySelector('#pwm').value='{pwm}';
            document.querySelector('#traffic').value='normal';
            document.querySelector('#scenario').requestSubmit();""")
        await self.page.wait("!document.querySelector('[data-action=simulator_configure]').disabled")
        await asyncio.sleep(.2)

    async def describe(self):
        return await self.page.description()


async def visual(w):
    p = w.page
    await w.awake()
    await p.screen('dashboard')
    shots = [await w.snap('dashboard')]
    await w.swipe('down'); await p.label('Settings.'); shots.append(await w.snap('settings'))
    await w.tap(120, 196); await p.screen('preset_slots'); shots.append(await w.snap('preset-slots'))
    await w.tap(80, 55); await p.screen('preset_editor'); shots.append(await w.snap('preset-name-field'))
    await w.tap(120, 80); await asyncio.sleep(.2); shots.append(await w.snap('name-keypad'))
    await w.swipe('up')  # closes the entry
    await w.swipe('left'); await asyncio.sleep(.2); shots.append(await w.snap('preset-sensitivity-field'))
    await w.tap(120, 80); await asyncio.sleep(.2); shots.append(await w.snap('numeric-keypad'))
    await w.swipe('up')  # entry
    await w.swipe('up')  # editor, back to slots
    await p.screen('preset_slots')
    await w.swipe('up'); await p.label('Settings.')
    await w.tap(120, 140); await p.label('Alert editor 1 of 4'); shots.append(await w.snap('alerts'))
    await w.tap(120, 135); await p.label('Watch threshold keypad.'); shots.append(await w.snap('alert-keypad'))
    await w.tap(64, 217); await p.label('Alert editor 1 of 4')
    await w.tap(64, 217); await p.label('Settings.')
    await w.swipe('up'); await p.screen('dashboard')
    await w.swipe('left'); await p.screen('presets'); shots.append(await w.snap('riding-presets'))
    await w.swipe('right'); await p.screen('dashboard')
    s = await state()
    note('visual', snapshots=shots, drafts=[s['alerts_draft'], s['preset_editor']], command_events=len(s['command_events']))


async def r4(w):
    p = w.page
    # The alert tests need controlled time: start the controlled simulator first.
    await p.evaluate("document.querySelector('#controlled').checked=true;document.querySelector('[data-action=simulator_start]').click()")
    await p.wait("document.querySelector('#watch').getAttribute('aria-label').includes('Connected')")
    await w.readings()
    initial = (await state())['config']
    await w.awake(); await w.swipe('down'); await p.label('Settings.')
    await w.tap(120, 140); await p.label('Alert editor 1 of 4')
    await w.tap(120, 88); await p.label('; enabled;')
    await w.tap(176, 217); await p.label('Error:')
    err = await w.describe(); shot = await w.snap('r4-missing-threshold')
    s = await state()
    note('R4.1 enable PWM without threshold, Save', observed=err, snapshot=shot,
         saved_unchanged=s['config'] == initial, passed='Error:' in err and s['config'] == initial)
    await w.tap(120, 135); await p.label('Watch threshold keypad.')
    await w.tap(49, 140); await p.label('threshold 7 %')
    await w.tap(119, 173); await p.label('threshold 70 %')
    await w.tap(176, 217); await p.label('Alert editor 1 of 4')
    await w.tap(176, 217); await p.label('Settings.')
    s = await state(); shot = await w.snap('r4-saved')
    note('R4.2 enter 70, Set value, Save', saved=s['config']['alerts']['pwm'], snapshot=shot,
         passed=s['config']['alerts']['pwm'] == {'enabled': True, 'threshold': 70})
    await w.tap(120, 140); await p.label('Alert editor 1 of 4')
    await w.tap(120, 88); await p.label('; disabled;')
    await w.tap(64, 217); await p.label('Settings.')
    s = await state()
    note('R4.3 toggle off, Cancel', saved=s['config']['alerts']['pwm'], draft=s['alerts_draft'],
         passed=s['config']['alerts']['pwm'] == {'enabled': True, 'threshold': 70} and s['alerts_draft'] is None)
    await w.tap(120, 140); await p.label('Alert editor 1 of 4')
    reopened = await w.describe()
    want = {'pwm': [.15] * 3, 'speed': [.15] * 2, 'battery': [.5], 'lost': [.15]}
    for index, name in enumerate(want):
        await p.label(f'Alert editor {index + 1} of 4')
        before = len((await state())['vibration']['events'])
        await w.tap(120, 178)
        await p.wait("document.querySelector('#vibration-status').textContent.includes(' test')")
        shot = await w.snap(f'r4-test-{name}')
        await w.advance(.9)  # guide says 1 s; a 1 s gap trips lost telemetry (fresh < 1.0 s)
        await p.wait("document.querySelector('#vibration-status').textContent.includes('idle')")
        events = (await state())['vibration']['events'][before:]
        starts = [e for e in events if e['phase'] == 'start']
        stops = [e for e in events if e['phase'] == 'stop']
        gaps = [round(b['at_s'] - a['at_s'], 6) for a, b in zip(stops, starts[1:])]
        durations = [round(e['duration_s'], 6) for e in starts]
        note(f'R4.4 Test vibration: {name}', durations_s=durations, gaps_s=gaps, snapshot=shot,
             all_test=all(e['test'] and e['alert'] == name for e in events),
             passed=durations == want[name] and all(g == .15 for g in gaps))
        await w.tap(220, 20)
    await p.label('Alert editor 1 of 4')
    await w.tap(64, 217); await p.label('Settings.')
    await w.swipe('up'); await p.screen('dashboard')
    s = await state()
    note('R4.5 Cancel to Settings, up to dashboard', reopened_shows=reopened[:160], screen=s['screen'],
         saved=s['config']['alerts']['pwm'], wheel_commands=len(s['command_events']),
         passed=s['screen'] == 'dashboard' and s['command_events'] == [])


async def pick_road(w):
    await w.awake()
    await w.swipe('left'); await w.page.screen('presets')
    await w.tap(62, 180)
    await w.page.screen('dashboard')


async def r5(w):
    p = w.page
    await w.readings()
    await pick_road(w)
    applying = await w.describe(); shot1 = await w.snap('r5-applying')
    await w.advance(.2); await w.advance(.2)
    await p.label('Road · Confirmed')
    shot2 = await w.snap('r5-confirmed'); s = await state()
    note('R5.1 tap Road, two 0.2 s advances', on_tap=applying[:120], attempt=s['preset_attempt'],
         snapshots=[shot1, shot2], passed='Applying' in applying and s['preset_attempt']['status'] == 'Confirmed')
    horns = lambda st: sum(r.get('kind') == 'horn' and r['event'] == 'submission' for r in st['command_events'])
    before = horns(await state())
    await w.awake()
    await p.press_button()
    await p.wait("document.querySelector('#watch-feedback').textContent.length>0")
    feedback = await p.evaluate("document.querySelector('#watch-feedback').textContent")
    box = await p.evaluate("(() => { const b=document.querySelector('#watch-button').getBoundingClientRect(); return {x:b.x+10,y:b.y+20}; })()")
    await p.call('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': box['x'], 'y': box['y'], 'button': 'left', 'buttons': 1, 'clickCount': 1})
    for _ in range(5):
        await w.advance(.2)
    await p.call('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': box['x'], 'y': box['y'], 'button': 'left', 'buttons': 0, 'clickCount': 1})
    await asyncio.sleep(.3)
    after = horns(await state())
    note('R5.2 side button while awake, then a 1 s hold', feedback=feedback, horn_requests_added=after - before,
         passed=after - before == 2 and 'orn' in feedback)
    await p.evaluate("document.querySelector('#control-readback').value='missing'; document.querySelector('#control-submission').value='normal'")
    await w.readings()
    await pick_road(w)
    steps = 0
    while (await state())['preset_attempt']['pending'] and steps < 70:
        await w.advance(.2); steps += 1
    s = await state(); shot = await w.snap('r5-not-confirmed')
    outcome = await p.evaluate("document.querySelector('#preset-outcome').textContent")
    note('R5.3 Missing readback, Road, 0.2 s advances', advances=steps, elapsed_s=round(steps * .2, 2),
         attempt=s['preset_attempt'], outcome=outcome, watch=(await w.describe())[:140], snapshot=shot,
         passed=s['preset_attempt']['status'] == 'Not confirmed' and 9.8 <= steps * .2 <= 10.6)
    await p.evaluate("document.querySelector('#control-readback').value='normal'")
    await w.readings()
    await pick_road(w)
    await w.advance(.2); await w.advance(.2)
    await p.label('Road · Confirmed')
    s = await state(); shot = await w.snap('r5-retry-confirmed')
    note('R5.4 Matching restored, explicit retry', attempt=s['preset_attempt'], snapshot=shot,
         passed=s['preset_attempt']['status'] == 'Confirmed')


async def r6(w):
    p = w.page
    await p.click('#stop')
    await p.wait("document.querySelector('#mode').textContent.includes('IDLE')")
    await p.choose_files('#replay-file', FIXTURE)
    await p.click('#replay-load')
    await p.wait("document.querySelector('#mode').textContent.includes('REPLAY')")
    for count in range(1, 14):
        await p.click('#replay-step')
        await p.wait(f"document.querySelector('#replay-progress').textContent.includes('{count} / 13')")
    await w.awake()
    final = await w.describe(); shot = await w.snap('r6-replay-finished'); s = await state()
    note('R6.1 replay 13 events', watch=final, progress=await p.evaluate("document.querySelector('#replay-progress').textContent"),
         snapshot=shot, passed=all(t in final for t in ('Speed 0', 'PWM 2', 'battery 97 percent', '4.09')))
    commands = len(s['command_events'])
    await w.swipe('left'); await asyncio.sleep(.3)
    screen = (await state())['screen']; shot = await w.snap('r6-replay-presets')
    if screen == 'presets':
        await w.tap(62, 180); await asyncio.sleep(.3)
    s = await state()
    note('R6.2 riding controls in replay', screen_after_swipe=screen, watch=(await w.describe())[:160], snapshot=shot,
         new_commands=len(s['command_events']) - commands, attempt=s['preset_attempt'],
         passed=len(s['command_events']) == commands)
    if s['screen'] != 'dashboard':
        await w.swipe('right'); await asyncio.sleep(.2)
    await w.swipe('down'); await p.label('Settings.')
    await w.tap(120, 196); await p.screen('preset_slots'); await w.tap(80, 55); await p.screen('preset_editor')
    editing = (await state())['preset_editor'] is not None; shot = await w.snap('r6-replay-local-editing')
    await w.swipe('up'); await w.swipe('up'); await w.swipe('up'); await asyncio.sleep(.3)
    note('R6.3 local editing in replay', editor_opened=editing, snapshot=shot, screen_after=(await state())['screen'], passed=editing)
    before = len((await state())['command_events'])
    await p.call('Page.reload')
    await asyncio.sleep(2); await p.wait("document.querySelector('#watch')?.dataset.screen!==undefined")
    await asyncio.sleep(1)
    s = await state()
    note('R6.4 browser reload', commands_before=before, commands_after=len(s['command_events']), mode=s['mode'],
         passed=len(s['command_events']) == before)


async def after_relaunch(w):
    s = await state(); shot = await w.snap('r6-after-relaunch')
    presets = [(x['name'], x['pedal_sensitivity'], x['dynamic_assist']) for x in s['config']['presets']]
    note('R6.5 stop/relaunch', mode=s['mode'], alerts=s['config']['alerts'], presets=presets,
         alerts_draft=s['alerts_draft'], preset_editor=s['preset_editor'], preset_attempt=s['preset_attempt'], confirmed_preset=s['confirmed_preset'],
         snapshot=shot,
         passed=s['mode'] == 'idle' and s['config']['alerts']['pwm'] == {'enabled': True, 'threshold': 70}
         and s['alerts_draft'] is None and s['preset_editor'] is None and not s['preset_attempt'] and not s['confirmed_preset'])


async def main():
    phase = sys.argv[1]
    async with chrome() as browser:
        page = await browser.open(URL)
        await page.wait("document.querySelector('#watch')?.dataset.screen!==undefined")
        await asyncio.sleep(1)
        w = Walk(page)
        if phase == 'B':
            w.n = 40
        try:
            for step in ([visual, r4, r5, r6] if phase == 'A' else [after_relaunch]):
                await step(w)
        except Exception as error:
            note('ERROR', step=step.__name__, error=repr(error), watch=(await page.description())[:200],
                 state_screen=(await state())['screen'])
            await w.snap('error')
        finally:
            (OUT / f'phase-{phase}.json').write_text(json.dumps(log, indent=1, default=str))


asyncio.run(main())
