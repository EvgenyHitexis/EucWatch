import './style.css';

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
interface View {
  mode: string;
  session: number;
  elapsed_s: number;
  connected: boolean;
  fresh: boolean;
  screen: 'dashboard' | 'presets' | 'settings';
  awake: boolean;
  button: { down: boolean; wake_cycle: boolean };
  recovery: boolean;
  established_connection: boolean;
  recording: { path: string; queued: number; written: number; rejected: number; error: string | null; closed: boolean } | null;
  replay: { name: string; sha256: string; source: string; total: number; position: number; finished: boolean } | null;
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
        <p class="watch-note">Swipe left for presets, down from the top for Settings.<br>Swipe right to go back. Side button wakes the screen.<br>Watch battery is simulated.</p>
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
          <div class="actions"><button type="submit" class="primary" data-action="simulator_configure" data-simulator>Send simulator readings</button><button type="button" id="emit" data-action="simulator_emit" data-simulator>Emit another frame</button></div>
        </form>
        <div class="actions"><button id="advance" data-action="advance" data-simulator>Advance 1.1 seconds</button><button id="disconnect" data-action="disconnect" data-simulator>Disconnect</button><button id="connect" data-action="connect" data-simulator>Reconnect</button></div>
        <p class="messages" id="message" role="alert"></p>
        <div class="divider"></div>
        <div class="metadata" id="diagnostics">Session not started.</div>
        <p class="metadata">Simulator results establish software behavior. Physical wheel and watch acceptance remains separate.</p>
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
      </section>
    </div>
  </main>`;

const canvas = document.querySelector<HTMLCanvasElement>('#watch')!;
const ctx = canvas.getContext('2d')!;
const status = document.querySelector<HTMLElement>('#backend-status')!;
const message = document.querySelector<HTMLElement>('#message')!;
let session: Session | null = null;
let current: View | null = null;
let available = false;
let submitting = false;
let loadingReplay = false;
let replayLoadGeneration = 0;
let rendered = '';
const controllerStorageKey = 'sherman-l-controller';
let acquiringSession: Promise<Session> | null = null;

function storedController(): string | null {
  try { return sessionStorage.getItem(controllerStorageKey); } catch { return null; }
}

async function acquireSession(): Promise<Session> {
  if (!acquiringSession) {
    const token = storedController();
    const query = token ? `?controller=${encodeURIComponent(token)}` : '';
    acquiringSession = read<Session>(`/api/session${query}`).then(result => {
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
  document.querySelector<HTMLButtonElement>('#advance')!.disabled ||= !document.querySelector<HTMLInputElement>('#controlled')!.checked;
  document.querySelector<HTMLButtonElement>('#replay-load')!.disabled ||= loadingReplay;
  document.querySelector<HTMLButtonElement>('#replay-step')!.disabled = !available || !session?.controller || submitting || current?.mode !== 'replay' || !current.replay || current.replay.finished;
  document.querySelector<HTMLButtonElement>('#recording-download')!.disabled = !available || !session?.credential || !current?.recording;
}

function text(value: string, x: number, y: number, size: number, color = '#ffffff', align: CanvasTextAlign = 'left'): void {
  ctx.fillStyle = color;
  ctx.font = `${size >= 22 ? 'bold ' : ''}${size}px sans-serif`;
  ctx.textAlign = align;
  ctx.fillText(value, x, y);
}

function render(view: View | null): void {
  const key = JSON.stringify([view, available]);
  if (key === rendered) return;
  rendered = key;
  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, 240, 240);
  const screen = view?.screen ?? 'dashboard';
  const awake = view?.awake ?? true;
  canvas.dataset.screen = screen;
  canvas.dataset.awake = String(awake);
  canvas.dataset.elapsed = String(view?.elapsed_s ?? 0);
  document.querySelector<HTMLElement>('#mode')!.textContent = view?.mode === 'simulator' ? 'SIMULATOR' : view?.mode === 'replay' ? 'READ-ONLY REPLAY' : view?.mode === 'live' ? 'LIVE WHEEL' : 'IDLE · NO WHEEL';
  if (view) document.querySelector<HTMLElement>('#diagnostics')!.textContent = `Session ${view.session} · Valid frames: ${view.diagnostics.valid_frames} · CRC/format rejects: ${view.diagnostics.rejected_frames} · Resume events: ${view.diagnostics.resume_events}`;
  const recording = view?.recording;
  document.querySelector<HTMLElement>('#recording-status')!.textContent = recording ? `${recording.closed ? 'Closed recording' : 'Recording'} · ${recording.written} events written · ${recording.queued} queued · ${recording.rejected} rejected${!available ? ' · last known status' : ''}` : 'Recording is not enabled for this application session.';
  document.querySelector<HTMLElement>('#recording-error')!.textContent = recording?.error ? `Recording failure: ${recording.error}` : '';
  const replay = view?.replay;
  document.querySelector<HTMLElement>('#replay-progress')!.textContent = replay ? `${replay.finished ? 'Replay finished' : 'Read-only replay'} · ${replay.position} / ${replay.total} events · elapsed ${(view?.elapsed_s ?? 0).toFixed(2)} s` : 'No replay loaded.';
  document.querySelector<HTMLElement>('#replay-provenance')!.textContent = replay ? `${replay.name} · Source: ${replay.source} · SHA-256: ${replay.sha256}` : '';
  if (!awake) {
    text('SCREEN ASLEEP', 120, 113, 16, '#777777', 'center');
    text('Press side button to wake', 120, 140, 12, '#777777', 'center');
    canvas.setAttribute('aria-label', 'Screen asleep. Press the watch physical button to wake only.');
    return;
  }
  if (view?.recovery) {
    text('RECOVERY', 120, 108, 24, '#ffffff', 'center');
    text('Wheel controls unavailable', 120, 137, 12, '#ffffff', 'center');
    canvas.setAttribute('aria-label', 'Recovery mode. Wheel controls unavailable.');
    return;
  }
  if (screen !== 'dashboard') {
    text(screen === 'presets' ? 'RIDING PRESETS' : 'SETTINGS', 120, 26, 15, '#ffffff', 'center');
    if (screen === 'presets') {
      for (let i = 0; i < 4; i++) {
        const x = 9 + (i % 2) * 115;
        const y = 43 + Math.floor(i / 2) * 81;
        ctx.strokeStyle = '#777777';
        ctx.strokeRect(x, y, 106, 72);
        text(`Preset ${i + 1}`, x + 53, y + 31, 16, '#777777', 'center');
        text('Unconfigured', x + 53, y + 51, 10, '#777777', 'center');
      }
      canvas.setAttribute('aria-label', 'Preset menu. Four fixed slots: Preset 1, Preset 2, Preset 3, Preset 4, all unconfigured. Swipe right to return without applying.');
    } else {
      ctx.strokeStyle = '#ffffff';
      ctx.strokeRect(12, 71, 216, 60);
      text('Sleep screen', 120, 107, 20, '#ffffff', 'center');
      text('Swipe right to go back', 120, 155, 12, '#ffffff', 'center');
      canvas.setAttribute('aria-label', 'Settings. Sleep screen. Swipe right to return without saving.');
    }
    text('‹ Swipe right to return', 120, 228, 11, '#ffffff', 'center');
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
  canvas.setAttribute('aria-label', summary);
  canvas.dataset.fresh = String(connected);
  canvas.dataset.batteryDimmed = String(!!d?.wheel_battery_dimmed || !available);
}

async function read<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: 'no-store', signal: AbortSignal.timeout(1500) });
  if (!response.ok) throw new Error(`Application returned ${response.status}`);
  return response.json() as Promise<T>;
}

async function refresh(): Promise<void> {
  try {
    if (!session) session = await acquireSession();
    const query = session.controller && document.visibilityState === 'visible' ? `?controller=${encodeURIComponent(session.controller)}` : '';
    current = await read<View>(`/api/state${query}`);
    available = true;
    status.textContent = session.controller ? 'Application ready' : 'Viewing only · another window controls this session';
    status.classList.remove('error');
  } catch {
    available = false;
    session = null;
    status.textContent = 'Application unavailable · controls disabled';
    status.classList.add('error');
  }
  setControls();
}

async function action(actionName: string, payload: Record<string, unknown> = {}): Promise<boolean> {
  if (!available || !session?.controller || submitting) return false;
  if (['simulator_start', 'stop', 'connect', 'replay_start'].includes(actionName)) replayLoadGeneration++;
  submitting = true;
  setControls();
  message.textContent = '';
  try {
    const response = await fetch('/api/action', {
      method: 'POST',
      signal: AbortSignal.timeout(1500),
      headers: { 'Content-Type': 'application/json', 'X-EucWatch-Key': session.credential },
      body: JSON.stringify({ id: crypto.randomUUID(), controller: session.controller, action: actionName, ...payload }),
    });
    if (!response.ok) {
      if (response.status === 403) {
        session = null;
        available = false;
      }
      const result = await response.json() as { error?: string };
      throw new Error(result.error ?? `Action refused (${response.status})`);
    }
    await refresh();
    return true;
  } catch (error) {
    message.textContent = error instanceof Error ? error.message : 'Action could not be sent';
    return false;
  } finally {
    submitting = false;
    setControls();
  }
}

function number(id: string): number { return Number(document.querySelector<HTMLInputElement>(`#${id}`)!.value); }

document.querySelector('#start')!.addEventListener('click', () => void action('simulator_start', { controlled: document.querySelector<HTMLInputElement>('#controlled')!.checked }));
document.querySelector('#stop')!.addEventListener('click', () => void action('stop'));
document.querySelector('#scenario')!.addEventListener('submit', async event => {
  event.preventDefault();
  const configured = await action('simulator_configure', {
    speed_kmh: number('speed'), voltage_V: number('voltage'), pwm_percent: number('pwm'),
    watch_battery_percent: number('watch-battery'), frame_length: number('length'),
    fragment_size: number('fragment'), traffic: document.querySelector<HTMLSelectElement>('#traffic')!.value,
  });
  if (configured) await action('simulator_emit');
});
document.querySelector('#emit')!.addEventListener('click', () => void action('simulator_emit'));
document.querySelector('#advance')!.addEventListener('click', () => void action('advance', { seconds: 1.1 }));
document.querySelector('#disconnect')!.addEventListener('click', () => void action('disconnect'));
document.querySelector('#connect')!.addEventListener('click', () => void action('connect', { mode: 'simulator', controlled: document.querySelector<HTMLInputElement>('#controlled')!.checked }));
document.querySelector('#controlled')!.addEventListener('change', setControls);
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
let gesture: { x: number; y: number; pointer: number } | null = null;
canvas.addEventListener('pointerdown', event => {
  if (!available || !session?.controller || !current?.awake || current.recovery) return;
  gesture = { ...watchPoint(event), pointer: event.pointerId };
  canvas.setPointerCapture(event.pointerId);
  enqueueWatch('interact');
});
canvas.addEventListener('pointerup', event => {
  if (!gesture || gesture.pointer !== event.pointerId) return;
  const start = gesture;
  gesture = null;
  const end = watchPoint(event);
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  if (Math.abs(dx) >= 40 && Math.abs(dx) > Math.abs(dy)) {
    enqueueWatch('swipe', { direction: dx < 0 ? 'left' : 'right', from_top: start.y <= 45 });
  } else if (dy >= 40 && Math.abs(dy) > Math.abs(dx)) {
    enqueueWatch('swipe', { direction: 'down', from_top: start.y <= 45 });
  } else if (Math.abs(dx) < 12 && Math.abs(dy) < 12 && current?.screen === 'settings' && end.x >= 12 && end.x <= 228 && end.y >= 71 && end.y <= 131) {
    enqueueWatch('sleep');
  }
});
canvas.addEventListener('pointercancel', () => { gesture = null; });

const sideButton = document.querySelector<HTMLButtonElement>('#watch-button')!;
let buttonPointer: number | null = null;
let watchChain: Promise<unknown> = Promise.resolve();
let holdTimer: number | null = null;
let buttonCycleOpen = false;
let inputGeneration = 0;
function enqueueWatch(actionName: string, payload: Record<string, unknown> = {}): Promise<unknown> {
  const wheelSession = current?.session;
  const controller = session?.controller;
  const generation = inputGeneration;
  watchChain = watchChain.then(() => {
    if (generation !== inputGeneration || current?.session !== wheelSession || session?.controller !== controller) return false;
    return action(actionName, payload);
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
    body: JSON.stringify({ id: crypto.randomUUID(), controller: session.controller, action: 'button_up' }),
  }).catch(() => { /* The backend input lease also releases abandoned presses. */ });
}
window.addEventListener('pagehide', releaseForLifecycle);
window.addEventListener('blur', releaseForLifecycle);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') releaseForLifecycle();
});

// A single awaited loop bounds requests and redraws to five per second,
// including recovery after a slow response. Browser time never drives behavior.
async function poll(): Promise<void> {
  await refresh();
  render(current);
  window.setTimeout(() => void poll(), 200);
}
void poll();
