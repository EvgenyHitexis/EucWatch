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
  kind: 'preset' | 'editor';
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
  preset_input: null | { field: Field; text: string; letters: number; lowercase: boolean };
  preset_attempt: PresetOperation | null;
  config: { presets: Preset[] };
  persistence_error: string | null;
}
type Field = 'name' | 'pedal_sensitivity' | 'dynamic_assist' | 'pedal_dip_compensation';
const fields: Field[] = ['name', 'pedal_sensitivity', 'dynamic_assist', 'pedal_dip_compensation'];
const labels = ['Name', 'Pedal sensitivity', 'Dynamic assist', 'Pedal dip compensation'];

export class WatchPresets {
  constructor(private ctx: CanvasRenderingContext2D, private canvas: HTMLCanvasElement,
              private enqueue: (action: string, payload?: Record<string, unknown>) => Promise<unknown>) {}
  private text(value: string, x: number, y: number, size = 14): void {
    this.ctx.fillStyle = '#ffffff'; this.ctx.font = `${size}px sans-serif`;
    this.ctx.textAlign = 'center'; this.ctx.fillText(value, x, y, 216);
  }
  private button(value: string, x: number, y: number, width: number, height = 30): void {
    this.ctx.strokeStyle = '#ffffff'; this.ctx.strokeRect(x, y, width, height);
    this.text(value, x + width / 2, y + height / 2 + 5);
  }
  private keys(input: NonNullable<WatchPresetView['preset_input']>): string[] {
    if (input.field !== 'name') return ['1','2','3','4','5','6','7','8','9','Clear','0','<'];
    const text = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.slice(input.letters * 12, input.letters * 12 + 12);
    return Array.from(input.lowercase ? text.toLowerCase() : text);
  }
  render(view: WatchPresetView, error: string, available: boolean): boolean {
    if (view.screen === 'preset_slots') {
      this.text('SETTINGS · PRESETS', 120, 22);
      view.config.presets.forEach((slot, index) => this.button(`${slot.id} · ${slot.name}`, 12, 36 + index * 44, 216, 38));
      this.text((view.persistence_error || error || 'Tap to edit · swipe up to return').slice(0, 34), 120, 231, 11);
      this.canvas.setAttribute('aria-label', `Settings Presets. ${view.config.presets.map(slot => `Slot ${slot.id}: ${slot.name}, configured`).join('; ')}. Swipe up to Settings. ${view.persistence_error ?? error}`);
      return true;
    }
    if (view.screen !== 'preset_editor' || !view.preset_draft || !view.preset_editor) return false;
    const draft = view.preset_draft, page = view.preset_page, field = fields[page], input = view.preset_input;
    const notice = !available ? 'Application unavailable' : view.preset_editor.reason || view.persistence_error || error;
    this.text(`‹ ${labels[page]} ›`, 120, 20, 13);
    if (input) {
      this.text(input.text || '—', 120, 46, 20);
      this.keys(input).forEach((key, index) => this.button(key, 16 + index % 3 * 70, 59 + Math.floor(index / 3) * 31, 66, 28));
      if (input.field === 'name') {
        this.button('a/A', 12, 185, 42, 24); this.button('Space', 57, 185, 45, 24);
        this.button('Clear', 105, 185, 45, 24); this.button('<', 153, 185, 30, 24);
        this.button(`${input.letters + 1}/3`, 186, 185, 42, 24);
      }
      if (input.field === 'pedal_dip_compensation') this.button(draft.dip_included ? 'Dip included' : 'Dip omitted', 12, 185, 216, 24);
      // Feedback replaces the value line while input remains available for correction.
      if (notice) {
        const reason = notice.replace('Configuration save failed: ', 'Save failed: ');
        this.ctx.fillStyle = '#000000'; this.ctx.fillRect(0, 29, 240, 28);
        this.text(reason.slice(0, 35), 120, 40, 10); this.text(reason.slice(35, 70), 120, 53, 10);
      }
    } else {
      this.text(`SLOT ${draft.id} · ${page + 1}/4`, 120, 49, 14);
      this.button(String(draft[field]), 12, 65, 216, 38);
      if (field === 'pedal_dip_compensation') this.button(draft.dip_included ? 'Dip included' : 'Dip omitted', 12, 111, 216);
      this.text('Local draft · tap value to edit', 120, 158, 12);
      this.text(notice.slice(0, 38), 120, 194, 11);
    }
    this.button('Cancel', 12, 214, 104, 24); this.button('Save', 124, 214, 104, 24);
    this.canvas.setAttribute('aria-label', `Preset editor slot ${draft.id}. ${labels[page]}: ${draft[field]}. ${input ? `${field} keypad. Input ${input.text || 'empty'}.` : ''} Swipe left/right through fields; up cancels. ${field === 'pedal_dip_compensation' ? `Dip ${draft.dip_included ? 'included' : 'omitted'}.` : ''} Whole-editor Save or Cancel. ${notice}`);
    return true;
  }
  tap(view: WatchPresetView, x: number, y: number): void {
    const send = (action: string, payload: Record<string, unknown> = {}) => void this.enqueue(action, {editor_id: view.preset_editor?.id, ...payload});
    if (view.screen === 'preset_slots') {
      if (x >= 12 && x <= 228 && y >= 36 && y < 212 && (y - 36) % 44 <= 38) send('preset_begin', {slot: Math.floor((y - 36) / 44) + 1});
      return;
    }
    if (!view.preset_draft) return;
    if (y >= 214) { send(x < 120 ? 'preset_cancel' : 'preset_save'); return; }
    const page = view.preset_page, input = view.preset_input;
    if (y <= 28 && (x <= 62 || x >= 178)) { send('preset_page', {page: (page + (x < 120 ? 3 : 1)) % 4}); return; }
    if (input) {
      if (input.field === 'name' && y >= 185 && y <= 209) {
        if (x >= 186) send('preset_input_page', {delta: 1});
        else send('preset_input_key', {key: x < 54 ? 'a/A' : x < 102 ? ' ' : x < 150 ? 'Clear' : '<'});
      } else if (input.field === 'pedal_dip_compensation' && x >= 12 && x <= 228 && y >= 185 && y <= 209) {
        send('preset_include_dip', {included: !view.preset_draft.dip_included});
      } else if (x >= 16 && x < 222 && y >= 59 && y < 180) {
        const key = this.keys(input)[Math.floor((y - 59) / 31) * 3 + Math.floor((x - 16) / 70)];
        if (key) send('preset_input_key', {key});
      }
    } else if (y >= 65 && y <= 103) send('preset_input_begin');
    else if (fields[page] === 'pedal_dip_compensation' && y >= 111 && y <= 141) send('preset_include_dip', {included: !view.preset_draft.dip_included});
  }
}
