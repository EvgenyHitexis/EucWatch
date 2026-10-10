"""Transient local preset editor. Only whole-editor Save creates a replacement."""
from copy import deepcopy
import re
from typing import Any
from .configuration import validate_configuration, validate_preset_name

FIELDS = ('name', 'pedal_sensitivity', 'dynamic_assist', 'pedal_dip_compensation')
LABELS = ('Name', 'Pedal sensitivity', 'Dynamic assist', 'Pedal dip compensation')


def validate_value(field: str, value: Any) -> str | int:
    if field == 'name':
        validate_preset_name(value)
    else:
        if isinstance(value, str) and re.fullmatch(r'[0-9]{1,3}', value):
            value = int(value)
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError(f'{LABELS[FIELDS.index(field)]}: enter a whole percentage 0–100')
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


class PresetEditor:
    def __init__(self):
        self.next_id = 1
        self.next_entry_id = 1
        self.request: dict[str, Any] | None = None
        self.draft: dict[str, Any] | None = None
        self.page = 0
        self.input: dict[str, Any] | None = None

    def open(self, config: dict[str, Any], slot: Any) -> None:
        self.draft = deepcopy(config['presets'][validate_slot(slot) - 1])
        self.request = {'id': self.next_id, 'slot': slot, 'status': 'ready', 'reason': ''}
        self.next_id += 1
        self.page = 0
        self.input = None

    def require(self, identity: Any) -> None:
        if not self.request or type(identity) is not int or identity != self.request['id']:
            raise ValueError('Preset editor changed; open a fresh editor operation')

    def update(self, changes: dict[str, Any]) -> None:
        if self.input:
            raise ValueError('Finish the current preset value entry first')
        if not self.draft or not changes or set(changes) - set(FIELDS):
            raise ValueError('Invalid preset draft field')
        self.draft.update(deepcopy(changes))

    def require_input(self, identity: Any) -> None:
        if not self.input or type(identity) is not int or identity != self.input['id']:
            raise ValueError('Preset value entry changed; open a fresh entry')

    def keys(self) -> list[str]:
        if not self.input:
            return []
        if self.input['field'] != 'name':
            return ['1','2','3','4','5','6','7','8','9','Clear','0','<']
        start = self.input['letters'] * 12
        chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'[start:start+12]
        return list(chars.lower() if self.input['lowercase'] else chars)

    def set_reason(self, reason: str) -> None:
        assert self.request is not None
        self.request['reason'] = reason

    def include_dip(self, included: Any) -> None:
        if type(included) is not bool:
            raise ValueError('Choose explicit dip inclusion')
        assert self.draft is not None
        self.draft['dip_included'] = included

    def input_page(self, delta: Any) -> None:
        if self.input is None or self.input['field'] != 'name' or type(delta) is not int or delta not in (-1, 1):
            raise ValueError('Invalid name keypad page')
        self.input['letters'] = (self.input['letters'] + delta) % 3

    def begin_input(self) -> None:
        assert self.draft is not None
        if self.input:
            return
        field = FIELDS[self.page]
        self.input = {'id': self.next_entry_id, 'field': field, 'text': str(self.draft[field]), 'letters': 0, 'lowercase': False}
        self.next_entry_id += 1

    def set_page(self, page: Any) -> None:
        if type(page) is not int or not 0 <= page <= 3:
            raise ValueError('Invalid preset page')
        if self.input is None:
            self.page = page

    def key(self, key: Any) -> None:
        if self.input is None or self.draft is None:
            raise ValueError('No preset input is open')
        entry = self.input
        if key == 'Clear':
            entry['text'] = ''
        elif key == '<':
            entry['text'] = entry['text'][:-1]
        elif key == 'a/A' and entry['field'] == 'name':
            entry['lowercase'] = not entry['lowercase']
        elif key in self.keys() or (key == ' ' and entry['field'] == 'name'):
            if len(entry['text']) < (24 if entry['field'] == 'name' else 3):
                entry['text'] += key
        else:
            raise ValueError('Invalid preset input key')

    def accept_input(self) -> None:
        assert self.input is not None and self.draft is not None
        self.draft[self.input['field']] = validate_value(self.input['field'], self.input['text'])
        self.input = None

    def cancel_input(self) -> None:
        self.input = None

    def validated(self, config: dict[str, Any]) -> dict[str, Any]:
        assert self.draft is not None
        if self.input:
            raise ValueError('Finish the current preset value entry first')
        draft = deepcopy(self.draft)
        for field in FIELDS:
            draft[field] = validate_value(field, draft[field])
        return replacement(config, draft)

    def close(self) -> None:
        self.request = None
        self.draft = None
        self.input = None
        self.page = 0

    def view(self) -> dict[str, Any] | None:
        return deepcopy(self.request)
