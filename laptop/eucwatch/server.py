"""Loopback-only application host; the browser never owns behavior time."""
import argparse
import asyncio
from contextlib import suppress
from pathlib import Path
import secrets
import time

from aiohttp import web

from eucwatch import Application
from eucwatch.recording import Recorder, Replay
from eucwatch.persistence import FileStore
from eucwatch.live import LiveSession
from eucwatch.live_control import LiveControl

ROOT = Path(__file__).resolve().parents[2]


def create_app(application=None, recorder=None, store=None, live=None, *, controller_timeout=10.0, result_limit=2048):
    behavior = application or Application(store=store,event_sink=None if recorder is None else recorder.record)
    live = live or LiveSession(behavior)
    control = LiveControl(live, behavior)
    behavior.live_command_output = control.submit
    credential = secrets.token_urlsafe(32)
    controllers = set()
    results = {}
    seen = set()
    intent_lock = asyncio.Lock()
    last_ui_seen = time.monotonic()

    def expire_controller():
        if controllers and time.monotonic() - last_ui_seen > controller_timeout:
            controllers.clear()
            results.clear()
            seen.clear()
            if behavior.view()['button']['down']:
                behavior.action('button_up')

    def snapshot():
        return {**behavior.view(), 'recording': None if recorder is None else recorder.status(), 'live':live.status()}

    def local(request):
        expected = f'{request.scheme}://{request.host}'
        origin = request.headers.get('Origin')
        if origin and origin != expected:
            raise web.HTTPForbidden(text='Untrusted origin')
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise web.HTTPForbidden(text='Cross-site access is unavailable')
        # DNS rebinding protection: host must name the loopback binding.
        if request.url.host not in ('127.0.0.1', 'localhost', '::1'):
            raise web.HTTPForbidden(text='Loopback host required')

    async def state(request):
        nonlocal last_ui_seen
        local(request)
        expire_controller()
        if request.query.get('controller') and request.query['controller'] not in controllers:
            raise web.HTTPForbidden(text='Controller expired; reacquire current state')
        if request.query.get('controller') in controllers:
            last_ui_seen = time.monotonic()
        return web.json_response(snapshot())

    async def session(request):
        nonlocal last_ui_seen
        local(request)
        expire_controller()
        controller = request.query.get('controller')
        if controller not in controllers:
            if controllers:
                controller = None
            else:
                controller = secrets.token_urlsafe(16)
                controllers.add(controller)
        if controller is not None:
            last_ui_seen = time.monotonic()
        return web.json_response({'credential': credential, 'controller': controller},
            headers={'Cache-Control': 'no-store'})

    async def action(request):
        nonlocal last_ui_seen
        local(request)
        if request.headers.get('Origin') != f'{request.scheme}://{request.host}':
            raise web.HTTPForbidden(text='Same-origin control required')
        if not secrets.compare_digest(request.headers.get('X-EucWatch-Key', ''), credential):
            raise web.HTTPForbidden(text='Launch credential required')
        try:
            payload = await request.json()
            expire_controller()
            controller, identity = payload.pop('controller'), payload.pop('id')
            name = payload.pop('action')
            if not isinstance(name, str) or len(name) > 64:
                raise ValueError('Application action name required')
            if name in ('live_start', 'live_connected', 'live_disconnected', 'command_result', 'horn_result'):
                raise ValueError('Transport callbacks are internal application inputs')
            if controller not in controllers or not isinstance(identity, str) or not identity or len(identity) > 128:
                raise ValueError('Valid controller and request identity required')
            last_ui_seen = time.monotonic()
            key = (controller, identity)
            async with intent_lock:
                if controller not in controllers:
                    raise web.HTTPForbidden(text='Controller expired while action was waiting')
                if key in results:
                    return web.json_response(results[key])
                if key in seen:
                    return web.json_response({'error':'Duplicate action was already processed; its response expired'}, status=409)
                epoch = payload.pop('epoch', None)
                if type(epoch) is not int or epoch != behavior.session:
                    return web.json_response({'error':'Application session changed; refresh before acting'}, status=409)
                if name == 'live_discover':
                    await live.discover()
                    result = snapshot()
                elif name == 'live_select':
                    await live.connect(payload['address'])
                    result = snapshot()
                elif name == 'live_disconnect':
                    await live.disconnect()
                    result = snapshot()
                elif name == 'transfer_begin':
                    # Validate the fresh stopped entry before ending the wheel link.
                    behavior.action(name, **payload)
                    await live.disconnect()
                    result = snapshot()
                else:
                    if name in ('simulator_start','connect','stop','disconnect','replay_start'):
                        await live.disconnect()
                    if name == 'replay_start':
                        payload['recording'] = Replay.from_text(payload['recording'], name=payload.pop('name', 'Imported recording'))
                    if name.startswith('transfer_') and live.client is not None:
                        raise ValueError('Wheel disconnect outcome is uncertain; complete disconnect before configuration transfer')
                    result = behavior.action(name, **payload)
                    if name in ('transfer_send', 'transfer_return') and not behavior.transfer.active and behavior.mode == 'live' and live.selected:
                        await live.connect(live.selected)
                        result = snapshot()
                results[key] = result
                seen.add(key)
                if len(results) > result_limit:
                    del results[next(iter(results))]
                return web.json_response(result)
        except (KeyError, TypeError, ValueError) as exc:
            return web.json_response({'error': str(exc)}, status=400)

    async def index(request):
        local(request)
        path = ROOT / 'frontend/dist/index.html'
        if not path.is_file():
            return web.Response(text='Build frontend assets with ./scripts/setup.sh', status=503)
        return web.FileResponse(path, headers={'Cache-Control': 'no-store'})

    async def recording(request):
        local(request)
        if not secrets.compare_digest(request.headers.get('X-EucWatch-Key',''), credential):
            raise web.HTTPForbidden(text='Launch credential required')
        if recorder is None:
            raise web.HTTPNotFound(text='Recording is not enabled')
        await recorder.drain()
        if recorder.status()['error']:
            raise web.HTTPServiceUnavailable(text=recorder.status()['error'])
        if not recorder.path.is_file():
            raise web.HTTPNotFound(text='No captured events yet')
        return web.FileResponse(recorder.path, headers={'Content-Disposition':'attachment; filename="wheel-recording.jsonl"'})

    async def websocket(request):
        local(request)
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        try:
            while not ws.closed:
                await ws.send_json(snapshot())
                await asyncio.sleep(.2)
        finally:
            await ws.close()
        return ws

    async def lifetime(app):
        async def run():
            while True:
                expire_controller()
                if time.monotonic() - last_ui_seen > 2 and behavior.view()['button']['down']:
                    behavior.action('button_up')
                behavior.tick()
                live.tick()
                control.tick()
                await asyncio.sleep(.02)
        async def write_recording():
            assert recorder is not None
            while True:
                await recorder.drain()
                await asyncio.sleep(.05)
        task = asyncio.create_task(run())
        writer = None if recorder is None else asyncio.create_task(write_recording())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await control.close()
        behavior.live_command_output = None
        await live.close()
        if writer is not None:
            writer.cancel()
            with suppress(asyncio.CancelledError):
                await writer
        if recorder is not None:
            await recorder.close()

    app = web.Application(client_max_size=16 * 1024 * 1024 + 4096)
    app.cleanup_ctx.append(lifetime)
    app.add_routes([web.get('/api/state', state), web.get('/api/session', session),
        web.post('/api/action', action), web.get('/api/ws', websocket), web.get('/api/recording', recording), web.get('/', index)])
    assets = ROOT / 'frontend/dist/assets'
    if assets.is_dir():
        app.router.add_static('/assets/', assets)
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    web.run_app(create_app(recorder=Recorder(),store=FileStore()), host='127.0.0.1', port=args.port, print=None,
        handle_signals=True)


if __name__ == '__main__':
    main()
