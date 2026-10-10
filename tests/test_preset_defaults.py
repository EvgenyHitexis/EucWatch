"""#44: public actions, persisted files and independent shared expectations."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eucwatch import Application, ManualClock
from eucwatch.persistence import FileStore

FIXTURE = json.loads(Path('docs/acceptance/scenarios/local-presets.json').read_text())


class PresetDefaultsTests(unittest.TestCase):
    def test_fresh_and_legacy_load_export_review_restore_restart(self):
        self.assertEqual(Application(clock=ManualClock()).view()['config'], FIXTURE['fresh'])
        for case in FIXTURE['cases']:
            with self.subTest(case=case['name']), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'configuration.json'
                path.write_text(json.dumps(case['input']))
                app = Application(clock=ManualClock(), store=FileStore(path))
                self.assertEqual(app.view()['config'], case['expected'])
                self.assertEqual(app.action('configuration_export')['configuration_export'], case['expected'])
                preview = app.action('configuration_import_prepare', content=json.dumps(case['input']))['configuration_preview']
                self.assertEqual(preview['content'], case['expected'])
                self.assertEqual((preview['migration']['from'], preview['migration']['to']), (1, 2))
                self.assertTrue(preview['migration']['changes'])
                saved = app.action('configuration_import_commit')['config']
                for _ in range(2):
                    restarted = Application(clock=ManualClock(), store=FileStore(path))
                    self.assertEqual(restarted.view()['config'], saved)
                    self.assertEqual(restarted.view()['command_events'], [])

    def test_sole_legacy_recovery_survives_interrupted_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'configuration.json'
            backup = path.with_suffix('.last-good.json')
            backup.write_text(json.dumps(FIXTURE['cases'][0]['input']))
            path.write_text('{partial')
            app = Application(clock=ManualClock(), store=FileStore(path))
            self.assertEqual(app.view()['config'], FIXTURE['cases'][0]['expected'])
            self.assertIn('Recovered', app.view()['persistence_error'])
            app.action('configuration_import_prepare', content=json.dumps(FIXTURE['fresh']))
            original_replace = __import__('os').replace
            def interrupt(source, target):
                if target == path:
                    raise OSError('interrupted active replacement')
                return original_replace(source, target)
            with patch('os.replace', side_effect=interrupt):
                state = app.action('configuration_import_commit')
            self.assertIn('interrupted', state['persistence_error'])
            self.assertEqual(Application(store=FileStore(path)).view()['config'], FIXTURE['cases'][0]['expected'])

    def test_failed_first_save_recovers_previous_defaults_not_uncommitted_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'configuration.json'
            app = Application(clock=ManualClock(), store=FileStore(path))
            app.action('configuration_import_prepare', content=json.dumps(FIXTURE['cases'][0]['input']))
            original_replace = __import__('os').replace
            def interrupt(source, target):
                if target == path:
                    raise OSError('interrupted first save')
                return original_replace(source, target)
            with patch('os.replace', side_effect=interrupt):
                state = app.action('configuration_import_commit')
            self.assertEqual(state['config'], FIXTURE['fresh'])
            self.assertEqual(Application(store=FileStore(path)).view()['config'], FIXTURE['fresh'])

    def test_explicit_included_zero_nonzero_and_omitted_values(self):
        expected = [
            ('pedal_dip_compensation', 0, '4c64417021010280808080808080808080808080808080808080808000f0fc0bd4'),
            ('pedal_dip_compensation', 11, '4c6441702101028080808080808080808080808080808080808080800b672ed25c'),
        ]
        for index, case in enumerate(expected):
            with self.subTest(slot=index+1):
                app=Application(clock=ManualClock())
                app.action('configuration_import_prepare',content=json.dumps(FIXTURE['cases'][0]['input']))
                app.action('configuration_import_commit');app.action('simulator_start',controlled=True)
                state=app.action('preset_apply',slot=index+1)
                packets=[row for row in state['command_events'] if row['event']=='submission']
                self.assertEqual((packets[-1]['field'],packets[-1]['value'],packets[-1]['packet_hex']),case)

    def test_invalid_unknown_and_oversized_saved_content_is_visible_without_overwrite(self):
        for content in ['{partial', '{"version":999}', ' ' * 32769]:
            with self.subTest(content=content[:30]), tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'configuration.json';path.write_text(content)
                app=Application(store=FileStore(path))
                self.assertIn('review',app.view()['persistence_error'])
                self.assertEqual(path.read_text(),content)
                self.assertEqual(app.view()['command_events'],[])

    def test_partial_active_write_is_detected_before_publish_and_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'configuration.json';path.write_text(json.dumps(FIXTURE['cases'][0]['input']))
            app=Application(clock=ManualClock(),store=FileStore(path));before=app.view()['config']
            app.action('configuration_import_prepare',content=json.dumps(FIXTURE['fresh']))
            original_replace=__import__('os').replace
            def partial(source,target):
                original_replace(source,target)
                if target==path:target.write_text('{partial')
            with patch('os.replace',side_effect=partial):state=app.action('configuration_import_commit')
            self.assertEqual(state['config'],before);self.assertIn('save failed',state['persistence_error'])
            self.assertEqual(Application(store=FileStore(path)).view()['config'],before)

    def test_valid_but_wrong_active_readback_is_not_accepted_on_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'configuration.json';path.write_text(json.dumps(FIXTURE['cases'][0]['input']))
            app=Application(clock=ManualClock(),store=FileStore(path));before=app.view()['config']
            opened=app.action('preset_begin',slot=1);identity=opened['preset_editor']['id']
            app.action('preset_update',editor_id=identity,name='Requested')
            original_replace=__import__('os').replace
            def wrong(source,target):
                original_replace(source,target)
                if target==path:target.write_text(json.dumps(FIXTURE['fresh']))
            with patch('os.replace',side_effect=wrong):state=app.action('preset_save',editor_id=identity)
            self.assertEqual(state['config'],before);self.assertIn('readback failed',state['persistence_error'])
            self.assertEqual(state['preset_draft']['name'],'Requested')
            self.assertEqual(Application(store=FileStore(path)).view()['config'],before)
            state=app.action('preset_save',editor_id=identity)
            self.assertEqual(state['config']['presets'][0]['name'],'Requested')
            self.assertEqual(Application(store=FileStore(path)).view()['config'],state['config'])
