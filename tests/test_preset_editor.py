"""Local drafts through public actions/raw notifications/saved views and output."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from eucwatch import Application, ManualClock
from eucwatch.persistence import FileStore
from eucwatch.recording import Replay
from support import edit, settings_frame


class PresetEditorTests(unittest.TestCase):
    def test_finished_entry_actions_cannot_change_later_entries_or_drafts(self):
        app = Application(clock=ManualClock())
        opened = app.action('preset_begin', slot=3)
        state = edit(app, 'preset_input_begin')
        old = {'editor_id': opened['preset_editor']['id'], 'entry_id': state['preset_input']['id']}
        edit(app, 'preset_input_cancel')
        edit(app, 'preset_input_begin')
        before = app.view()
        for action, payload in [('preset_input_accept', {}), ('preset_input_cancel', {}),
                                ('preset_input_key', {'key': 'Clear'}), ('preset_input_page', {'delta': 1}),
                                ('swipe', {'direction': 'up'}), ('preset_page', {'page': 1}),
                                ('preset_save', {}), ('preset_cancel', {})]:
            with self.assertRaisesRegex(ValueError, 'changed'):
                app.action(action, **old, **payload)
            self.assertEqual(app.view()['preset_input'], before['preset_input'])
            self.assertEqual(app.view()['preset_draft'], before['preset_draft'])
        edit(app, 'preset_input_cancel')
        before = app.view()
        with self.assertRaisesRegex(ValueError, 'changed'):
            app.action('swipe', direction='up', **old)
        self.assertEqual(app.view()['screen'], before['screen'])
        edit(app, 'preset_cancel')
        app.action('preset_begin', slot=4)
        edit(app, 'preset_input_begin')
        before = app.view()
        with self.assertRaisesRegex(ValueError, 'changed'):
            app.action('preset_input_accept', **old)
        self.assertEqual(app.view()['preset_draft'], before['preset_draft'])

    def test_value_ok_accepts_only_into_the_draft_and_cancel_restores_latest_accepted_value(self):
        app = Application(clock=ManualClock())
        before = app.view()['config']
        app.action('preset_begin', slot=3)
        edit(app, 'preset_input_begin')
        edit(app, 'preset_input_key', key='Clear')
        for key in 'COMMUTE':
            page = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.index(key) // 12
            while app.view()['preset_input']['letters'] != page:
                edit(app, 'preset_input_page', delta=1)
            edit(app, 'preset_input_key', key=key)
        self.assertEqual(app.view()['preset_draft']['name'], 'Road')
        state = edit(app, 'preset_input_accept')
        self.assertIsNone(state['preset_input'])
        self.assertEqual(state['preset_draft']['name'], 'COMMUTE')
        self.assertEqual(state['config'], before)
        edit(app, 'preset_page', page=1)
        for text, action, expected in [('40', 'preset_input_cancel', 30),
                                       ('40', 'preset_input_accept', 40),
                                       ('42', 'preset_input_cancel', 40)]:
            edit(app, 'preset_input_begin')
            edit(app, 'preset_input_key', key='Clear')
            for key in text:
                edit(app, 'preset_input_key', key=key)
            state = edit(app, action)
            self.assertIsNone(state['preset_input'])
            self.assertEqual(state['preset_draft']['pedal_sensitivity'], expected)
            self.assertEqual(state['preset_draft']['name'], 'COMMUTE')
            self.assertEqual(state['config'], before)
        state = edit(app, 'preset_save')
        self.assertEqual(state['screen'], 'preset_slots')
        expected = before
        expected['revision'] += 1
        expected['presets'][2].update(name='COMMUTE', pedal_sensitivity=40)
        self.assertEqual(state['config'], expected)
        self.assertEqual(state['command_events'], [])

    def test_all_slots_save_draft_locally_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            store=FileStore(Path(directory)/'config.json');app=Application(clock=ManualClock(),store=store)
            for slot in range(1,5):
                before=app.view()['config'];opened=app.action('preset_begin',slot=slot)
                self.assertEqual(opened['preset_draft'],before['presets'][slot-1])
                edit(app,'preset_update',name=f'City {slot}',pedal_sensitivity=31,dynamic_assist=26,pedal_dip_compensation=11)
                edit(app,'preset_include_dip',included=False)
                self.assertEqual(app.view()['config'],before)
                state=edit(app,'preset_save')
                self.assertEqual(state['screen'],'preset_slots');self.assertIsNone(state['preset_editor'])
                self.assertEqual(state['config']['revision'],before['revision']+1)
                self.assertEqual(state['config']['presets'][slot-1],{'id':slot,'name':f'City {slot}','configured':True,'pedal_sensitivity':31,'dynamic_assist':26,'pedal_dip_compensation':11,'dip_included':False})
                self.assertEqual(state['config']['presets'][:slot-1]+state['config']['presets'][slot:],before['presets'][:slot-1]+before['presets'][slot:])
                self.assertEqual(state['command_events'],[])
                self.assertEqual(Application(store=FileStore(store.path)).view()['config'],state['config'])

    def test_input_navigation_validation_cancel_and_duplicate_completion(self):
        app=Application(clock=ManualClock());before=app.view()['config'];opened=app.action('preset_begin',slot=3);old=opened['preset_editor']['id']
        edit(app,'preset_input_begin');edit(app,'preset_input_key',key='Clear');edit(app,'preset_input_key',key='A')
        edit(app,'preset_input_accept')
        edit(app,'preset_page',page=1);edit(app,'preset_input_begin');edit(app,'preset_input_key',key='Clear')
        state=edit(app,'preset_input_accept');self.assertIn('Pedal sensitivity',state['preset_editor']['reason']);self.assertEqual(state['config'],before)
        for direction in ['left','right']:
            state=edit(app,'swipe',direction=direction)
            self.assertEqual(state['preset_page'],1);self.assertEqual(state['preset_input']['text'],'')
        edit(app,'preset_input_key',key='3');edit(app,'preset_input_key',key='1');edit(app,'preset_input_accept')
        state=edit(app,'preset_save')
        self.assertEqual(state['config']['presets'][2]['name'],'A');self.assertEqual(state['config']['presets'][2]['pedal_sensitivity'],31)
        app.action('preset_begin',slot=4)
        with self.assertRaises(ValueError):app.action('preset_save',editor_id=old)
        saved=app.view()['config'];edit(app,'preset_update',name='Discard');edit(app,'preset_cancel');self.assertEqual(app.view()['config'],saved)
        for action in ['preset_clear','preset_input_done']:
            with self.assertRaises(ValueError):app.action(action,slot=1)

    def test_wheel_changes_reconnect_and_replay_do_not_own_drafts(self):
        app=Application(clock=ManualClock());app.action('preset_begin',slot=4);edit(app,'preset_update',name='Local')
        expected=app.view()['preset_draft']
        app.action('connect');app.receive(app.session,settings_frame(44,55,66));app.receive(app.session-1,settings_frame());app.receive(app.session,b'corrupt')
        app.action('disconnect');app.action('connect');self.assertEqual(app.view()['preset_draft'],expected)
        self.assertEqual(app.view()['command_events'],[])
        fixture=Path('experiments/laptop-feasibility/evidence/fixture-recording.jsonl');app.action('replay_start',recording=Replay.load(fixture))
        app.action('preset_begin',slot=2);edit(app,'preset_update',name='Replay')
        edit(app,'preset_page',page=1);edit(app,'preset_input_begin');edit(app,'preset_input_key',key='Clear')
        edit(app,'preset_input_key',key='4');edit(app,'preset_input_key',key='0');edit(app,'preset_input_accept')
        edit(app,'preset_input_begin');edit(app,'preset_input_key',key='Clear');edit(app,'preset_input_cancel')
        edit(app,'preset_save')
        self.assertEqual(app.view()['config']['presets'][1]['name'],'Replay')
        self.assertEqual(app.view()['config']['presets'][1]['pedal_sensitivity'],40)
        self.assertEqual(app.view()['command_events'],[])
        with self.assertRaises(ValueError):app.action('preset_apply',slot=2)

    def test_file_failure_retry_and_replacement_invalidate_old_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.json';app=Application(clock=ManualClock(),store=FileStore(path));before=app.view()['config']
            app.action('preset_begin',slot=4);edit(app,'preset_update',name='Retry',pedal_dip_compensation=17)
            with patch('os.replace',side_effect=OSError('Disk full')):state=edit(app,'preset_save')
            self.assertEqual(state['config'],before);self.assertEqual(state['preset_draft']['name'],'Retry');self.assertIn('Disk full',state['persistence_error'])
            self.assertEqual(state['preset_notice'],'Configuration save failed: Disk full');self.assertEqual(state['preset_entry_notice'],'Save failed: Disk full')
            state=edit(app,'preset_save');self.assertEqual(state['config']['presets'][3]['pedal_dip_compensation'],17);self.assertEqual(state['command_events'],[])
            app.action('preset_begin',slot=1);old=app.view()['preset_editor']['id']
            app.action('configuration_import_prepare',content=json.dumps(before));app.action('configuration_import_commit')
            with self.assertRaises(ValueError):app.action('preset_save',editor_id=old)
            self.assertIsNone(app.view()['preset_editor'])

    def test_save_stops_unsent_application_without_editor_packets(self):
        writes=[];app=Application(clock=ManualClock(),command_output=writes.append);app.action('connect');app.receive(app.session,settings_frame())
        app.action('preset_apply',slot=1);row=writes[0]
        app.action('preset_begin',slot=1);edit(app,'preset_update',dynamic_assist=12);edit(app,'preset_save')
        app.action('command_result',attempt=row['attempt'],session=row['session'],index=0,success=True)
        self.assertEqual(len(writes),1);self.assertFalse(app.view()['preset_attempt']['pending']);self.assertIn('changed',app.view()['preset_attempt']['reason'])

    def test_shared_raw_frame_fixture_cannot_replace_active_keypad(self):
        fixture=json.loads(Path('docs/acceptance/scenarios/local-editor-frames.json').read_text())
        app=Application(clock=ManualClock());app.action('preset_begin',slot=4)
        edit(app,'preset_input_begin');edit(app,'preset_input_key',key='Clear');edit(app,'preset_input_key',key='A')
        observations=[]
        app.action('connect');old=app.session
        for session,raw in [(old,fixture['frame_hex']),(old,fixture['corrupt_hex']),(old-1,fixture['frame_hex'])]:
            app.clock.advance(.1);app.receive(session,bytes.fromhex(raw))
            self.assertEqual(app.view()['preset_draft'],fixture['expected_draft']);self.assertEqual(app.view()['preset_input']['text'],fixture['expected_input'])
            observations.append({'session':session,'raw_hex':raw,'draft':app.view()['preset_draft'],'input':app.view()['preset_input'],'packets':app.view()['command_events']})
        app.action('disconnect');app.action('connect');app.receive(old,bytes.fromhex(fixture['frame_hex']))
        self.assertEqual(app.view()['preset_draft'],fixture['expected_draft']);self.assertEqual(app.view()['command_events'],[])
        output=Path('.test-output/local-editor-frames.json');output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps({'fixture':fixture,'observations':observations,'reconnect_input':app.view()['preset_input'],'outcome':'passed'},indent=2)+'\n')
