"""Exercise the real launcher and offline relaunch with isolated XDG storage."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4


def run():
    root = Path(__file__).resolve().parents[1]
    fixture = json.loads((root / 'docs/acceptance/scenarios/freshness.json').read_text())
    with tempfile.TemporaryDirectory(prefix='eucwatch-launch-') as temporary:
        directory = Path(temporary)
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        url = f'http://127.0.0.1:{port}'
        environment = os.environ | {
            'XDG_CONFIG_HOME': str(directory / 'config'),
            'XDG_DATA_HOME': str(directory / 'data'),
            'EUCWATCH_PORT': str(port), 'EUCWATCH_NO_BROWSER': '1',
        }

        def get(path):
            with urlopen(url + path, timeout=1) as response:
                return json.load(response)

        def start(log):
            process = subprocess.Popen(['./scripts/launch.sh'], cwd=root, env=environment,
                                       stdout=log, stderr=log, start_new_session=True)
            try:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError('Launcher exited before readiness')
                    try:
                        state = get('/api/state')
                        with urlopen(url, timeout=1) as response:
                            assert b'/assets/' in response.read()
                        return process, state
                    except (URLError, TimeoutError):
                        time.sleep(.05)
                raise TimeoutError('Launcher readiness')
            except BaseException:
                stop(process)
                raise

        def stop(process):
            try:
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
                    process.wait(timeout=10)
                assert process.returncode == 0, process.returncode
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    try:
                        connection = socket.create_connection(('127.0.0.1', port), timeout=1)
                    except ConnectionRefusedError:
                        return
                    else:
                        connection.close()
                    time.sleep(.05)
                raise AssertionError('Backend survived launcher shutdown')
            finally:
                # Only this test's process group, including any abandoned child.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)

        with (directory / 'launch.log').open('w') as log:
            process, state = start(log)
            try:
                assert state['mode'] == 'idle' and not state['connected']
                assert state['command_events'] == []
                session = get('/api/session')

                def action(action_name, **payload):
                    current = get('/api/state')
                    body = {'action': action_name, 'id': uuid4().hex, 'epoch': current['session'],
                            'controller': session['controller'], **payload}
                    request = Request(url + '/api/action', data=json.dumps(body).encode(),
                                      headers={'Origin': url, 'X-EucWatch-Key': session['credential'],
                                               'Content-Type': 'application/json'})
                    with urlopen(request, timeout=2) as response:
                        return json.load(response)

                action('alerts_begin')
                action('alerts_update', alert='pwm', enabled=True, threshold=70)
                action('alerts_save')
                state = action('preset_begin', slot=3)
                editor = state['preset_editor']['id']
                action('preset_update', editor_id=editor, name='Commute', pedal_sensitivity=40)
                saved = action('preset_save', editor_id=editor)['config']
                action('simulator_configure', **fixture['simulator'])
                action('scenario_save', name=fixture['name'], steps=fixture['steps'])
                definition = get('/api/state')['scenario']['definition']
                assert definition == fixture
                action('scenario_start')
                state = action('preset_apply', slot=3)
                assert state['preset_attempt']['pending']
                # Both a pending simulated command and a local draft are transient.
                action('preset_begin', slot=2)
                state = get('/api/state')
                assert state['preset_draft'] is not None
            finally:
                stop(process)

            process, restored = start(log)
            try:
                assert restored['mode'] == 'idle' and not restored['connected']
                assert restored['config'] == saved
                assert restored['preset_draft'] is None and restored['preset_input'] is None
                assert restored['alerts_draft'] is None
                assert restored['command_events'] == [] and restored['preset_attempt'] is None
                assert restored['confirmed_preset'] is None
                assert restored['scenario']['definition'] == definition
                assert not restored['scenario']['active']
                assert (directory / 'config/eucwatch/configuration.json').is_file()
                assert (directory / 'data/eucwatch/scenarios/current.json').is_file()
                assert list((directory / 'data/eucwatch/recordings').glob('*.jsonl'))
            finally:
                stop(process)

    result = {'issue': 31, 'command': './scripts/launch.sh',
              'provenance': 'real launcher subprocess / HTTP / isolated XDG files; simulator only',
              'expected': 'idle startup; SIGINT closes port; offline relaunch retains saved preset, alerts and scenario without draft, command or confirmation replay',
              'observed': 'passed', 'offline': 'launcher uses uv --offline --no-sync and existing frontend assets; network not physically disconnected',
              'saved': saved, 'scenario': definition, 'shutdowns': 2}
    output = root / '.test-output/launch.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print('launch / shutdown / offline relaunch: passed')


if __name__ == '__main__':
    run()
