"""Loopback-only application host; the browser never owns behavior time."""
import argparse
import asyncio
from contextlib import suppress
from pathlib import Path
import secrets

from aiohttp import web

from eucwatch import Application

ROOT = Path(__file__).resolve().parents[2]


def create_app(application=None):
    behavior = application or Application()
    credential = secrets.token_urlsafe(32)
    controllers = set()
    results = {}

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
        local(request)
        return web.json_response(behavior.view())

    async def session(request):
        local(request)
        controller = request.query.get('controller')
        if controller not in controllers:
            if controllers:
                controller = None
            else:
                controller = secrets.token_urlsafe(16)
                controllers.add(controller)
        return web.json_response({'credential': credential, 'controller': controller},
            headers={'Cache-Control': 'no-store'})

    async def action(request):
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
            key = (controller, identity)
            if key in results:
                return web.json_response(results[key])
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

    async def websocket(request):
        local(request)
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        try:
            while not ws.closed:
                await ws.send_json(behavior.view())
                await asyncio.sleep(.2)
        finally:
            await ws.close()
        return ws

    async def lifetime(app):
        async def run():
            while True:
                behavior.tick()
                await asyncio.sleep(.02)
        task = asyncio.create_task(run())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    app = web.Application(client_max_size=128 * 1024)
    app.cleanup_ctx.append(lifetime)
    app.add_routes([web.get('/api/state', state), web.get('/api/session', session),
        web.post('/api/action', action), web.get('/api/ws', websocket), web.get('/', index)])
    assets = ROOT / 'frontend/dist/assets'
    if assets.is_dir():
        app.router.add_static('/assets/', assets)
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    web.run_app(create_app(), host='127.0.0.1', port=args.port, print=None,
        handle_signals=True)


if __name__ == '__main__':
    main()
