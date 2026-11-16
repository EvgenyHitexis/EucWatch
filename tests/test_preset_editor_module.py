"""The Preset editor at its own interface, without an Application (#58)."""
import unittest

from eucwatch.configuration import default_configuration
from eucwatch.presets import PresetEditor


class PresetEditorModuleTests(unittest.TestCase):
    def setUp(self):
        self.config = default_configuration()
        self.editor = PresetEditor()

    def act(self, action, /, editable=True, **payload):
        """Send one editor-scoped action with the identities the current view shows."""
        view = self.editor.view()
        payload.setdefault('editor_id', view['preset_editor']['id'])
        if view['preset_input'] is not None:
            payload.setdefault('entry_id', view['preset_input']['id'])
        return self.editor.action(action, payload, editable, self.config)

    def test_actions_carrying_a_finished_editor_or_entry_identity_change_nothing(self):
        self.editor.open(self.config, 3)
        first = self.editor.view()['preset_editor']['id']
        self.act('preset_input_begin')
        finished_entry = self.editor.view()['preset_input']['id']
        self.act('preset_input_cancel')
        self.act('preset_input_begin')
        before = self.editor.view()
        for name, payload in [('preset_input_key', {'key': '1'}), ('preset_input_accept', {}),
                              ('preset_input_cancel', {}), ('preset_page', {'page': 1})]:
            with self.assertRaisesRegex(ValueError, 'Preset value entry changed'):
                self.editor.action(name, {'editor_id': first, 'entry_id': finished_entry, **payload}, True, self.config)
            self.assertEqual(self.editor.view(), before)
        self.act('preset_input_cancel')
        self.editor.open(self.config, 4)
        before = self.editor.view()
        for name in ['preset_page', 'preset_save', 'preset_cancel', 'preset_input_begin']:
            with self.assertRaisesRegex(ValueError, 'Preset editor changed'):
                self.editor.action(name, {'editor_id': first, 'page': 1}, True, self.config)
            self.assertEqual(self.editor.view(), before)
        with self.assertRaisesRegex(ValueError, 'Preset value entry changed'):
            self.editor.action('preset_input_key', {'editor_id': before['preset_editor']['id'], 'key': '1'}, True, self.config)

    def test_swipes_turn_field_pages_close_the_entry_then_leave(self):
        self.editor.open(self.config, 2)
        ids = lambda: {'editor_id': self.editor.view()['preset_editor']['id'],
                       'entry_id': (self.editor.view()['preset_input'] or {}).get('id')}
        pages = []
        for direction in ['right', 'right', 'left', 'left', 'left', 'down']:
            self.assertFalse(self.editor.swipe({'direction': direction, **ids()}))
            pages.append(self.editor.view()['preset_page'])
        self.assertEqual(pages, [3, 2, 3, 0, 1, 1])
        self.act('preset_input_begin')
        self.assertFalse(self.editor.swipe({'direction': 'left', **ids()}))
        self.assertEqual(self.editor.view()['preset_page'], 1)
        self.assertIsNotNone(self.editor.view()['preset_input'])
        self.assertFalse(self.editor.swipe({'direction': 'up', **ids()}))
        self.assertIsNone(self.editor.view()['preset_input'])
        self.assertEqual(self.editor.view()['preset_draft'], self.config['presets'][1])
        self.assertTrue(self.editor.swipe({'direction': 'up', **ids()}))

    def test_swipe_carrying_a_finished_identity_changes_nothing(self):
        self.editor.open(self.config, 1)
        first = self.editor.view()['preset_editor']['id']
        self.editor.open(self.config, 1)
        before = self.editor.view()
        with self.assertRaisesRegex(ValueError, 'Preset editor changed'):
            self.editor.swipe({'direction': 'up', 'editor_id': first})
        self.act('preset_input_begin')
        before = self.editor.view()
        with self.assertRaisesRegex(ValueError, 'Preset value entry changed'):
            self.editor.swipe({'direction': 'up', 'editor_id': before['preset_editor']['id']})
        self.assertEqual(self.editor.view(), before)

    def test_view_lists_fields_labels_neighbour_pages_and_the_keypad_key_set(self):
        self.editor.open(self.config, 3)
        view = self.editor.view()
        self.assertEqual(view['preset_fields'], ['name', 'pedal_sensitivity', 'dynamic_assist', 'pedal_dip_compensation'])
        self.assertEqual(view['preset_labels'], ['Name', 'Pedal sensitivity', 'Dynamic assist', 'Pedal dip compensation'])
        self.assertEqual((view['preset_previous_page'], view['preset_next_page'], view['preset_keys']), (3, 1, []))
        self.act('preset_input_begin')
        self.assertEqual(self.editor.view()['preset_keys'], list('ABCDEFGHIJKL'))
        self.act('preset_input_page', delta=1)
        self.act('preset_input_key', key='a/A')
        self.assertEqual(self.editor.view()['preset_keys'], list('mnopqrstuvwx'))
        self.act('preset_input_page', delta=-1)
        self.act('preset_input_page', delta=-1)
        self.assertEqual(self.editor.view()['preset_keys'], list('yz0123456789'))
        self.act('preset_input_cancel')
        self.act('preset_page', page=3)
        view = self.editor.view()
        self.assertEqual((view['preset_previous_page'], view['preset_next_page']), (2, 0))
        self.act('preset_input_begin')
        self.assertEqual(self.editor.view()['preset_keys'], ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'Clear', '0', '<'])
        with self.assertRaisesRegex(ValueError, 'Invalid preset input key'):
            self.act('preset_input_key', key='A')

    def test_percentage_entry_accepts_whole_0_to_100_and_shows_the_short_reason_in_the_entry(self):
        self.editor.open(self.config, 3)
        self.act('preset_page', page=1)
        for text, accepted in [('100', 100), ('0', 0), ('101', None), ('', None)]:
            self.act('preset_input_begin')
            self.act('preset_input_key', key='Clear')
            for key in text:
                self.act('preset_input_key', key=key)
            if len(text) == 3:
                self.act('preset_input_key', key='9')  # A fourth digit is not typed.
            self.assertEqual(self.editor.view()['preset_input']['text'], text)
            self.act('preset_input_accept')
            view = self.editor.view()
            if accepted is None:
                self.assertEqual(view['preset_editor']['reason'], 'Pedal sensitivity: enter a whole percentage 0–100')
                self.assertEqual(view['preset_notice'], 'Pedal sensitivity: enter a whole percentage 0–100')
                self.assertEqual(view['preset_entry_notice'], 'Enter whole % (0–100)')
                self.act('preset_input_cancel')
                self.assertEqual((self.editor.view()['preset_notice'], self.editor.view()['preset_entry_notice']), ('', ''))
            else:
                self.assertIsNone(view['preset_input'])
                self.assertEqual(view['preset_draft']['pedal_sensitivity'], accepted)
                self.assertEqual(view['preset_notice'], '')

    def test_the_editor_reason_wins_over_a_configuration_problem_shown_short_in_the_entry(self):
        self.assertEqual(self.editor.view('Configuration save failed: Disk full')['preset_notice'], '')
        self.editor.open(self.config, 1)
        view = self.editor.view('Configuration save failed: Disk full')
        self.assertEqual(view['preset_notice'], 'Configuration save failed: Disk full')
        self.assertEqual(view['preset_entry_notice'], 'Save failed: Disk full')
        view = self.editor.view('Saved configuration requires review: bad')
        self.assertEqual((view['preset_notice'], view['preset_entry_notice']), ('Saved configuration requires review: bad',) * 2)
        self.act('preset_input_begin')
        self.act('preset_input_key', key='Clear')
        self.act('preset_input_accept')
        view = self.editor.view('Configuration save failed: Disk full')
        self.assertEqual(view['preset_notice'], 'Preset name must contain 1–24 readable characters')
        self.assertEqual(view['preset_entry_notice'], 'Preset name must contain 1–24 readable characters')

    def test_only_cancel_is_allowed_while_editing_is_unavailable(self):
        self.editor.open(self.config, 4)
        before = self.editor.view()
        for name, payload in [('preset_page', {'page': 1}), ('preset_input_begin', {}),
                              ('preset_update', {'name': 'X'}), ('preset_include_dip', {'included': True}),
                              ('preset_save', {})]:
            with self.assertRaisesRegex(ValueError, 'Preset editing unavailable'):
                self.act(name, editable=False, **payload)
            self.assertEqual(self.editor.view(), before)
        self.assertEqual(self.act('preset_cancel', editable=False), {'leave': True})

    def test_an_open_value_entry_must_be_finished_before_the_draft_changes_or_saves(self):
        self.editor.open(self.config, 1)
        self.act('preset_input_begin')
        self.act('preset_input_key', key='Clear')
        before = self.editor.view()
        with self.assertRaisesRegex(ValueError, 'Finish the current preset value entry first'):
            self.act('preset_update', name='Other')
        self.assertEqual(self.editor.view()['preset_draft'], before['preset_draft'])
        self.assertIsNone(self.act('preset_save'))
        view = self.editor.view()
        self.assertEqual(view['preset_notice'], 'Finish the current preset value entry first')
        self.assertEqual(view['preset_entry_notice'], 'Finish the current preset value entry first')
        self.assertEqual(view['preset_input']['text'], '')
        self.assertEqual(view['preset_draft'], self.config['presets'][0])

    def test_save_returns_the_replacement_for_the_caller_and_a_refused_save_keeps_the_draft(self):
        self.editor.open(self.config, 2)
        self.assertIsNone(self.act('preset_update', name='Trail', dynamic_assist=12, source='panel'))
        self.assertIsNone(self.act('preset_include_dip', included=True))
        saved = self.act('preset_save')
        expected = default_configuration()
        expected['revision'] = 1
        expected['presets'][1].update(name='Trail', dynamic_assist=12, dip_included=True)
        self.assertEqual(saved, {'save': expected})
        self.assertEqual(self.config, default_configuration())
        self.assertTrue(self.editor.is_open())
        self.act('preset_update', pedal_sensitivity='150')
        self.assertIsNone(self.act('preset_save'))
        self.assertEqual(self.editor.view()['preset_notice'], 'Pedal sensitivity: enter a whole percentage 0–100')
        self.assertEqual(self.editor.view()['preset_draft']['pedal_sensitivity'], '150')
        with self.assertRaisesRegex(ValueError, 'Invalid preset draft field'):
            self.act('preset_update', dip_included=False)
        self.editor.close()
        self.assertFalse(self.editor.is_open())
        self.assertIsNone(self.editor.view()['preset_editor'])


if __name__ == '__main__':
    unittest.main()
