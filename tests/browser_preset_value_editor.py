"""Confirmed value completion through built Canvas, HTTP and real FileStore."""
import asyncio
import base64
import json
from eucwatch import Application
from unittest.mock import patch
from browser_preset_editor import type_percentage


async def exercise(cdp, session, app, output):
    timeline = []
    renderings = []

    async def pointer(start, end):
        await cdp.pointer('#watch', start, end, session)
        await asyncio.sleep(.13)
        state = app.view()
        assert state['command_events'] == []
        timeline.append({'input': 'tap' if start == end else 'swipe', 'start': start, 'end': end,
                         'expected': {key: state[key] for key in
                                      ['screen', 'preset_page', 'preset_input', 'preset_draft', 'config']}})
        return state

    async def tap(x, y):
        return await pointer((x, y), (x, y))

    async def label(text):
        await cdp.wait(f"document.querySelector('#watch').getAttribute('aria-label').includes({json.dumps(text)})", session)

    async def snapshot(name):
        await asyncio.sleep(.15)
        data = await cdp.evaluate("document.querySelector('#watch').toDataURL().split(',')[1]", session)
        (output / (name + '.png')).write_bytes(base64.b64decode(data))
        renderings.append(name + '.png')

    async def number(text):
        await tap(120, 80)
        await type_percentage(tap, text)

    await cdp.wait("document.querySelector('#backend-status')?.textContent==='Application ready'", session)
    initial = app.view()['config']
    await pointer((120, 10), (120, 110))
    await tap(120, 196)
    await tap(80, 143)  # Road.
    await tap(120, 80)
    await tap(125, 196)
    for character in 'Commute':
        entry = app.view()['preset_input']
        if entry['lowercase'] != character.islower():
            await tap(30, 196)
        index = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.index(character.upper())
        while app.view()['preset_input']['letters'] != index // 12:
            await tap(205, 196)
        await tap(49 + index % 12 % 3 * 70, 73 + index % 12 // 3 * 31)
    await label('OK or Cancel')
    assert app.view()['preset_draft']['name'] == 'Road'
    await snapshot('name-entry')
    state = await tap(176, 226)
    assert state['screen'] == 'preset_editor' and state['preset_input'] is None
    assert state['preset_draft']['name'] == 'Commute' and state['config'] == initial
    await label('Whole-preset Save or Cancel')
    await tap(220, 20)
    for text, x, expected in [('40', 64, 30), ('40', 176, 40), ('42', 64, 40)]:
        await number(text)
        state = await tap(x, 226)
        assert state['preset_input'] is None
        assert state['preset_draft']['pedal_sensitivity'] == expected
        assert state['preset_draft']['name'] == 'Commute'
        assert state['config'] == initial
    await snapshot('accepted-values')
    state = await tap(176, 226)
    expected = json.loads(json.dumps(initial))
    expected['revision'] = 1
    expected['presets'][2].update(name='Commute', pedal_sensitivity=40)
    assert state['screen'] == 'preset_slots' and state['config'] == expected
    assert Application(store=app.store).view()['config'] == expected
    # Accept multiple fields, then discard the entire draft.
    await tap(80, 143)
    await tap(220, 20)
    await number('55')
    await tap(176, 226)
    await tap(220, 20)
    await number('66')
    await tap(176, 226)
    await tap(64, 226)
    assert app.view()['config'] == expected
    # Invalid entries retain text and a visible reason. Navigation cannot close them.
    await tap(80, 143)
    await tap(120, 80)
    await tap(125, 196)
    await tap(176, 226)
    await label('name must contain')
    await snapshot('invalid-name')
    assert app.view()['preset_input']['text'] == ''
    assert app.view()['preset_draft']['name'] == 'Commute'
    await tap(64, 226)
    await tap(220, 20)
    await number('101')
    await tap(176, 226)
    await label('Pedal sensitivity: enter')
    await snapshot('invalid-percentage')
    entry = app.view()['preset_input']
    for start, end in [((215, 220), (20, 220)), ((20, 220), (215, 220)),
                       ((220, 20), (220, 20))]:
        state = await pointer(start, end)
        assert state['preset_page'] == 1 and state['preset_input'] == entry
    await pointer((120, 220), (120, 40))
    assert app.view()['preset_input'] is None
    assert app.view()['preset_draft']['pedal_sensitivity'] == 40
    await number('')
    await tap(176, 226)
    await label('Pedal sensitivity: enter')
    assert app.view()['preset_input']['text'] == ''
    await tap(64, 226)
    # Dip inclusion is independent of cancelling a numeric value.
    await tap(220, 20)
    await tap(220, 20)
    await number('99')
    await tap(120, 196)
    await tap(64, 226)
    assert app.view()['preset_draft']['pedal_dip_compensation'] == 10
    assert app.view()['preset_draft']['dip_included'] is True
    await pointer((120, 220), (120, 40))
    assert app.view()['screen'] == 'preset_slots' and app.view()['config'] == expected
    # A failed whole-preset Save keeps all accepted values for retry and restart.
    await tap(80, 143)
    await tap(220, 20)
    await number('41')
    await tap(176, 226)
    timeline.append({'input': 'storage_failure', 'mode': 'refuse'})
    with patch('os.replace', side_effect=OSError('Controlled disk full')):
        await tap(176, 226)
        await label('Controlled disk full')
        await snapshot('value-failed-save')
    assert app.view()['preset_input'] is None
    assert app.view()['preset_draft']['pedal_sensitivity'] == 41
    assert Application(store=app.store).view()['config'] == expected
    timeline.append({'input': 'storage_failure', 'mode': 'none'})
    await tap(176, 226)
    expected['revision'] = 2
    expected['presets'][2]['pedal_sensitivity'] = 41
    assert app.view()['config'] == expected
    assert Application(store=app.store).view()['config'] == expected
    await pointer((120, 220), (120, 40))
    assert app.view()['screen'] == 'settings'
    await pointer((120, 220), (120, 40))
    assert app.view()['screen'] == 'dashboard'
    return {'spec': 'docs/design/preset-value-editor.md', 'timeline': timeline,
            'renderings': renderings, 'saved': expected, 'packets': [], 'outcome': 'passed'}


if __name__ == '__main__':
    from browser_local_presets import run
    asyncio.run(run(exercise, 'value-editor-laptop', 'preset-values'))
