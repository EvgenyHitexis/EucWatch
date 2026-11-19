"""Shared test support. Test files import from here, never from one another.

It owns the protocol frame builders, the fake Bleak transports, the Preset
editor action helper, the saved Preset fixture, and, for the browser flows, the served laptop
application plus Chrome page bootstrap, the CDP driver and the watch pointer
and screenshot helpers, the gate on tracked evidence, and the loader for the
hyphenated scripts/*.py. Nothing here opens
Bluetooth or touches a wheel.
"""
import asyncio
import base64
import hashlib
import importlib.util
import inspect
import json
import os
import socket
import subprocess
import sys
import tempfile
import zlib
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from aiohttp import ClientSession, web

from eucwatch import Application, ManualClock
from eucwatch.live import LiveSession
from eucwatch.persistence import FileStore
from eucwatch.recording import Recorder
from eucwatch.scenarios import FileScenarioStore
from eucwatch.server import create_app

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    """Import scripts/<name>.py as a module; its hyphenated name rules out a plain import."""
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(content):
    return hashlib.sha256(content).hexdigest()


# Frame builders

SOURCE_FRAME = bytes.fromhex(
    "".join(
        json.loads(line)["raw_hex"]
        for line in (ROOT / "experiments/laptop-feasibility/evidence/fixture-recording.jsonl")
        .read_text()
        .splitlines()[:5]
    )
)


def settings_frame(sensitivity=31, assist=26, dip=10, subtype=8):
    frame = bytearray(71)
    frame[:4] = bytes.fromhex("dc5a5c47")
    frame[4:6] = (13500).to_bytes(2, "big")
    frame[6:8] = (250).to_bytes(2, "big", signed=True)
    frame[28:30] = (6010).to_bytes(2, "big")
    frame[46] = subtype
    frame[50], frame[66], frame[68] = sensitivity, assist, dip
    return bytes(frame) + zlib.crc32(frame).to_bytes(4, "big")


# Fake Bleak transports

ADDRESS = "00:11:22:33:44:55"
SERVICE = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC = "0000ffe1-0000-1000-8000-00805f9b34fb"


class Scanner:
    def __init__(self):
        self.device = SimpleNamespace(address=ADDRESS, name="Selected wheel")
        self.calls = []

    async def discover(self, **options):
        self.calls.append(options)
        advertisement = SimpleNamespace(
            local_name="Selected wheel", rssi=-76, service_uuids=[SERVICE]
        )
        return {ADDRESS: (self.device, advertisement)}


class Client:
    def __init__(self, device, *, disconnected_callback, **options):
        self.device = device
        self.disconnected_callback = disconnected_callback
        self.is_connected = False
        self.calls = []
        self.notification = None
        self.characteristic = SimpleNamespace(
            uuid=CHARACTERISTIC, service_uuid=SERVICE, properties=["notify", "write"]
        )
        self.services = SimpleNamespace(
            get_service=lambda uuid: (
                SimpleNamespace(uuid=SERVICE) if uuid == SERVICE else None
            ),
            get_characteristic=lambda uuid: (
                self.characteristic if uuid == CHARACTERISTIC else None
            ),
        )

    async def connect(self):
        self.calls.append("connect")
        self.is_connected = True

    async def start_notify(self, characteristic, callback, **options):
        self.calls.append(("subscribe", characteristic.uuid, options))
        self.notification = callback

    async def disconnect(self):
        self.calls.append("disconnect")
        self.is_connected = False
        self.disconnected_callback(self)

    def emit(self, raw):
        self.notification(self.characteristic, bytearray(raw))

    def lose_link(self):
        self.is_connected = False
        self.disconnected_callback(self)


class WritingClient(Client):
    def __init__(self, *args, **options):
        super().__init__(*args, **options)
        self.characteristic.properties = ["notify", "write-without-response"]
        self.characteristic.max_write_without_response_size = 20
        self.writes = []
        self.behavior = None

    async def write_gatt_char(self, characteristic, data, *, response):
        self.writes.append((characteristic.uuid, bytes(data), response))
        if self.behavior:
            await self.behavior(bytes(data))


class Clients:
    """A Bleak client factory that keeps every client it creates."""

    def __init__(self, kind=Client):
        self.kind = kind
        self.created = []

    def __call__(self, device, **options):
        client = self.kind(device, **options)
        self.created.append(client)
        return client


# Preset editor actions and saved Preset fixture

def save_preset(app, slot=1, **changes):
    """Seed a saved Preset definition through local restore; never pretend fixture setup is editing."""
    config = app.view()["config"]
    config["presets"][slot - 1].update(changes)
    if any(field in changes for field in ("pedal_sensitivity", "dynamic_assist")):
        config["presets"][slot - 1]["configured"] = True
    if "pedal_dip_compensation" in changes:
        config["presets"][slot - 1]["dip_included"] = True
    app.action("configuration_import_prepare", content=json.dumps(config))
    return app.action("configuration_import_commit")


def edit(app, action, **payload):
    """Send a Preset editor action with the current editor and entry identities."""
    request = app.view()['preset_editor']
    entry = app.view()['preset_input']
    if entry and 'id' in entry:
        payload.setdefault('entry_id', entry['id'])
    return app.action(action, editor_id=request['id'] if request else -1, **payload)


# Chrome DevTools Protocol driver

def label_shows(label, text):
    """Whether a watch label shows text as whole text: an occurrence counts only if
    it does not run into a longer word. 'Input Ab 3' is not shown by 'Input Ab 3y.',
    the frame the Preset editor draws before a backspace, and '6.' not by '26.'."""
    start = label.find(text)
    while start >= 0:
        end = start + len(text)
        starts_word = start == 0 or not (text[0].isalnum() and label[start - 1].isalnum())
        ends_word = end == len(label) or not (text[-1].isalnum() and label[end].isalnum())
        if starts_word and ends_word:
            return True
        start = label.find(text, start + 1)
    return False


class Browser:
    """One Chrome DevTools websocket. Page-level calls name a session."""

    def __init__(self, ws):
        self.ws, self.sequence = ws, 0

    async def call(self, method, params=None, session=None):
        self.sequence += 1
        message = {'id': self.sequence, 'method': method, 'params': params or {}}
        if session:
            message['sessionId'] = session
        await self.ws.send_json(message)
        async with asyncio.timeout(15):
            while True:
                response = await self.ws.receive_json()
                if response.get('id') == self.sequence:
                    if 'error' in response:
                        raise RuntimeError(response['error'])
                    return response.get('result', {})

    async def open(self, url):
        target = await self.call('Target.createTarget', {'url': url})
        attached = await self.call('Target.attachToTarget',
                                   {'targetId': target['targetId'], 'flatten': True})
        return Page(self, attached['sessionId'], target['targetId'])


class Page:
    """One attached tab showing the laptop application."""

    def __init__(self, browser, session, target):
        self.browser, self.session, self.target = browser, session, target

    async def call(self, method, params=None):
        return await self.browser.call(method, params, self.session)

    async def close(self):
        await self.browser.call('Target.closeTarget', {'targetId': self.target})

    async def evaluate(self, expression):
        response = await self.call('Runtime.evaluate', {'expression': expression,
            'returnByValue': True, 'awaitPromise': True})
        if 'exceptionDetails' in response:
            raise RuntimeError(response['exceptionDetails'])
        return response['result'].get('value')

    async def wait(self, expression):
        async with asyncio.timeout(15):
            while not await self.evaluate(expression):
                await asyncio.sleep(.05)

    async def click(self, selector):
        """Wait until the control is enabled, then click it."""
        await self.wait(f"!document.querySelector({json.dumps(selector)}).disabled")
        await self.evaluate(f"document.querySelector({json.dumps(selector)}).click()")

    async def choose_files(self, selector, *paths):
        document = await self.call('DOM.getDocument')
        node = await self.call('DOM.querySelector', {'nodeId': document['root']['nodeId'],
                                                     'selector': selector})
        await self.call('DOM.setFileInputFiles', {'nodeId': node['nodeId'],
                                                  'files': [str(path) for path in paths]})

    async def screenshot(self, path):
        image = await self.call('Page.captureScreenshot', {'format': 'png'})
        Path(path).write_bytes(base64.b64decode(image['data']))

    # The watch face

    async def pointer(self, start, end, selector='#watch'):
        box = await self.evaluate(f"""(() => {{ const b=document.querySelector({json.dumps(selector)}).getBoundingClientRect(); return {{x:b.x,y:b.y,width:b.width,height:b.height}}; }})()""")
        for kind, point, pressed in [('mousePressed', start, True), ('mouseMoved', end, True), ('mouseReleased', end, False)]:
            await self.call('Input.dispatchMouseEvent', {'type': kind,
                'x': box['x'] + point[0], 'y': box['y'] + point[1],
                'button': 'left', 'buttons': 1 if pressed else 0, 'clickCount': 1})

    async def tap(self, x, y):
        await self.pointer((x, y), (x, y))

    async def press_button(self):
        """Press and release the watch's physical button."""
        await self.pointer((10, 20), (10, 20), '#watch-button')

    async def label(self, text, timeout=15):
        """Wait until the watch's accessible description shows text (see label_shows).
        Raises TimeoutError naming text and the last label after `timeout` seconds."""
        shown = None
        try:
            async with asyncio.timeout(timeout):
                while not label_shows(shown := await self.evaluate(
                        "document.querySelector('#watch')?.getAttribute('aria-label') ?? ''"), text):
                    await asyncio.sleep(.05)
        except TimeoutError:
            raise TimeoutError(f'the watch label never showed {text!r} within {timeout} s; it showed {shown!r}') from None

    async def screen(self, name):
        await self.wait(f"document.querySelector('#watch')?.dataset.screen==={json.dumps(name)}")

    async def description(self):
        return await self.evaluate("document.querySelector('#watch').getAttribute('aria-label')")

    async def snapshot(self, path, *, shows, timeout=5):
        """Wait until the watch shows `shows`, then write that 240x240 Canvas frame as a PNG.

        `shows` is a screen id (the Canvas's data-screen) or text its
        accessible label shows, matched as label_shows matches it. The Canvas
        repaints on its own 200 ms timer, and each paint sets the screen id and
        label together with the pixels, so one page evaluation reads all three
        from the same frame. Returns the frame's accessible label. Raises TimeoutError naming
        `shows`, the path and what the watch showed instead if no frame within
        `timeout` seconds shows it.
        """
        shown = None
        try:
            async with asyncio.timeout(timeout):
                while True:
                    shown = await self.evaluate("""(() => { const watch = document.querySelector('#watch');
                        return {screen: watch.dataset.screen ?? '', label: watch.getAttribute('aria-label') ?? '',
                                png: watch.toDataURL().split(',')[1]}; })()""")
                    if shown['screen'] == shows or label_shows(shown['label'], shows):
                        break
                    await asyncio.sleep(.05)
        except TimeoutError:
            instead = f"screen {shown['screen']!r}, label {shown['label']!r}" if shown else 'nothing'
            raise TimeoutError(f'the watch never showed {shows!r} within {timeout} s, so {path} '
                               f'was not written; it showed {instead}') from None
        Path(path).write_bytes(base64.b64decode(shown['png']))
        return shown['label']


async def type_percentage(tap, text):
    """Clear the Preset value entry keypad, then type text on its digits."""
    await tap(49, 166)
    for digit in text:
        index = 10 if digit == '0' else '123456789'.index(digit)
        await tap(49 + index % 3 * 70, 73 + index // 3 * 31)


# Served application and Chrome bootstrap

class Server:
    """The aiohttp application on 127.0.0.1, restartable on the same port."""

    def __init__(self, app, **options):
        self.runner = web.AppRunner(create_app(app, **options))
        self.running = False

    async def start(self, port=0):
        await self.runner.setup()
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('127.0.0.1', port))
        await web.SockSite(self.runner, sock).start()
        self.running = True
        self.port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{self.port}'
        return self

    async def stop(self):
        if self.running:
            self.running = False
            await self.runner.cleanup()


@asynccontextmanager
async def chrome():
    """Headless Chrome with a throwaway profile, driven over CDP."""
    with tempfile.TemporaryDirectory(prefix='eucwatch-chrome-', ignore_cleanup_errors=True) as profile:
        process = subprocess.Popen(['google-chrome', '--headless', '--no-first-run',
            '--no-default-browser-check', '--disable-sync', '--disable-background-networking',
            '--remote-debugging-port=0', f'--user-data-dir={profile}', 'about:blank'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            # Chrome creates DevToolsActivePort before it writes the port and path into it, so wait for both lines.
            port_file = Path(profile) / 'DevToolsActivePort'
            async with asyncio.timeout(15):
                while len(lines := port_file.read_text().splitlines() if port_file.exists() else []) < 2:
                    if process.poll() is not None:
                        raise RuntimeError('Chrome exited before readiness')
                    await asyncio.sleep(.1)
            port, path = lines[:2]
            async with ClientSession() as client, client.ws_connect(f'http://127.0.0.1:{port}{path}') as ws:
                yield Browser(ws)
        finally:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)


@asynccontextmanager
async def watch_page(app, **options):
    """Serve app (create_app options pass through) and open it in Chrome."""
    server = await Server(app, **options).start()
    try:
        async with chrome() as browser:
            yield await browser.open(server.url)
    finally:
        await server.stop()


@asynccontextmanager
async def served_laptop():
    """The laptop application the riding flows exercise, open in Chrome.

    A controlled host clock, a recorder, a FileStore and a scenario store under
    .test-output/, and a live session over fake writing Bleak clients. The page
    is ready to take actions when it is yielded.
    """
    output = Path('.test-output')
    output.mkdir(exist_ok=True)
    run_id = uuid4().hex
    clock = ManualClock()
    recorder = Recorder(output / f'ui-recording-{run_id}.jsonl')
    app = Application(clock=clock, event_sink=recorder.record,
                      store=FileStore(output / f'ui-config-{run_id}.json'))
    clients = Clients(WritingClient)
    live = LiveSession(app, scanner=Scanner(), client_factory=clients, reconnect_delay=0)
    async with watch_page(app, recorder=recorder, live=live,
                          scenario_store=FileScenarioStore(output / f'ui-scenario-{run_id}.json')) as page:
        await page.wait("document.querySelector('#backend-status')?.textContent==='Application ready'")
        yield SimpleNamespace(page=page, app=app, clock=clock, clients=clients,
                              output=output, run_id=run_id)


def evidence_directory(directory):
    """Where a flow writes the evidence for docs/acceptance/evidence/<directory>.

    Tracked evidence is rewritten only on request, as in the watch suites: with
    EUCWATCH_WRITE_EVIDENCE=1 this is the tracked directory, otherwise the same
    files go to .test-output/evidence/<directory>, so a plain run leaves git
    status unchanged.
    """
    if os.environ.get('EUCWATCH_WRITE_EVIDENCE') == '1':
        return Path('docs/acceptance/evidence') / directory
    return Path('.test-output/evidence') / directory


def write_evidence(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def source_digests(paths):
    """The sha256 of each source, keyed by its path from the repository root
    and sorted, so every checkout and working directory writes the same keys."""
    digests = {Path(p).resolve().relative_to(ROOT).as_posix(): hashlib.sha256(Path(p).read_bytes()).hexdigest()
               for p in paths}
    return dict(sorted(digests.items()))


async def record_flow(exercise, name, directory):
    """Run exercise(page, app, output) on a fresh FileStore application and
    record its result as <name>.json in evidence_directory(directory)."""
    output = evidence_directory(directory)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='eucwatch-local-', ignore_cleanup_errors=True) as temporary:
        app = Application(clock=ManualClock(), store=FileStore(Path(temporary) / 'config.json'))
        async with watch_page(app) as page:
            result = await exercise(page, app, output)
        sources = [*ROOT.glob('laptop/eucwatch/*.py'), *ROOT.glob('frontend/src/*.ts'),
                   Path(__file__), Path(inspect.getfile(exercise))]
        result.update(provenance='Actual built Canvas / Chrome pointer events / aiohttp Application / FileStore / controlled simulator; no physical operations',
                      source_sha256=source_digests(sources))
        write_evidence(output / (name + '.json'), result)
        print(name + ': passed')


def main(*flows):
    """Run the named flows from the command line, or all of them, in order."""
    chosen = sys.argv[1:] or [flow.__name__ for flow in flows]
    known = {flow.__name__: flow for flow in flows}
    unknown = [name for name in chosen if name not in known]
    if unknown:
        raise SystemExit(f'unknown flow {unknown}; choose from {list(known)}')
    for name in chosen:
        asyncio.run(known[name]())


# Riding dashboard steps shared by the flows

async def start_simulator(page):
    """Start the controlled-time Wheel simulator from the panel."""
    await page.evaluate("document.querySelector('#controlled').checked=true;document.querySelector('[data-action=simulator_start]').click()")
    await page.wait("document.querySelector('#watch').getAttribute('aria-label').includes('Connected')")


async def send_readings(page, speed, voltage, pwm, traffic='normal'):
    """Submit Wheel simulator readings and wait until the panel accepts them."""
    await page.evaluate(f"""document.querySelector('#speed').value={json.dumps(str(speed))};
        document.querySelector('#voltage').value={json.dumps(str(voltage))};
        document.querySelector('#pwm').value={json.dumps(str(pwm))};
        document.querySelector('#traffic').value={json.dumps(traffic)};
        document.querySelector('#scenario').requestSubmit();""")
    await page.wait("!document.querySelector('[data-action=simulator_configure]').disabled")


async def advance(page, app, seconds):
    """Advance controlled simulator time through the panel."""
    elapsed = app.view()['elapsed_s']
    await page.evaluate(f"document.querySelector('#advance-seconds').value={json.dumps(str(seconds))}")
    await page.wait("!document.querySelector('#advance').disabled")
    await page.evaluate("document.querySelector('#advance').click()")
    await page.wait(f"Number(document.querySelector('#watch').dataset.elapsed)>={elapsed+seconds-.00001}")


async def select_second_preset(page):
    """Swipe to the Preset menu and tap Preset slot 2."""
    await page.pointer((215, 120), (20, 120))
    await page.screen('presets')
    await page.tap(177, 80)


def save_ab_2(app):
    """Seed Preset slot 2 as the riding flows expect it."""
    save_preset(app, slot=2, name='Ab 2', pedal_sensitivity=31, dynamic_assist=26)


def horn_requests(app):
    return sum(row.get('kind') == 'horn' and row['event'] == 'submission'
               for row in app.view()['command_events'])
