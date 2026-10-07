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

ROOT = Path(__file__).resolve().parents[2]


def create_app(application=None, recorder=None):
    behavior = application or Application(event_sink=None if recorder is None else recorder.record)
    credential = secrets.token_urlsafe(32)
    controllers = set()
    results = {}
    last_ui_seen = time.monotonic()

    def snapshot():
        return {**behavior.view(), 'recording': None if recorder is None else recorder.status()}

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
        if request.query.get('controller') in controllers:
            last_ui_seen = time.monotonic()
        return web.json_response(snapshot())

    async def session(request):
        nonlocal last_ui_seen
        local(request)
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
            controller, identity = payload.pop('controller'), payload.pop('id')
            name = payload.pop('action')
            if controller not in controllers or not isinstance(identity, str) or not identity or len(identity) > 128:
                raise ValueError('Valid controller and request identity required')
            last_ui_seen = time.monotonic()
            key = (controller, identity)
            if key in results:
                return web.json_response(results[key])
            if name == 'replay_start':
                payload['recording'] = Replay.from_text(payload['recording'], name=payload.pop('name', 'Imported recording'))
            result = behavior.action(name, **payload)
            results[key] = result
            if len(results) > 2048:
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
                if time.monotonic() - last_ui_seen > 2 and behavior.view()['button']['down']:
                    behavior.action('button_up')
                behavior.tick()
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
    web.run_app(create_app(recorder=Recorder()), host='127.0.0.1', port=args.port, print=None,
        handle_signals=True)


if __name__ == '__main__':
    main()
