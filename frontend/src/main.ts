import './style.css';
import { mountScenarios, type ScenarioView } from './scenarios';
import { mountBackup } from './backup';
import { WatchPresets, type Preset, type PresetOperation, type WatchPresetView } from './preset-editor';

interface Dashboard {
  speed: string;
  pwm: string;
  wheel_battery_percent: string;
  average_cell_voltage: string;
  wheel_battery_dimmed: boolean;
  watch_battery_percent: string;
  watch_battery_simulated: boolean;
  connection: string;
}
type AlertName = 'pwm' | 'speed' | 'battery' | 'lost';
interface MeasurementAlert { enabled: boolean; threshold: number | null }
interface AlertSettings {
  pwm: MeasurementAlert;
  speed: MeasurementAlert;
  battery: MeasurementAlert;
  lost: { enabled: boolean };
}
interface PresetMenuSlot { id: number; name: string; configured: boolean; available: boolean; revision: number }
interface LiveStatus {
  devices: { address: string; name: string; rssi: number; service_uuids: string[] }[];
  selected: string | null;
  link: string;
  error: string | null;
  firmware: string | null;
  notifications: number;
  valid_frames: number;
  rejected_frames: number;
  disconnects: number;
  reconnections: number;
  notification_rate_hz: number | null;
  maximum_notification_gap_s: number;
  maximum_frame_gap_s: number;
  provenance: string;
}
// The alert editor view is Python's; the Canvas only draws it and forwards touches.
interface AlertEditorView {
  page: number;
  previous_page: number;
  next_page: number;
  alert: AlertName;
  label: string;
  unit: string;
  enabled: boolean;
  toggle_label: string;
  threshold: string | null;
  threshold_label: string | null;
  note: string | null;
  reason: string;
  entry: null | { alert: AlertName; label: string; unit: string; text: string; display: string; notice: string };
  keys: { key: string; label: string }[];
}
// Each alert's display name, threshold unit and highest saved threshold (null without a threshold), from Python.
type AlertDefinitions = Record<AlertName, { label: string; unit: string; limit: number | null }>;
const alertNames: AlertName[] = ['pwm', 'speed', 'battery', 'lost'];
interface View extends WatchPresetView {
  mode: string;
  controlled: boolean;
  session: number;
  elapsed_s: number;
  connected: boolean;
  fresh: boolean;
  screen: 'dashboard' | 'presets' | 'settings' | 'preset_slots' | 'preset_editor';
  scenario: ScenarioView;
  awake: boolean;
  button: { down: boolean; wake_cycle: boolean };
  recovery: boolean;
  horn_feedback: null | {message:string};
  established_connection: boolean;
  recording: { path: string; queued: number; written: number; rejected: number; error: string | null; closed: boolean } | null;
  replay: { name: string; sha256: string; source: string; total: number; position: number; finished: boolean } | null;
  config: { version: number; revision: number; alerts: AlertSettings; presets: Preset[] };
  alerts_draft: AlertSettings | null;
  alert_editor: AlertEditorView | null;
  alert_definitions: AlertDefinitions;
  preset_draft: WatchPresetView['preset_draft'];
  presets_menu: PresetMenuSlot[];
  configuration_preview: null | { content: unknown; base_revision:number; migration:{from:number;to:number;changes:string[]} };
  configuration_export: unknown;
  preset_attempt: PresetOperation | null;
  confirmed_preset: null | { name: string };
  live: LiveStatus | null;
  persistence_error: string | null;
  vibration: {
    simulated: boolean;
    current: { alert: AlertName; test: boolean; started_s: number; duration_s: number } | null;
    events: { alert: AlertName; test: boolean; phase: 'start' | 'stop'; at_s: number; duration_s: number }[];
    queued: AlertName[];
  };
  dashboard: Dashboard;
  simulator: {
    speed_kmh: number;
    voltage_V: number;
    pwm_percent: number;
    watch_battery_percent: number;
    traffic: string;
    frame_length: number;
    fragment_size: number;
  };
  diagnostics: { valid_frames: number; rejected_frames: number; resume_events: number };
}
interface Session { credential: string; controller: string | null }

document.querySelector<HTMLDivElement>('#app')!.innerHTML = `
  <main class="shell">
    <header class="masthead">
      <div><p class="eyebrow">Dedicated riding application</p><h1>Sherman L</h1></div>
      <span class="mode" id="mode">Starting application</span>
    </header>
    <div class="workspace">
      <section class="watch-area" aria-label="Watch interface">
        <div class="watch"><canvas id="watch" width="240" height="240" role="img" aria-label="Connecting to application"></canvas><button class="side-button" id="watch-button" aria-label="Watch physical button" disabled></button></div>
        <p class="watch-caption">Riding dashboard · 240 × 240</p>
        <p class="watch-note">Swipe left for presets, down from the top for Settings.<br>Swipe up to leave Settings; left/right change preset fields.<br>Swipe right from riding presets to return. Side button wakes the screen.<br>Watch battery is simulated.</p>
        <p id="watch-feedback" role="status"></p>
      </section>
      <section class="panel" aria-labelledby="scenario-title">
        <h2 id="scenario-title">Wheel simulator</h2>
        <p class="intro">Protocol-shaped notifications pass through the application's real parser. Start a simulator session explicitly, then choose readings and failure scenarios.</p>
        <p class="status" id="backend-status" role="status">Connecting to application…</p>
        <div class="actions"><button id="start" class="primary" data-action="simulator_start" data-control>Start simulator</button><button id="stop" data-action="stop" data-control>End session</button></div>
        <label class="check"><input type="checkbox" id="controlled" checked>Controlled time (advance explicitly)</label>
        <div class="divider"></div>
        <form id="scenario">
          <div class="fields">
            <label>Speed (km/h)<input id="speed" type="number" min="0" max="150" step="0.1" value="25" required></label>
            <label>Pack voltage (V)<input id="voltage" type="number" min="0" max="200" step="0.01" value="138" required></label>
            <label>PWM (%)<input id="pwm" type="number" min="0" max="100" step="0.1" value="45" required></label>
          </div>
          <div class="fields" style="margin-top:16px">
            <label>Frame length<select id="length"><option>75</option><option>77</option><option selected>87</option><option>99</option></select></label>
            <label>Fragment size (bytes)<input id="fragment" type="number" min="1" max="99" value="20" required></label>
            <label>Watch battery (%)<input id="watch-battery" type="number" min="0" max="100" value="80" required></label>
          </div>
          <label style="margin-top:16px">Notification traffic<select id="traffic"><option value="normal">Normal</option><option value="paused">Paused (no valid readings)</option><option value="corrupt">Corrupt CRC</option></select></label>
          <div class="fields" style="margin-top:16px">
            <label>Setting submission<select id="control-submission"><option value="normal">Normal</option><option value="fail">Fail between writes</option><option value="hang">No completion</option></select></label>
            <label>Fail after write<input id="control-fail-after" type="number" min="0" max="3" value="1"></label>
            <label>Submission delay (s)<input id="control-submission-delay" type="number" min="0" max="30" value="0" step="0.1"></label>
          </div>
          <div class="fields" style="margin-top:16px">
            <label>Settings readback<select id="control-readback"><option value="normal">Matching</option><option value="missing">Missing</option><option value="mismatch">Mismatching</option><option value="partial">Only some match</option></select></label>
            <label>Readback delay (s)<input id="control-readback-delay" type="number" min="0" max="30" value="0" step="0.1"></label>
          </div>
          <div class="actions"><button type="submit" class="primary" data-action="simulator_configure" data-simulator>Send simulator readings</button><button type="button" id="emit" data-action="simulator_emit" data-simulator>Emit another frame</button></div>
        </form>
        <label>Advance elapsed time (s)<input id="advance-seconds" type="number" min="0" max="3600" step="0.1" value="1.1"></label>
        <div class="actions"><button id="advance" data-action="advance" data-simulator>Advance time</button><button id="disconnect" data-action="disconnect" data-simulator>Disconnect</button><button id="connect" data-action="connect" data-simulator>Reconnect</button></div>
        <p class="messages" id="message" role="alert"></p>
        <div class="divider"></div>
        <div class="metadata" id="diagnostics">Session not started.</div>
        <p class="metadata">Simulator results establish software behavior. Physical wheel and watch acceptance remains separate.</p>
        <p id="preset-outcome" role="status">No preset requested.</p>
        <pre class="metadata" id="preset-field-results"></pre>
        <div class="divider"></div>
        <h2>Session recording</h2>
        <p class="metadata" id="recording-status">Recording status unavailable.</p>
        <p class="messages" id="recording-error" role="alert"></p>
        <button id="recording-download" data-action="recording_download" disabled>Download recording</button>
        <div class="divider"></div>
        <h2>Read-only replay</h2>
        <p class="intro">Load a versioned JSONL recording to reproduce its notification boundaries and time gaps. Replay cannot submit wheel commands.</p>
        <label>Recording file<input id="replay-file" type="file" accept=".jsonl,application/json,application/x-ndjson"></label>
        <div class="actions"><button id="replay-load" data-action="replay_start" data-control>Load replay</button><button id="replay-step" data-action="replay_step" disabled>Step one event</button></div>
        <p class="metadata" id="replay-progress">No replay loaded.</p>
        <p class="metadata replay-provenance" id="replay-provenance"></p>
        <div class="divider"></div>
        <h2>Live Sherman L connection</h2>
        <p class="intro">Discover Bluetooth devices explicitly, then select your wheel. The backend uses ordinary-user BlueZ/Bleak; this panel does not use browser Bluetooth.</p>
        <button id="live-discover" data-action="live_discover" data-control>Discover devices</button>
        <label style="margin-top:16px">Discovered device<select id="live-device"><option value="">Discover devices first</option></select></label>
        <div class="actions"><button id="live-select" data-action="live_select" data-control>Connect selected wheel</button><button id="live-disconnect" data-action="live_disconnect" data-control>Disconnect live wheel</button></div>
        <p class="metadata" id="live-status">Live transport is not active.</p>
        <p class="messages" id="live-error" role="alert"></p>
        <p class="metadata" id="live-diagnostics"></p>
        <p class="metadata" id="live-provenance">Physical live evidence remains pending until observed.</p>
        <div class="divider"></div>
        <h2>Vibration alerts</h2>
        <p class="intro">Edit the saved alert settings here or in watch Settings. Changes require Save; Cancel and watch back-navigation discard the draft.</p>
        <button id="alerts-edit" data-action="alerts_begin" data-control>Edit alerts</button>
        <form id="alerts-editor">
          ${alertNames.map(name => `<div class="alert-row"><label class="check"><input id="alert-${name}-enabled" type="checkbox"><span id="alert-${name}-label"></span></label>${name === 'lost' ? '<span class="metadata">One weak pulse per interruption</span>' : `<label>Threshold (<span id="alert-${name}-unit"></span>)<input id="alert-${name}-threshold" type="number" min="0" step="any" placeholder="Not configured"></label>`}<button type="button" data-alert-test="${name}" data-control>Test pattern</button></div>`).join('')}
          <div class="actions"><button type="submit" id="alerts-save" data-action="alerts_save" class="primary">Save alerts</button><button type="button" id="alerts-cancel" data-action="alerts_cancel">Cancel</button></div>
        </form>
        <p class="metadata" id="alerts-status">Loading saved settings…</p>
        <p class="messages" id="persistence-error" role="alert"></p>
        <div class="vibration-output"><p id="vibration-status" role="status">Simulated vibration output · idle</p><pre id="vibration-trace" aria-label="Timestamped simulated vibration pulse trace"></pre></div>
        <p class="metadata">Pulse traces establish software timing. Physical vibration effectiveness requires watch acceptance.</p>
        <div class="divider"></div>
        <h2>Riding presets</h2>
        <p class="intro">Edit all four saved presets locally through watch Settings → Presets, without a wheel connection. Keypad OK accepts one value into the unsaved draft; keypad Cancel discards only that entry. Close the keypad before changing fields. Save stores the whole preset; Cancel on a field display discards the whole draft.</p>
        <p class="metadata">Only choosing a preset in the riding menu applies its saved included values to the wheel. Saving locally is separate from wheel confirmation. Replay cannot send wheel commands.</p>
      </section>
    </div>
  </main>`;

const canvas = document.querySelector<HTMLCanvasElement>('#watch')!;
const ctx = canvas.getContext('2d')!;
const watchPresets = new WatchPresets(ctx, canvas, (name, payload) => enqueueWatch(name, payload));
const status = document.querySelector<HTMLElement>('#backend-status')!;
const message = document.querySelector<HTMLElement>('#message')!;
let session: Session | null = null;
let current: View | null = null;
let available = false;
let submitting = false;
let loadingReplay = false;
let replayLoadGeneration = 0;
// The refusal of an alert editor request that never reached the Application (transport, lease, session): the
// editor's own refusals arrive as its reason in the view.
let undeliveredAlertError = '';
let presetError = '';
const documentId = crypto.randomUUID();
let liveError = '';
let discoveredDevices = '';
let rendered = '';
const controllerStorageKey = 'sherman-l-controller';
let readGeneration = 0;
let acquiringSession: Promise<Session> | null = null;

function storedController(): string | null {
  try { return sessionStorage.getItem(controllerStorageKey); } catch { return null; }
}

async function acquireSession(): Promise<Session> {
  if (!acquiringSession) {
    const token = storedController();
    const query = token ? `?controller=${encodeURIComponent(token)}` : '';
    acquiringSession = read<Session>(`/api/session${query}${query ? '&' : '?'}document=${encodeURIComponent(documentId)}`).then(result => {
      if (result.controller) {
        try { sessionStorage.setItem(controllerStorageKey, result.controller); } catch { /* Storage is optional. */ }
      }
      return result;
    }).finally(() => { acquiringSession = null; });
  }
  return acquiringSession;
}

function setControls(): void {
  document.querySelector<HTMLButtonElement>('#watch-button')!.disabled = !available || !session?.controller;
  document.querySelectorAll<HTMLButtonElement>('[data-control]').forEach(button => {
    button.disabled = !available || !session?.controller || submitting;
  });
  document.querySelectorAll<HTMLButtonElement>('[data-simulator]').forEach(button => {
    button.disabled = !available || !session?.controller || submitting || current?.mode !== 'simulator';
  });
  document.querySelector<HTMLButtonElement>('#advance')!.disabled = !available || !session?.controller || submitting || !current?.controlled || current.mode !== 'simulator';
  document.querySelector<HTMLButtonElement>('#replay-load')!.disabled ||= loadingReplay;
  document.querySelector<HTMLButtonElement>('#replay-step')!.disabled = !available || !session?.controller || submitting || current?.mode !== 'replay' || !current.replay || current.replay.finished;
  document.querySelector<HTMLButtonElement>('#recording-download')!.disabled = !available || !session?.credential || !current?.recording;
  const editable = available && !!session?.controller && !submitting && !!current?.alerts_draft;
  document.querySelectorAll<HTMLInputElement>('#alerts-editor input').forEach(input => { input.disabled = !editable; });
  document.querySelector<HTMLButtonElement>('#alerts-save')!.disabled = !editable;
  document.querySelector<HTMLButtonElement>('#alerts-cancel')!.disabled = !editable;
  document.querySelector<HTMLButtonElement>('#live-discover')!.disabled ||= !current?.live || (current?.mode === 'live' && current.connected);
  document.querySelector<HTMLButtonElement>('#live-select')!.disabled ||= !current?.live || !document.querySelector<HTMLSelectElement>('#live-device')!.value;
  document.querySelector<HTMLButtonElement>('#live-disconnect')!.disabled ||= !current?.live || current.mode !== 'live';
  document.querySelector<HTMLSelectElement>('#live-device')!.disabled = !available || submitting || !current?.live?.devices.length;
  updateBackup(!submitting && available && !!session?.controller);
  updateScenarios(!submitting && available && !!session?.controller);
}

function text(value: string, x: number, y: number, size: number, color = '#ffffff', align: CanvasTextAlign = 'left'): void {
  ctx.fillStyle = color;
  ctx.font = `${size >= 22 ? 'bold ' : ''}${size}px sans-serif`;
  ctx.textAlign = align;
  ctx.fillText(value, x, y);
}

const settingsButtons = [
  { label: 'Sleep screen', top: 44, action: 'sleep' },
  { label: 'Vibration alerts', top: 108, action: 'alerts_begin' },
  { label: 'Presets', top: 172, action: 'preset_slots' },
];
const settingsButtonHeight = 56;
const ridingRects: Rect[] = Array.from({length: 4}, (_, index) => {
  const x = 9 + index % 2 * 115, y = 36 + Math.floor(index / 2) * 98;
  return [x, y, x + 106, y + 90];
});

function render(view: View | null): void {
  const key = JSON.stringify([view, available, undeliveredAlertError, presetError, liveError]);
  if (key === rendered) return;
  rendered = key;
  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, 240, 240);
  const screen = view?.screen ?? 'dashboard';
  document.querySelector<HTMLElement>('#watch-feedback')!.textContent=view?.horn_feedback?.message ?? '';
  const awake = view?.awake ?? true;
  canvas.dataset.screen = screen;
  canvas.dataset.awake = String(awake);
  canvas.dataset.fresh = String(!!view?.fresh && available);
  canvas.dataset.elapsed = String(view?.elapsed_s ?? 0);
  document.querySelector<HTMLElement>('#mode')!.textContent = view?.mode === 'simulator' ? 'SIMULATOR' : view?.mode === 'replay' ? 'READ-ONLY REPLAY' : view?.mode === 'live' ? 'LIVE WHEEL' : 'IDLE · NO WHEEL';
  if (view) document.querySelector<HTMLElement>('#diagnostics')!.textContent = `Session ${view.session} · Valid frames: ${view.diagnostics.valid_frames} · CRC/format rejects: ${view.diagnostics.rejected_frames} · Resume events: ${view.diagnostics.resume_events}`;
  const outcome=view?.preset_attempt;
  document.querySelector<HTMLElement>('#preset-outcome')!.textContent=outcome ? `${outcome.name} · ${outcome.pending ? 'Applying' : outcome.kind==='preset' && outcome.status==='Confirmed' && !view?.confirmed_preset ? 'Previous result Confirmed; current confirmation lost' : outcome.status}${outcome.reason ? ` · ${outcome.reason}` : ''}${!outcome.pending && (outcome.status!=='Confirmed' || (outcome.kind==='preset' && !view?.confirmed_preset)) ? ' · Some settings may have changed; the previous preset is not assured.' : ''}` : 'No preset requested.';
  document.querySelector<HTMLElement>('#preset-field-results')!.textContent=outcome ? Object.entries(outcome.fields).map(([field,result])=>`${field.replaceAll('_',' ')}: requested ${result.requested}, ${result.submitted_s === null ? 'not submitted' : 'submitted'}, actual ${result.actual ?? 'unknown'} · ${result.state}`).join('\n')+`\nRequested ${outcome.requested_s.toFixed(3)} s · submission ${outcome.submitted_s===null ? 'incomplete' : outcome.submitted_s.toFixed(3)+' s'}` : '';
  const recording = view?.recording;
  document.querySelector<HTMLElement>('#recording-status')!.textContent = recording ? `${recording.closed ? 'Closed recording' : 'Recording'} · ${recording.written} events written · ${recording.queued} queued · ${recording.rejected} rejected${!available ? ' · last known status' : ''}` : 'Recording is not enabled for this application session.';
  document.querySelector<HTMLElement>('#recording-error')!.textContent = recording?.error ? `Recording failure: ${recording.error}` : '';
  const replay = view?.replay;
  document.querySelector<HTMLElement>('#replay-progress')!.textContent = replay ? `${replay.finished ? 'Replay finished' : 'Read-only replay'} · ${replay.position} / ${replay.total} events · elapsed ${(view?.elapsed_s ?? 0).toFixed(2)} s` : 'No replay loaded.';
  document.querySelector<HTMLElement>('#replay-provenance')!.textContent = replay ? `${replay.name} · Source: ${replay.source} · SHA-256: ${replay.sha256}` : '';
  const live = view?.live;
  const devices = JSON.stringify(live?.devices ?? []);
  if (devices !== discoveredDevices) {
    discoveredDevices = devices;
    const select = document.querySelector<HTMLSelectElement>('#live-device')!;
    const selected = select.value;
    select.replaceChildren(new Option(live?.devices.length ? 'Select your wheel' : 'No discovered devices', ''));
    for (const device of live?.devices ?? []) select.add(new Option(`${device.name} · ${device.address} · ${device.rssi} dBm`, device.address));
    if (Array.from(select.options).some(option => option.value === selected)) select.value = selected;
    else if (live?.selected && Array.from(select.options).some(option => option.value === live.selected)) select.value = live.selected;
    setControls();
  }
  document.querySelector<HTMLElement>('#live-status')!.textContent = live ? `Live transport: ${live.link}${live.selected ? ` · ${live.selected}` : ''} · ${live.firmware ? `CRC-valid Sherman L telemetry · firmware ${live.firmware}` : 'Wheel identity pending valid telemetry'}` : 'Live transport is unavailable in this application session.';
  document.querySelector<HTMLElement>('#live-error')!.textContent = liveError || live?.error || '';
  document.querySelector<HTMLElement>('#live-diagnostics')!.textContent = live ? `${live.notifications} notifications · ${live.valid_frames} valid frames · ${live.rejected_frames} rejects · ${live.notification_rate_hz === null ? 'Cadence pending' : `${live.notification_rate_hz.toFixed(2)} notifications/s`} · max notification gap ${live.maximum_notification_gap_s.toFixed(3)} s · max frame gap ${live.maximum_frame_gap_s.toFixed(3)} s · ${live.disconnects} disconnects · ${live.reconnections} reconnections` : '';
  document.querySelector<HTMLElement>('#live-provenance')!.textContent = live?.provenance ?? 'Physical live evidence remains pending until observed.';
  const definitions = view?.alert_definitions;
  if (definitions) {
    for (const name of alertNames) {
      document.querySelector<HTMLElement>(`#alert-${name}-label`)!.textContent = definitions[name].label;
      const limit = definitions[name].limit;
      if (limit !== null) {
        document.querySelector<HTMLElement>(`#alert-${name}-unit`)!.textContent = definitions[name].unit;
        document.querySelector<HTMLInputElement>(`#alert-${name}-threshold`)!.max = String(limit);
      }
    }
  }
  const alertLabel = (name: AlertName): string => definitions?.[name].label ?? name;
  const alerts = view?.alerts_draft ?? view?.config?.alerts;
  if (alerts) {
    for (const name of alertNames) {
      const enabled = document.querySelector<HTMLInputElement>(`#alert-${name}-enabled`)!;
      if (document.activeElement !== enabled) enabled.checked = alerts[name].enabled;
      if (name !== 'lost') {
        const input = document.querySelector<HTMLInputElement>(`#alert-${name}-threshold`)!;
        if (document.activeElement !== input) input.value = alerts[name].threshold === null ? '' : String(alerts[name].threshold);
      }
    }
    document.querySelector<HTMLElement>('#alerts-status')!.textContent = view?.alerts_draft ? 'Unsaved draft · Save or Cancel explicitly' : `Saved alert settings · revision ${view?.config?.revision}`;
  }
  document.querySelector<HTMLElement>('#persistence-error')!.textContent = view?.persistence_error ? `Configuration could not be saved: ${view.persistence_error}` : '';
  const vibration = view?.vibration;
  const vibrationStatus = document.querySelector<HTMLElement>('#vibration-status')!;
  vibrationStatus.textContent = vibration?.current ? `Simulated vibration · ${alertLabel(vibration.current.alert)}${vibration.current.test ? ' test' : ''} · pulse ${vibration.current.duration_s * 1000} ms` : 'Simulated vibration output · idle';
  vibrationStatus.classList.toggle('active', !!vibration?.current);
  document.querySelector<HTMLElement>('#vibration-trace')!.textContent = vibration?.events.map(event => `${event.at_s.toFixed(3)} s · ${alertLabel(event.alert)}${event.test ? ' test' : ''} · ${event.phase} · ${event.duration_s * 1000} ms`).join('\n') ?? '';
  if (!awake) {
    canvas.setAttribute('aria-label', 'Screen asleep. Press the watch physical button to wake only.');
    return;
  }
  if (view?.recovery) {
    text('RECOVERY', 120, 108, 24, '#ffffff', 'center');
    text('Wheel controls unavailable', 120, 137, 12, '#ffffff', 'center');
    canvas.setAttribute('aria-label', 'Recovery mode. Wheel controls unavailable.');
    return;
  }
  if (view && watchPresets.render(view, presetError, available)) return;
  if (screen !== 'dashboard') {
    if (screen === 'settings' && view?.alert_editor) {
      renderWatchAlerts(view.alert_editor);
      return;
    }
    text(screen === 'presets' ? 'RIDING PRESETS' : 'SETTINGS', 120, 26, 15, '#ffffff', 'center');
    if (screen === 'presets') {
      for (let i = 0; i < 4; i++) {
        const [x, y, right, bottom] = ridingRects[i];
        const preset = view?.config?.presets[i];
        const color = preset?.configured ? '#ffffff' : '#777777';
        ctx.strokeStyle = color;
        ctx.strokeRect(x, y, right - x, bottom - y);
        drawPresetName(preset?.name ?? `Preset ${i + 1}`, x + 53, y + 42, color);
        const eligible = view?.presets_menu?.[i]?.available && available;
        if (!eligible) text(preset?.configured ? 'Unavailable' : 'Unconfigured', x + 53, y + 76, 10, color, 'center');
      }
      const names = (view?.config?.presets ?? [1, 2, 3, 4].map(id => ({ id, name: `Preset ${id}`, configured: false }))).map(preset => `slot ${preset.id}: ${preset.name}, ${preset.configured ? 'configured' : 'unconfigured'}`).join('; ');
      canvas.setAttribute('aria-label', `Preset menu. Four fixed slots: ${names}. ${view?.presets_menu?.some(slot=>slot.available) && available ? 'Tap one eligible slot to apply immediately.' : 'Application unavailable.'} Swipe right to return without applying.${view?.horn_feedback ? ` ${view.horn_feedback.message}` : ''}`);
    } else {
      ctx.strokeStyle = '#ffffff';
      for (const button of settingsButtons) {
        ctx.strokeRect(12, button.top, 216, settingsButtonHeight);
        text(button.label, 120, button.top + settingsButtonHeight / 2 + 6, 16, '#ffffff', 'center');
      }
      canvas.setAttribute('aria-label', 'Settings. Sleep screen. Vibration alerts. Presets. Swipe up to return without saving.'+(view?.horn_feedback ? ` ${view.horn_feedback.message}` : ''));
    }
    if (view?.horn_feedback) {
      ctx.fillStyle = '#000000'; ctx.fillRect(0, 0, 240, 32);
      text(view.horn_feedback.message, 120, 22, 11, '#ffffff', 'center');
    }
    return;
  }
  const d = view?.dashboard;
  const connected = !!view?.fresh && available;
  const muted = '#777777';
  text('SHERMAN L', 12, 21, 11);
  text(`W ${d?.watch_battery_percent ?? '—'}%`, 228, 21, 11, '#ffffff', 'right');
  ctx.strokeStyle = '#777777';
  ctx.strokeRect(190, 9, 10, 12);
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(193, 6, 4, 2);
  const speed = connected ? d!.speed : '—';
  const pwm = connected ? d!.pwm : '—';
  text(speed, 120, 99, 69, '#ffffff', 'center');
  text('km/h', 120, 121, 12, '#ffffff', 'center');
  const attempt=view?.preset_attempt;
  const presetFeedback=attempt ? `${attempt.name} · ${attempt.pending ? 'Applying' : attempt.status==='Confirmed' && !view?.confirmed_preset ? 'Unconfirmed' : attempt.status}` : '';
  if(view?.horn_feedback)text(view.horn_feedback.message,120,139,11,'#ffffff','center');
  else if(presetFeedback) text(presetFeedback,120,139,11,'#ffffff','center');
  text('PWM', 13, 161, 13);
  text(`${pwm}%`, 228, 164, 33, '#ffffff', 'right');
  ctx.fillStyle = '#777777';
  ctx.fillRect(12, 176, 216, 1);
  const batteryColor = d?.wheel_battery_dimmed || !available ? muted : '#ffffff';
  text(`${d?.wheel_battery_percent ?? '—'}% est.`, 12, 197, 18, batteryColor);
  text(`${d?.average_cell_voltage ?? '—'} V/cell`, 228, 197, 13, batteryColor, 'right');
  const connection = available ? (d?.connection ?? 'Not connected') : 'Application unavailable';
  if (!connected) { ctx.strokeStyle = '#ffffff'; ctx.strokeRect(8, 210, 224, 23); }
  text(connection, 120, 226, 12, '#ffffff', 'center');
  const summary = `Speed ${speed} km/h; PWM ${pwm} percent; estimated wheel battery ${d?.wheel_battery_percent ?? '—'} percent; average cell voltage ${d?.average_cell_voltage ?? '—'} volts; simulated watch battery ${d?.watch_battery_percent ?? '—'} percent; ${connection}${d?.wheel_battery_dimmed ? '; wheel battery dimmed' : ''}`;
  canvas.setAttribute('aria-label', summary+(presetFeedback ? `; ${presetFeedback}` : '')+(view?.horn_feedback ? `; ${view.horn_feedback.message}` : ''));
  canvas.dataset.fresh = String(connected);
  canvas.dataset.batteryDimmed = String(!!d?.wheel_battery_dimmed || !available);
}

async function read<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: 'no-store', signal: AbortSignal.timeout(1500) });
  if (!response.ok) throw new Error(`Application returned ${response.status}`);
  return response.json() as Promise<T>;
}

// A read started after this one supersedes it, and its answer is dropped. refresh() then resolves only when the
// superseding read has, so its caller (an action that just completed, say) never goes on with a view read before
// it called.
let latestRefresh: Promise<void> = Promise.resolve();

function refresh(): Promise<void> {
  const generation=++readGeneration;
  const settled=readState(generation).then(() => generation===readGeneration ? undefined : latestRefresh);
  latestRefresh=settled;
  return settled;
}

async function readState(generation: number): Promise<void> {
  try {
    if (!session?.controller) {
      const acquired=await acquireSession();
      if(generation!==readGeneration) return;
      session=acquired;
    }
    const owner=session;
    const query = session.controller && document.visibilityState === 'visible' ? `?controller=${encodeURIComponent(session.controller)}` : '';
    const view = await read<View>(`/api/state${query}`);
    if(generation!==readGeneration || owner!==session) return;
    current=view;
    available = true;
    status.textContent = session.controller ? 'Application ready' : 'Viewing only · another window controls this session';
    status.classList.remove('error');
  } catch {
    if(generation!==readGeneration) return;
    available = false;
    session = null;
    status.textContent = 'Application unavailable · controls disabled';
    status.classList.add('error');
  }
  setControls();
}

async function action(actionName: string, payload: Record<string, unknown> = {}): Promise<boolean> {
  if (!available || !session?.controller || submitting) return false;
  if (['simulator_start', 'stop', 'connect', 'replay_start', 'live_select', 'live_disconnect'].includes(actionName)) replayLoadGeneration++;
  submitting = true;
  setControls();
  message.textContent = '';
  if (alertEditorAction(actionName)) undeliveredAlertError = '';
  let delivered = false;
  if (actionName.startsWith('preset_')) presetError = '';
  if (actionName.startsWith('live_')) liveError = '';
  try {
    const response = await fetch('/api/action', {
      method: 'POST',
      signal: AbortSignal.timeout(actionName === 'live_discover' ? 10000 : actionName.startsWith('live_') ? 35000 : 1500),
      headers: { 'Content-Type': 'application/json', 'X-EucWatch-Key': session.credential },
      body: JSON.stringify({ id: crypto.randomUUID(), controller: session.controller, action: actionName, epoch:current?.session, ...payload }),
    });
    if (!response.ok) {
      if (response.status === 403) {
        session = null;
        available = false;
      }
      const result = await response.json() as { error?: string; refused_by?: string };
      delivered = result.refused_by === 'application';
      // The Application's refusal may have set the editor's reason: show it now, not at the next poll.
      if (delivered) await refresh();
      throw new Error(result.error ?? `Action refused (${response.status})`);
    }
    await refresh();
    return true;
  } catch (error) {
    message.textContent = error instanceof Error ? error.message : 'Action could not be sent';
    if (alertEditorAction(actionName) && !delivered) undeliveredAlertError = message.textContent;
    if (actionName.startsWith('preset_')) presetError = message.textContent;
    if (actionName.startsWith('live_')) liveError = message.textContent;
    return false;
  } finally {
    submitting = false;
    setControls();
  }
}

function number(id: string): number { return Number(document.querySelector<HTMLInputElement>(`#${id}`)!.value); }

function drawPresetName(name: string, x: number, y: number, color: string): void {
  ctx.font = '14px sans-serif';
  const characters = Array.from(name);
  let split = characters.length;
  while (split > 1 && ctx.measureText(characters.slice(0, split).join('')).width > 96) split--;
  text(characters.slice(0, split).join(''), x, y, 14, color, 'center');
  if (split < characters.length) {
    const second = characters.slice(split);
    let end = second.length;
    while (end > 0 && ctx.measureText(second.slice(0, end).join('') + (end < second.length ? '…' : '')).width > 96) end--;
    text(second.slice(0, end).join('') + (end < second.length ? '…' : ''), x, y + 17, 14, color, 'center');
  }
}

type Rect = readonly [number, number, number, number];
interface WatchInput { action: string; payload?: Record<string, unknown> }
const alertRects = {
  previous: [8, 0, 56, 44], next: [184, 0, 232, 44],
  toggle: [12, 52, 228, 92], decrease: [12, 100, 60, 140], threshold: [68, 100, 172, 140], increase: [180, 100, 228, 140],
  test: [12, 148, 228, 188], cancel: [12, 196, 116, 236], save: [124, 196, 228, 236],
} as const;
function thresholdKeyRect(index: number): Rect {
  const x = 12 + index % 3 * 74, y = 52 + Math.floor(index / 3) * 35;
  return [x, y, x + 68, y + 32];
}
function hit(rect: Rect, x: number, y: number): boolean { return x >= rect[0] && x <= rect[2] && y >= rect[1] && y <= rect[3]; }
function watchButton(rect: Rect, label: string, size = 16): void {
  ctx.strokeStyle = '#ffffff'; ctx.strokeRect(rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]);
  text(label, (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2 + size / 3, size, '#ffffff', 'center');
}
function alertEditorAction(actionName: string): boolean { return actionName.startsWith('alerts_') || actionName.startsWith('threshold_'); }
// The alert title stays above a message, wrapped at spaces into lines of at most width characters, as watch/render.js does.
function wrapLines(value: string, width: number, count: number): string[] {
  const lines: string[] = [];
  while (value && lines.length < count) {
    let cut = value.length <= width ? value.length : value.lastIndexOf(' ', width);
    if (cut <= 0) cut = width;
    lines.push(value.slice(0, cut));
    value = value.slice(cut).replace(/^ +/, '');
  }
  return lines;
}
function renderWatchAlerts(editor: AlertEditorView): void {
  const error = undeliveredAlertError || editor.reason || current?.persistence_error || '';
  const entry = editor.entry;
  if (entry) {
    // A refused Set value keeps the alert's name above the short notice, as watch/render.js does.
    const notice = entry.notice;
    text(entry.label, 120, notice ? 13 : 14, 12, '#ffffff', 'center');
    if (notice) text(notice, 120, 24, 10, '#ffffff', 'center');
    text(entry.display, 120, notice ? 46 : 39, 20, '#ffffff', 'center');
    editor.keys.forEach(({label}, index) => watchButton(thresholdKeyRect(index), label, 18));
    watchButton(alertRects.cancel, 'Cancel'); watchButton(alertRects.save, 'Set value');
    canvas.setAttribute('aria-label', `Watch threshold keypad. ${entry.label} threshold ${entry.text || 'empty'} ${entry.unit}. Digits 1 through 9, decimal point, 0, backspace. Cancel or Set value updates the unsaved draft.${notice ? ` Error: ${notice}` : ''}`);
    canvas.dataset.alert = entry.alert;
    return;
  }
  watchButton(alertRects.previous, '‹', 24); watchButton(alertRects.next, '›', 24);
  if (error) {
    text(editor.label, 120, 14, 12, '#ffffff', 'center');
    wrapLines(error, 23, 3).forEach((line, index) => text(line, 120, 26 + index * 11, 10, '#ffffff', 'center'));
  } else {
    text(editor.label, 120, 18, 12, '#ffffff', 'center');
    text(`${editor.page + 1}/4`, 120, 36, 12, '#ffffff', 'center');
  }
  watchButton(alertRects.toggle, editor.toggle_label);
  if (editor.threshold_label !== null) {
    watchButton(alertRects.decrease, '−', 22); watchButton(alertRects.increase, '+', 22);
    watchButton(alertRects.threshold, editor.threshold_label);
  } else text(editor.note ?? '', 120, 125, 14, '#ffffff', 'center');
  watchButton(alertRects.test, 'Test vibration');
  watchButton(alertRects.cancel, 'Cancel'); watchButton(alertRects.save, 'Save');
  const thresholdText = editor.threshold_label === null ? '' : `; threshold ${editor.threshold ?? 'not configured'} ${editor.unit}`;
  canvas.setAttribute('aria-label', `Alert editor ${editor.page + 1} of 4. ${editor.label}; ${editor.enabled ? 'enabled' : 'disabled'}${thresholdText}. Previous and next alert; toggle enabled; decrease or increase threshold or tap value for keypad; Test vibration pattern; Cancel; Save. Unsaved draft.${error ? ` Error: ${error}` : ''}`);
  canvas.dataset.alert = editor.alert;
}

// The touched control's action, read from the view the earlier touches produced.
function alertTarget(editor: AlertEditorView, x: number, y: number): WatchInput | null {
  if (editor.entry) {
    if (hit(alertRects.cancel, x, y)) return { action: 'threshold_cancel' };
    if (hit(alertRects.save, x, y)) return { action: 'threshold_done' };
    const index = editor.keys.findIndex((_, position) => hit(thresholdKeyRect(position), x, y));
    return index < 0 ? null : { action: 'threshold_key', payload: { key: editor.keys[index].key } };
  }
  const alert = editor.alert, measurement = editor.threshold_label !== null;
  if (hit(alertRects.previous, x, y)) return { action: 'alerts_page', payload: { page: editor.previous_page } };
  if (hit(alertRects.next, x, y)) return { action: 'alerts_page', payload: { page: editor.next_page } };
  if (hit(alertRects.toggle, x, y)) return { action: 'alerts_update', payload: { alert, enabled: !editor.enabled } };
  if (measurement && hit(alertRects.threshold, x, y)) return { action: 'threshold_begin', payload: { alert } };
  if (measurement && hit(alertRects.decrease, x, y)) return { action: 'alerts_adjust', payload: { alert, delta: -1 } };
  if (measurement && hit(alertRects.increase, x, y)) return { action: 'alerts_adjust', payload: { alert, delta: 1 } };
  if (hit(alertRects.test, x, y)) return { action: 'alert_test', payload: { alert } };
  if (hit(alertRects.cancel, x, y)) return { action: 'alerts_cancel' };
  if (hit(alertRects.save, x, y)) return { action: 'alerts_save' };
  return null;
}

document.querySelector('#alerts-edit')!.addEventListener('click', () => void action('alerts_begin'));
document.querySelector('#alerts-editor')!.addEventListener('submit', event => { event.preventDefault(); enqueueWatch('alerts_save'); });
document.querySelector('#alerts-cancel')!.addEventListener('click', () => { enqueueWatch('alerts_cancel'); });
document.querySelectorAll<HTMLButtonElement>('[data-alert-test]').forEach(button => { button.addEventListener('click', () => void action('alert_test', { alert: button.dataset.alertTest })); });
for (const name of alertNames) {
  const update = (): void => {
    const enabled = document.querySelector<HTMLInputElement>(`#alert-${name}-enabled`)!.checked;
    const threshold = name === 'lost' ? undefined : document.querySelector<HTMLInputElement>(`#alert-${name}-threshold`)!.value;
    enqueueWatch('alerts_update', { alert: name, enabled, ...(threshold === undefined ? {} : { threshold: threshold === '' ? null : Number(threshold) }) });
  };
  document.querySelector(`#alert-${name}-enabled`)!.addEventListener('change', update);
  if (name !== 'lost') document.querySelector(`#alert-${name}-threshold`)!.addEventListener('change', update);
}

document.querySelector('#start')!.addEventListener('click', () => void action('simulator_start', { controlled: document.querySelector<HTMLInputElement>('#controlled')!.checked }));
document.querySelector('#stop')!.addEventListener('click', () => void action('stop'));
document.querySelector('#scenario')!.addEventListener('submit', async event => {
  event.preventDefault();
  const configured = await action('simulator_configure', {
    speed_kmh: number('speed'), voltage_V: number('voltage'), pwm_percent: number('pwm'),
    watch_battery_percent: number('watch-battery'), frame_length: number('length'),
    fragment_size: number('fragment'), traffic: document.querySelector<HTMLSelectElement>('#traffic')!.value,
    control_submission:document.querySelector<HTMLSelectElement>('#control-submission')!.value,
    control_fail_after:number('control-fail-after'),control_submission_delay_s:number('control-submission-delay'),
    control_readback:document.querySelector<HTMLSelectElement>('#control-readback')!.value,control_delay_s:number('control-readback-delay'),
  });
  if (configured) await action('simulator_emit');
});
document.querySelector('#emit')!.addEventListener('click', () => void action('simulator_emit'));
document.querySelector('#advance')!.addEventListener('click', () => void action('advance', { seconds: number('advance-seconds') }));
document.querySelector('#disconnect')!.addEventListener('click', () => void action('disconnect'));
document.querySelector('#connect')!.addEventListener('click', () => void action('connect', { mode: 'simulator', controlled: document.querySelector<HTMLInputElement>('#controlled')!.checked }));
document.querySelector('#controlled')!.addEventListener('change', setControls);
document.querySelector('#live-discover')!.addEventListener('click', () => void action('live_discover'));
document.querySelector('#live-select')!.addEventListener('click', () => void action('live_select', { address: document.querySelector<HTMLSelectElement>('#live-device')!.value }));
document.querySelector('#live-disconnect')!.addEventListener('click', () => void action('live_disconnect'));
document.querySelector('#live-device')!.addEventListener('change', setControls);
document.querySelector('#replay-step')!.addEventListener('click', () => void action('replay_step'));
document.querySelector('#replay-load')!.addEventListener('click', async () => {
  const file = document.querySelector<HTMLInputElement>('#replay-file')!.files?.[0];
  if (!file) { message.textContent = 'Choose a JSONL recording before loading replay.'; return; }
  loadingReplay = true;
  setControls();
  const generation = replayLoadGeneration;
  const wheelSession = current?.session;
  const controller = session?.controller;
  const credential = session?.credential;
  try {
    const recording = await file.text();
    if (generation !== replayLoadGeneration || wheelSession !== current?.session || controller !== session?.controller || credential !== session?.credential) return;
    await action('replay_start', { recording, name: file.name });
  } catch (error) {
    message.textContent = error instanceof Error ? error.message : 'Could not read the selected recording.';
  } finally {
    loadingReplay = false;
    setControls();
  }
});
document.querySelector('#recording-download')!.addEventListener('click', async () => {
  if (!available || !session?.credential) return;
  try {
    const response = await fetch('/api/recording', { headers: { 'X-EucWatch-Key': session.credential }, cache: 'no-store', signal: AbortSignal.timeout(5000) });
    if (!response.ok) throw new Error(`Recording download unavailable (${response.status}).`);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = 'sherman-l-session.jsonl';
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    message.textContent = error instanceof Error ? error.message : 'Recording download failed.';
  }
});

function watchPoint(event: PointerEvent): { x: number; y: number } {
  const bounds = canvas.getBoundingClientRect();
  return { x: (event.clientX - bounds.left) * 240 / bounds.width, y: (event.clientY - bounds.top) * 240 / bounds.height };
}
let gesture: { x: number; y: number; pointer: number; editor_id?: number; entry_id?: number } | null = null;
canvas.addEventListener('pointerdown', event => {
  if (!available || !session?.controller || !current?.awake || current.recovery) return;
  gesture = { ...watchPoint(event), pointer: event.pointerId, editor_id: current.preset_editor?.id, entry_id: current.preset_input?.id };
  canvas.setPointerCapture(event.pointerId);
  enqueueWatch('interact');
});
canvas.addEventListener('pointerup', event => {
  if (!gesture || gesture.pointer !== event.pointerId) return;
  const start = gesture;
  gesture = null;
  if (start.editor_id !== current?.preset_editor?.id || start.entry_id !== current?.preset_input?.id) return;
  const end = watchPoint(event);
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  if (Math.abs(dx) >= 40 && Math.abs(dx) > Math.abs(dy)) {
    enqueueWatch('swipe', { direction: dx < 0 ? 'left' : 'right', from_top: start.y <= 45, editor_id: start.editor_id, entry_id: start.entry_id });
  } else if (Math.abs(dy) >= 40 && Math.abs(dy) > Math.abs(dx)) {
    enqueueWatch('swipe', { direction: dy < 0 ? 'up' : 'down', from_top: start.y <= 45, editor_id: start.editor_id, entry_id: start.entry_id });
  } else if (Math.abs(dx) < 12 && Math.abs(dy) < 12 && current && ['preset_slots', 'preset_editor'].includes(current.screen)) {
    watchPresets.tap(current, end.x, end.y);
  } else if (Math.abs(dx) < 12 && Math.abs(dy) < 12 && current?.screen === 'settings') {
    if (current.alert_editor) enqueueInput(() => current?.alert_editor ? alertTarget(current.alert_editor, end.x, end.y) : null);
    else if (end.x >= 12 && end.x <= 228) {
      const button = settingsButtons.find(item => end.y >= item.top && end.y <= item.top + settingsButtonHeight);
      if (button) enqueueWatch(button.action);
    }
  } else if (Math.abs(dx)<12 && Math.abs(dy)<12 && current?.screen==='presets') {
    const index = ridingRects.findIndex(rect => hit(rect, end.x, end.y));
    if (index >= 0 && current.presets_menu?.[index]?.available) enqueueWatch('preset_apply', {slot: index + 1});
  }
});
canvas.addEventListener('pointercancel', () => { gesture = null; });

const sideButton = document.querySelector<HTMLButtonElement>('#watch-button')!;
let buttonPointer: number | null = null;
let watchChain: Promise<unknown> = Promise.resolve();
let holdTimer: number | null = null;
let buttonCycleOpen = false;
let inputGeneration = 0;
const updateScenarios=mountScenarios(action,()=>current?.scenario ?? null,()=>JSON.stringify([inputGeneration,current?.session,session?.credential]));
const updateBackup=mountBackup(action,()=>current,()=>JSON.stringify([inputGeneration,current?.session,current?.config.revision,session?.credential]));
function enqueueWatch(actionName: string, payload: Record<string, unknown> = {}): Promise<unknown> {
  return enqueueInput(() => ({ action: actionName, payload }));
}
// Inputs run in order; each is resolved when its turn comes, after earlier inputs' views.
function enqueueInput(resolve: () => WatchInput | null): Promise<unknown> {
  const wheelSession = current?.session;
  const controller = session?.controller;
  const generation = inputGeneration;
  watchChain = watchChain.then(() => {
    if (generation !== inputGeneration || current?.session !== wheelSession || session?.controller !== controller) return false;
    const input = resolve();
    return input ? action(input.action, input.payload) : false;
  });
  return watchChain;
}
sideButton.addEventListener('pointerdown', event => {
  if (buttonCycleOpen || !available || !session?.controller || submitting) return;
  event.preventDefault();
  buttonPointer = event.pointerId;
  buttonCycleOpen = true;
  sideButton.setPointerCapture(event.pointerId);
  sideButton.classList.add('pressed');
  enqueueWatch('button_down');
  holdTimer = window.setTimeout(() => enqueueWatch('button_hold'), 500);
});
function releaseButton(event: PointerEvent): void {
  if (buttonPointer !== event.pointerId) return;
  if (holdTimer !== null) window.clearTimeout(holdTimer);
  holdTimer = null;
  buttonPointer = null;
  sideButton.classList.remove('pressed');
  void enqueueWatch('button_up').finally(() => { buttonCycleOpen = false; });
}
sideButton.addEventListener('pointerup', releaseButton);
sideButton.addEventListener('pointercancel', releaseButton);

function releaseForLifecycle(): void {
  replayLoadGeneration++;
  inputGeneration++;
  gesture = null;
  if (holdTimer !== null) window.clearTimeout(holdTimer);
  holdTimer = null;
  const pressed = buttonCycleOpen || !!current?.button.down;
  buttonPointer = null;
  buttonCycleOpen = false;
  sideButton.classList.remove('pressed');
  if (!pressed || !session?.controller) return;
  // A release is safe even if its matching down was interrupted. Do not retry
  // or submit any new press when the document loses its input lifecycle.
  void fetch('/api/action', {
    method: 'POST', keepalive: true,
    headers: { 'Content-Type': 'application/json', 'X-EucWatch-Key': session.credential },
    body: JSON.stringify({ id: crypto.randomUUID(), controller: session.controller, action: 'button_up', epoch:current?.session }),
  }).catch(() => { /* The backend input lease also releases abandoned presses. */ });
}
window.addEventListener('pagehide', releaseForLifecycle);
window.addEventListener('blur', releaseForLifecycle);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') releaseForLifecycle();
});

// Polling is sequential. Rendering has its own five-Hz limit so a slow poll
// cannot hide authoritative state returned by a completed action.
async function poll(): Promise<void> {
  await refresh();
  window.setTimeout(() => void poll(), 200);
}
window.setInterval(()=>render(current),200);
void poll();
