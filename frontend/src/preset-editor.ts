/** Watch-sized inputs shared by staging flows; completion is an explicit action. */
export interface Preset {
  id: number;
  name: string;
  configured: boolean;
  dip_included: boolean;
  pedal_sensitivity?: number;
  dynamic_assist?: number;
  pedal_dip_compensation?: number;
}
export interface PresetOperation {
  kind: 'preset';
  slot: number;
  name: string;
  status: string;
  pending: boolean;
  requested_s: number;
  submitted_s: number | null;
  reason: string;
  fields: Record<string, { requested: number; actual: number | null; state: string; submitted_s: number | null }>;
}
export interface WatchPresetView {
  screen: string;
  session: number;
  preset_editor: null | { id: number; slot: number; status: string; reason: string };
  preset_draft: (Omit<Preset, 'pedal_sensitivity' | 'dynamic_assist' | 'pedal_dip_compensation'> & Record<string, unknown>) | null;
  preset_page: number;
  preset_input: null | { id: number; field: Field; text: string; letters: number; lowercase: boolean };
  /** The open entry's keypad key set; empty without an entry. */
  preset_keys: string[];
  preset_fields: Field[];
  preset_labels: string[];
  preset_previous_page: number;
  preset_next_page: number;
  /** The reason the editor shows ('' when clear), and its short form for the value-entry header. */
  preset_notice: string;
  preset_entry_notice: string;
  preset_attempt: PresetOperation | null;
  config: { presets: Preset[] };
  persistence_error: string | null;
}
type Field = 'name' | 'pedal_sensitivity' | 'dynamic_assist' | 'pedal_dip_compensation';

type Target = { x: number; y: number; width: number; height: number; label: string; action: string; payload?: Record<string, unknown> };

export class WatchPresets {
  constructor(private ctx: CanvasRenderingContext2D, private canvas: HTMLCanvasElement,
              private enqueue: (action: string, payload?: Record<string, unknown>) => Promise<unknown>) {}
  private text(value: string, x: number, y: number, size = 14, width = 216): void {
    this.ctx.fillStyle = '#ffffff'; this.ctx.font = `${size}px sans-serif`;
    this.ctx.textAlign = 'center'; this.ctx.fillText(value, x, y, width);
  }
  // Drawing and hit testing consume the same rectangles, including the gaps.
  private targets(view: WatchPresetView): Target[] {
    const button = (label: string, x: number, y: number, width: number, height: number, action: string, payload?: Record<string, unknown>): Target => ({label, x, y, width, height, action, payload});
    if (view.screen === 'preset_slots') return view.config.presets.map((slot, index) => button(`${slot.id} · ${slot.name}`, 12, 32 + index * 50, 216, 44, 'preset_begin', {slot: slot.id}));
    if (!view.preset_draft) return [];
    const draft = view.preset_draft, input = view.preset_input, page = view.preset_page, field = view.preset_fields[page];
    const rows: Target[] = [];
    if (input) {
      const isNameEntry = input.field === 'name';
      view.preset_keys.forEach((key, index) => rows.push(button(key,
        12 + index % (isNameEntry ? 4 : 3) * (isNameEntry ? 56 : 74),
        (isNameEntry ? 44 : 52) + Math.floor(index / (isNameEntry ? 4 : 3)) * (isNameEntry ? 38 : 35),
        isNameEntry ? 48 : 68, 32, 'preset_input_key', {key})));
      if (isNameEntry) {
        ['a/A', 'Space', 'Clear', '<', `${input.letters + 1}/3`].forEach((key, index) => rows.push(button(key, 12 + index * 44, 158, 40, 32,
          index === 4 ? 'preset_input_page' : 'preset_input_key', index === 4 ? {delta: 1} : {key: key === 'Space' ? ' ' : key})));
      } else if (field === 'pedal_dip_compensation') rows.push(button(draft.dip_included ? 'Included' : 'Omitted', 144, 4, 84, 40, 'preset_include_dip', {included: !draft.dip_included}));
    } else {
      rows.push(button('‹', 8, 4, 48, 40, 'preset_page', {page: view.preset_previous_page}), button('›', 184, 4, 48, 40, 'preset_page', {page: view.preset_next_page}));
      rows.push(button(String(draft[field]), 12, 72, 216, field === 'pedal_dip_compensation' ? 60 : 112, 'preset_input_begin'));
      if (field === 'pedal_dip_compensation') rows.push(button(draft.dip_included ? 'Dip included' : 'Dip omitted', 12, 140, 216, 44, 'preset_include_dip', {included: !draft.dip_included}));
    }
    return rows.concat([button('Cancel', 12, 196, 104, 40, input ? 'preset_input_cancel' : 'preset_cancel'), button(input ? 'OK' : 'Save', 124, 196, 104, 40, input ? 'preset_input_accept' : 'preset_save')]);
  }
  render(view: WatchPresetView, error: string, available: boolean): boolean {
    if (!['preset_slots', 'preset_editor'].includes(view.screen)) return false;
    if (view.screen === 'preset_editor' && (!view.preset_draft || !view.preset_editor)) return false;
    this.targets(view).forEach(target => {
      this.ctx.strokeStyle = '#ffffff'; this.ctx.strokeRect(target.x, target.y, target.width, target.height);
      this.text(target.label, target.x + target.width / 2, target.y + target.height / 2 + 5, target.width <= 48 ? 12 : target.action === 'preset_input_begin' ? 22 : 16, target.width - 8);
    });
    if (view.screen === 'preset_slots') {
      const notice = view.persistence_error || error;
      this.text(notice ? notice.slice(0, 38) : 'PRESETS', 120, 21, notice ? 11 : 15);
      this.canvas.setAttribute('aria-label', `Settings Presets. ${view.config.presets.map(slot => `Slot ${slot.id}: ${slot.name}, configured`).join('; ')}. Swipe up to Settings. ${notice}`);
      return true;
    }
    const draft = view.preset_draft!, page = view.preset_page, field = view.preset_fields[page], input = view.preset_input, labels = view.preset_labels;
    const notice = !available ? 'Application unavailable' : view.preset_notice || error;
    if (input) {
      const dip = field === 'pedal_dip_compensation', center = dip ? 74 : 120, width = dip ? 124 : 216;
      if (notice) {
        const reason = !available ? notice : view.preset_entry_notice || error, length = dip ? 24 : 38;
        this.text(reason.slice(0, length), center, 11, 10, width); this.text(reason.slice(length, length * 2), center, 23, 10, width);
      } else this.text(dip ? 'Pedal dip %' : labels[page], center, 14, 12, width);
      this.text(input.text || '—', center, notice ? 42 : 38, notice ? 16 : 20, width);
    } else {
      const heading = notice || labels[page], split = notice ? 23 : field === 'pedal_dip_compensation' ? 9 : heading.length;
      this.text(heading.slice(0, split), 120, 20, notice ? 10 : 12, 120);
      this.text(heading.slice(split, notice ? split * 2 : undefined), 120, 35, notice ? 10 : 12, 120);
      this.text(`SLOT ${draft.id} · ${page + 1}/4`, 120, 61, 12);
    }
    this.canvas.setAttribute('aria-label', `Preset editor slot ${draft.id}. ${labels[page]}: ${draft[field]}. ${input ? `${field} keypad. Input ${input.text || 'empty'}. OK or Cancel this value; swipe up cancels this entry.` : 'Swipe left/right through fields; up cancels. Whole-preset Save or Cancel.'} ${field === 'pedal_dip_compensation' ? `Dip ${draft.dip_included ? 'included' : 'omitted'}.` : ''} ${notice}`);
    return true;
  }
  tap(view: WatchPresetView, x: number, y: number): void {
    const target = this.targets(view).find(t => x >= t.x && x <= t.x + t.width && y >= t.y && y <= t.y + t.height);
    if (target) void this.enqueue(target.action, {editor_id: view.preset_editor?.id, entry_id: view.preset_input?.id, ...target.payload});
  }
}
