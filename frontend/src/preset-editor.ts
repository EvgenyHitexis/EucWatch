/** Watch-sized inputs shared by staging flows; completion is an explicit action. */
export interface Preset {
  id: number;
  name: string;
  configured: boolean;
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
  preset_editor: null | { slot: number; session: number; requested_s: number; status: string; reason: string; current_confirmation: boolean; wheel_values: Record<string, number | null> | null };
  preset_draft: Preset | null;
  preset_attempt: PresetOperation | null;
  config: { presets: Preset[] };
  persistence_error: string | null;
}
type Field = 'name' | 'pedal_sensitivity' | 'dynamic_assist' | 'pedal_dip_compensation';
const fields: Field[] = ['name', 'pedal_sensitivity', 'dynamic_assist', 'pedal_dip_compensation'];
const labels = ['Name', 'Pedal sensitivity', 'Dynamic assist', 'Pedal dip compensation'];

export class WatchPresets {
  private page = 0;
  private entry: string | null = null;
  private letters = 0;
  private lowercase = false;
  private clearSlot: number | null = null;
  private identity = '';
  constructor(private ctx: CanvasRenderingContext2D, private canvas: HTMLCanvasElement,
              private enqueue: (action: string, payload?: Record<string, unknown>) => Promise<unknown>) {}

  stateKey(): string { return JSON.stringify([this.page, this.entry, this.letters, this.lowercase, this.clearSlot]); }
  cancelInput(): boolean {
    if (this.entry === null && this.clearSlot === null) return false;
    this.entry = null;
    this.clearSlot = null;
    return true;
  }
  private text(value: string, x: number, y: number, size = 14): void {
    this.ctx.fillStyle = '#ffffff'; this.ctx.font = `${size}px sans-serif`;
    this.ctx.textAlign = 'center'; this.ctx.fillText(value, x, y, 216);
  }
  private button(value: string, x: number, y: number, width: number, height = 30): void {
    this.ctx.strokeStyle = '#ffffff'; this.ctx.strokeRect(x, y, width, height);
    this.text(value, x + width / 2, y + height / 2 + 5);
  }
  private keys(): string[] {
    if (fields[this.page] !== 'name') return ['1','2','3','4','5','6','7','8','9','Clear','0','⌫'];
    const characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.slice(this.letters * 12, this.letters * 12 + 12);
    return Array.from(this.lowercase ? characters.toLowerCase() : characters);
  }

  render(view: WatchPresetView, error: string, available: boolean): boolean {
    const identity = JSON.stringify([view.session, view.preset_editor?.slot, view.preset_editor?.requested_s, view.screen]);
    if (identity !== this.identity) {
      this.identity = identity; this.page = 0; this.entry = null; this.clearSlot = null;
    }
    if (this.clearSlot !== null && ['preset_slots', 'preset_editor'].includes(view.screen)) {
      this.text(`Clear slot ${this.clearSlot}?`, 120, 80, 20);
      this.text('Wheel values stay unchanged', 120, 115, 13);
      this.button('Cancel', 12, 174, 104); this.button('Clear', 124, 174, 104);
      this.canvas.setAttribute('aria-label', `Clear slot ${this.clearSlot}? Cancel or Clear. Wheel values stay unchanged. ${view.persistence_error ?? error}`);
      return true;
    }
    if (view.screen === 'preset_slots') {
      this.text('SETTINGS · PRESETS', 120, 22);
      view.config.presets.forEach((slot, index) => {
        const y = 36 + index * 44;
        this.button(`${slot.id} · ${slot.name}`, 12, y, 157, 38);
        this.button('Clear', 174, y, 54, 38);
      });
      this.text((view.persistence_error || error || 'Tap a slot to edit · ‹ Back').slice(0, 34), 120, 231, 11);
      this.canvas.setAttribute('aria-label', `Settings Presets. ${view.config.presets.map(slot => `Slot ${slot.id}: ${slot.name}, ${slot.configured ? 'configured' : 'unconfigured'}; edit or clear`).join('; ')}. Swipe right to Settings. ${view.persistence_error ?? error}`);
      return true;
    }
    if (view.screen !== 'preset_editor') return false;
    const editor = view.preset_editor;
    const draft = view.preset_draft;
    if (!editor || !draft) {
      this.text(`SLOT ${editor?.slot ?? '—'}`, 120, 25);
      this.text(editor?.status === 'waiting' ? 'Reading wheel settings…' : 'Settings unavailable', 120, 90, 17);
      this.text(editor?.status === 'waiting' ? 'Waiting for a new valid frame' : 'Reopen to read this session', 120, 124, 12);
      this.text((editor?.reason || error).slice(0, 36), 120, 156, 11);
      this.button('Back', 12, 202, 216);
      this.canvas.setAttribute('aria-label', `Preset editor slot ${editor?.slot}. ${editor?.status === 'waiting' ? 'Waiting for fresh wheel settings' : 'Settings unavailable'}. ${editor?.reason || error}. Back.`);
      return true;
    }
    const field = fields[this.page];
    if (this.entry !== null) {
      const name = field === 'name';
      this.text(name ? `‹ Letters ${this.letters + 1}/3 ›` : labels[this.page], 120, 21, 13);
      this.text(this.entry || '—', 120, 48, 20);
      this.keys().forEach((key, index) => this.button(key, 16 + index % 3 * 70, 59 + Math.floor(index / 3) * 31, 66, 28));
      if (name) { this.button('a/A', 12, 185, 50, 24); this.button('Space', 68, 185, 50, 24); this.button('Clear', 124, 185, 50, 24); this.button('⌫', 180, 185, 48, 24); }
      this.button('Cancel', 12, 214, 104, 24); this.button('Set', 124, 214, 104, 24);
      this.canvas.setAttribute('aria-label', `Preset ${field} keypad. Input ${this.entry || 'empty'}. ${name ? 'Paged letters and digits, a/A, Space, backspace' : 'Digits 0 through 9, Clear, backspace'}. Cancel or Set; Set completes the adjustment.`);
      return true;
    }
    this.text(`‹ SLOT ${draft.id} · ${this.page + 1}/4 ›`, 120, 22, 13);
    this.text(labels[this.page], 120, 50, 17);
    this.button(String(draft[field] ?? 'Omitted'), 12, 65, 216, 38);
    if (field === 'pedal_dip_compensation') this.button(draft[field] === undefined ? 'Include dip (local)' : 'Omit dip (local)', 12, 111, 216);
    const attempt = view.preset_attempt;
    const result = attempt?.kind === 'editor' && attempt.slot === draft.id ? attempt.fields[field] : undefined;
    this.text(result ? `Requested ${result.requested} · ${result.submitted_s === null ? 'submission pending' : 'submitted'}` : 'Tap value to edit', 120, 155, 12);
    const wheelValue = editor.wheel_values?.[field];
    const confirmation = editor.current_confirmation ? 'confirmed' : attempt?.status === 'Confirmed' ? 'confirmation lost' : result?.state ?? 'unknown';
    this.text(result ? `Wheel ${wheelValue ?? 'unknown'} · ${confirmation}` : field === 'name' ? 'Name stays local' : 'Set writes directly to wheel', 120, 176, 12);
    const notice = !available ? 'Application unavailable' : view.persistence_error || error || (attempt?.kind === 'editor' && attempt.slot === draft.id ? attempt.pending ? 'Applying · wait' : attempt.reason || (attempt.status === 'Confirmed' && !editor.current_confirmation ? 'Previous Confirmed · now unknown' : attempt.status) : '');
    this.text(notice.slice(0, 36), 120, 197, 11);
    this.button('Back', 12, 207, 64);
    this.button(view.persistence_error ? 'Retry save' : 'Save slot', 82, 207, 98);
    this.button('Clear', 186, 207, 42);
    this.canvas.setAttribute('aria-label', `Preset editor slot ${draft.id}. ${labels[this.page]}: ${draft[field] ?? 'omitted'}. Previous and next field. Tap value for input. ${result ? `Requested ${result.requested}; ${result.submitted_s === null ? 'not submitted' : 'submitted'}; latest wheel ${wheelValue ?? 'unknown'} ${confirmation}.` : ''} ${field === 'pedal_dip_compensation' ? 'Include or omit dip locally.' : ''} Back, Save slot locally, Clear. ${notice}. Submitted wheel changes are not undone by leaving.`);
    return true;
  }

  tap(view: WatchPresetView, x: number, y: number): void {
    if (this.clearSlot !== null) {
      if (y >= 174 && y <= 204) {
        if (x >= 124) void this.enqueue('preset_clear', {slot: this.clearSlot});
        this.clearSlot = null;
      }
      return;
    }
    if (view.screen === 'preset_slots') {
      if (x >= 12 && x <= 228 && y >= 36 && y < 212) {
        const slot = Math.floor((y - 36) / 44) + 1;
        if ((y - 36) % 44 <= 38) {
          if (x >= 174) this.clearSlot = slot;
          else if (x <= 169) void this.enqueue('preset_begin', {slot, source: 'watch'});
        }
      }
      return;
    }
    if (!view.preset_draft) { if (y >= 202) void this.enqueue('preset_cancel'); return; }
    const field = fields[this.page];
    const name = field === 'name';
    if (this.entry !== null) {
      if (y >= 214) {
        const value = this.entry;
        this.entry = null;
        if (x >= 124) {
          if (!name && !/^\d{1,3}$/.test(value)) return;
          void this.enqueue('preset_update', {[field]: name ? value : Number(value), source: 'watch'});
        }
      } else if (name && y <= 28) this.letters = (this.letters + (x < 120 ? 2 : 1)) % 3;
      else if (name && y >= 185 && y <= 209) {
        if (x < 62) this.lowercase = !this.lowercase;
        else if (x < 118 && this.entry.length < 24) this.entry += ' ';
        else if (x >= 124 && x < 174) this.entry = '';
        else if (x >= 180) this.entry = this.entry.slice(0, -1);
      } else if (x >= 16 && x < 222 && y >= 59 && y < 180) {
        const key = this.keys()[Math.floor((y - 59) / 31) * 3 + Math.floor((x - 16) / 70)];
        if (key === 'Clear') this.entry = '';
        else if (key === '⌫') this.entry = this.entry.slice(0, -1);
        else if (key && this.entry.length < (name ? 24 : 3)) this.entry += key;
      }
      return;
    }
    if (view.preset_attempt?.pending) { if (y >= 207 && x <= 76) void this.enqueue('preset_cancel'); return; }
    if (y <= 30) this.page = (this.page + (x < 120 ? 3 : 1)) % 4;
    else if (y >= 65 && y <= 103) {
      this.entry = name ? view.preset_draft.name : '';
      this.letters = 0;
    } else if (field === 'pedal_dip_compensation' && y >= 111 && y <= 141) {
      void this.enqueue('preset_include_dip', {included: view.preset_draft[field] === undefined});
    } else if (y >= 207) {
      if (x <= 76) void this.enqueue('preset_cancel');
      else if (x <= 180) void this.enqueue('preset_save');
      else this.clearSlot = view.preset_draft.id;
    }
  }
}
