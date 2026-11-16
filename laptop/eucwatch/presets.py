"""Preset editor: Preset draft, Preset value entry, field page and their rules.

Local only: Save returns a replacement configuration for the caller to persist and never
reaches a wheel writer (ADR 0002). The caller decides whether editing is allowed, persists
the replacement and changes screens; the editor checks identities, handles every
editor-scoped action and in-editor swipe, and returns its complete view.
"""
from copy import deepcopy
import re
from typing import Any
from .configuration import (WHOLE_PERCENTAGE, validate_configuration, validate_preset_name,
                            whole_percentage)
from .persistence import SAVE_FAILED

FIELDS = ('name', 'pedal_sensitivity', 'dynamic_assist', 'pedal_dip_compensation')
LABELS = ('Name', 'Pedal sensitivity', 'Dynamic assist', 'Pedal dip compensation')
# The actions that act on the open Preset value entry, so they need its entry id.
ENTRY_ACTIONS = ('preset_input_key', 'preset_input_page', 'preset_input_accept', 'preset_input_cancel')
# Every editor-scoped action; the caller routes exactly these to PresetEditor.action.
ACTIONS = ('preset_update', 'preset_cancel', 'preset_save', 'preset_include_dip', 'preset_page',
           'preset_input_begin') + ENTRY_ACTIONS
NAME_KEYS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
NUMBER_KEYS = ('1', '2', '3', '4', '5', '6', '7', '8', '9', 'Clear', '0', '<')
NAME_LENGTH = 24
_LOW, _HIGH = WHOLE_PERCENTAGE
PERCENTAGE_LENGTH = len(str(_HIGH))
_PERCENTAGE_TEXT = re.compile(f'[0-9]{{1,{PERCENTAGE_LENGTH}}}')
# The value-entry header is narrow; these are the short forms it shows.
SAVE_FAILED_SHORT = 'Save failed: '
PERCENTAGE_SHORT = f'Enter whole % ({_LOW}–{_HIGH})'


class PercentageError(ValueError):
    """A preset riding value outside the whole-percentage rule."""

    def __init__(self, field: str):
        super().__init__(f'{LABELS[FIELDS.index(field)]}: enter a whole percentage {_LOW}–{_HIGH}')
        self.short = PERCENTAGE_SHORT


def validate_value(field: str, value: Any) -> str | int:
    if field == 'name':
        validate_preset_name(value)
    else:
        if isinstance(value, str) and _PERCENTAGE_TEXT.fullmatch(value):
            value = int(value)
        if not whole_percentage(value):
            raise PercentageError(field)
    return value


def validate_slot(slot: Any) -> int:
    if type(slot) is not int or not 1 <= slot <= 4:
        raise ValueError('Choose one of the four fixed preset slots')
    return slot


def replacement(config: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    proposed = deepcopy(config)
    proposed['presets'][validate_slot(draft['id']) - 1] = deepcopy(draft)
    proposed['revision'] += 1
    return validate_configuration(proposed)


def _keys(entry: dict[str, Any] | None) -> list[str]:
    """The keypad key set of a Preset value entry ([] without one)."""
    if not entry:
        return []
    if entry['field'] != 'name':
        return list(NUMBER_KEYS)
    start = entry['letters'] * 12
    chars = NAME_KEYS[start:start + 12]
    return list(chars.lower() if entry['lowercase'] else chars)


class PresetEditor:
    """One Preset editor operation at a time.

    - open(config, slot) / close(): start a fresh operation or end it.
    - is_open(): whether an operation is open.
    - action(name, payload, editable, config): one name from ACTIONS, checked against the
      editor id, then the entry id, then `editable` (Cancel is allowed while not editable);
      it clears the reason first. Raises ValueError for a refused action. Returns None,
      {'leave': True}, or {'save': replacement} for the caller to persist; a refused Save
      sets the reason and returns None.
    - swipe(payload): left/right turn the field page unless an entry is open; up closes the
      entry, otherwise returns True so the caller leaves the editor.
    - view(persistence_error): the complete editor view, keyed as the Application publishes it.
    """

    def __init__(self):
        self._next_id = 1
        self._next_entry_id = 1
        self._request: dict[str, Any] | None = None
        self._draft: dict[str, Any] | None = None
        self._page = 0
        self._input: dict[str, Any] | None = None
        self._short_reason = ''

    def open(self, config: dict[str, Any], slot: Any) -> None:
        self._draft = deepcopy(config['presets'][validate_slot(slot) - 1])
        self._request = {'id': self._next_id, 'slot': slot, 'status': 'ready', 'reason': ''}
        self._next_id += 1
        self._page = 0
        self._input = None
        self._short_reason = ''

    def close(self) -> None:
        self._request = None
        self._draft = None
        self._input = None
        self._page = 0
        self._short_reason = ''

    def is_open(self) -> bool:
        return self._request is not None

    def action(self, name: str, payload: dict[str, Any], editable: bool,
               config: dict[str, Any]) -> dict[str, Any] | None:
        if name not in ACTIONS:
            raise ValueError(f'Unknown action: {name}')
        self._current(payload, name in ENTRY_ACTIONS)
        if name != 'preset_cancel' and not editable:
            raise ValueError('Preset editing unavailable')
        self._set_reason('')
        if name == 'preset_update':
            self._update({k: v for k, v in payload.items() if k not in ('editor_id', 'entry_id', 'source')})
        elif name == 'preset_include_dip':
            self._include_dip(payload.get('included'))
        elif name == 'preset_page':
            self._set_page(payload.get('page'))
        elif name == 'preset_input_begin':
            self._begin_input()
        elif name == 'preset_input_key':
            self._key(payload.get('key'))
        elif name == 'preset_input_page':
            self._input_page(payload.get('delta'))
        elif name == 'preset_input_accept':
            self._accept_input()
        elif name == 'preset_input_cancel':
            self._input = None
        elif name == 'preset_cancel':
            return {'leave': True}
        elif name == 'preset_save':
            return self._save(config)
        return None

    def swipe(self, payload: dict[str, Any]) -> bool:
        direction = payload.get('direction')
        self._current(payload, self._input is not None)
        if direction in ('left', 'right'):
            self._set_page((self._page + (1 if direction == 'left' else -1)) % 4)
        elif direction == 'up':
            if not self._input:
                return True
            self._input = None
            self._set_reason('')
        return False

    def view(self, persistence_error: str | None = None) -> dict[str, Any]:
        reason = self._request['reason'] if self._request else ''
        persistence = (persistence_error or '') if self._request else ''
        if reason:
            entry_notice = self._short_reason
        else:
            entry_notice = persistence.replace(SAVE_FAILED, SAVE_FAILED_SHORT, 1)
        return {
            'preset_draft': deepcopy(self._draft),
            'preset_editor': deepcopy(self._request),
            'preset_page': self._page,
            'preset_input': deepcopy(self._input),
            'preset_keys': _keys(self._input),
            'preset_fields': list(FIELDS),
            'preset_labels': list(LABELS),
            'preset_previous_page': (self._page + 3) % 4,
            'preset_next_page': (self._page + 1) % 4,
            # The reason to show: the editor's own, otherwise the configuration problem.
            'preset_notice': reason or persistence,
            # The same reason in the short form the value-entry header shows.
            'preset_entry_notice': entry_notice,
        }

    def _current(self, payload: dict[str, Any], entry: bool) -> None:
        identity = payload.get('editor_id')
        if not self._request or type(identity) is not int or identity != self._request['id']:
            raise ValueError('Preset editor changed; open a fresh editor operation')
        entry_id = payload.get('entry_id')
        if entry or entry_id is not None:
            if not self._input or type(entry_id) is not int or entry_id != self._input['id']:
                raise ValueError('Preset value entry changed; open a fresh entry')

    def _set_reason(self, reason: str, short: str | None = None) -> None:
        assert self._request is not None
        self._request['reason'] = reason
        self._short_reason = reason if short is None else short

    def _refuse(self, exc: ValueError) -> None:
        self._set_reason(str(exc), getattr(exc, 'short', None))

    def _update(self, changes: dict[str, Any]) -> None:
        if self._input:
            raise ValueError('Finish the current preset value entry first')
        if not self._draft or not changes or set(changes) - set(FIELDS):
            raise ValueError('Invalid preset draft field')
        self._draft.update(deepcopy(changes))

    def _include_dip(self, included: Any) -> None:
        if type(included) is not bool:
            raise ValueError('Choose explicit dip inclusion')
        assert self._draft is not None
        self._draft['dip_included'] = included

    def _set_page(self, page: Any) -> None:
        if type(page) is not int or not 0 <= page <= 3:
            raise ValueError('Invalid preset page')
        if self._input is None:
            self._page = page

    def _begin_input(self) -> None:
        assert self._draft is not None
        if self._input:
            return
        field = FIELDS[self._page]
        self._input = {'id': self._next_entry_id, 'field': field, 'text': str(self._draft[field]),
                       'letters': 0, 'lowercase': False}
        self._next_entry_id += 1

    def _input_page(self, delta: Any) -> None:
        if self._input is None or self._input['field'] != 'name' or type(delta) is not int or delta not in (-1, 1):
            raise ValueError('Invalid name keypad page')
        self._input['letters'] = (self._input['letters'] + delta) % 3

    def _key(self, key: Any) -> None:
        if self._input is None or self._draft is None:
            raise ValueError('No preset input is open')
        entry = self._input
        if key == 'Clear':
            entry['text'] = ''
        elif key == '<':
            entry['text'] = entry['text'][:-1]
        elif key == 'a/A' and entry['field'] == 'name':
            entry['lowercase'] = not entry['lowercase']
        elif key in _keys(entry) or (key == ' ' and entry['field'] == 'name'):
            if len(entry['text']) < (NAME_LENGTH if entry['field'] == 'name' else PERCENTAGE_LENGTH):
                entry['text'] += key
        else:
            raise ValueError('Invalid preset input key')

    def _accept_input(self) -> None:
        assert self._input is not None and self._draft is not None
        try:
            self._draft[self._input['field']] = validate_value(self._input['field'], self._input['text'])
        except ValueError as exc:
            self._refuse(exc)
        else:
            self._input = None

    def _save(self, config: dict[str, Any]) -> dict[str, Any] | None:
        assert self._draft is not None
        try:
            if self._input:
                raise ValueError('Finish the current preset value entry first')
            draft = deepcopy(self._draft)
            for field in FIELDS:
                draft[field] = validate_value(field, draft[field])
            return {'save': replacement(config, draft)}
        except ValueError as exc:
            self._refuse(exc)
            return None
