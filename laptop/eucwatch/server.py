"""Loopback-only application host; the browser never owns behavior time."""

import argparse
import asyncio
import secrets
from contextlib import suppress
from pathlib import Path

from aiohttp import web

from eucwatch import Application
from eucwatch.clock import SystemClock
from eucwatch.lease import Conflict, ControllerExpired, ControllerLease
from eucwatch.live import LiveSession
from eucwatch.live_control import LiveControl
from eucwatch.persistence import FileStore
from eucwatch.recording import Recorder
from eucwatch.scenarios import FileScenarioStore, ScenarioLibrary

ROOT = Path(__file__).resolve().parents[2]


def create_app(
    application=None,
    recorder=None,
    store=None,
    live=None,
    *,
    controller_timeout=10.0,
    result_limit=2048,
    scenario_store=None,
    clock=None,
):
    behavior = application or Application(
        store=store, event_sink=None if recorder is None else recorder.record
    )
    live = live or LiveSession(behavior)
    control = LiveControl(live, behavior)
    behavior.live_command_output = control.submit
    credential = secrets.token_urlsafe(32)
    lease = ControllerLease(
        behavior,
        live,
        ScenarioLibrary(scenario_store),
        clock or SystemClock(),
        recorder=recorder,
        timeout=controller_timeout,
        result_limit=result_limit,
    )

    def local(request):
        expected = f"{request.scheme}://{request.host}"
        origin = request.headers.get("Origin")
        if origin and origin != expected:
            raise web.HTTPForbidden(text="Untrusted origin")
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            raise web.HTTPForbidden(text="Cross-site access is unavailable")
        # DNS rebinding protection: host must name the loopback binding.
        if request.url.host not in ("127.0.0.1", "localhost", "::1"):
            raise web.HTTPForbidden(text="Loopback host required")

    async def state(request):
        local(request)
        try:
            lease.observe(request.query.get("controller"))
        except ControllerExpired as exc:
            raise web.HTTPForbidden(text=str(exc)) from None
        return web.json_response(lease.snapshot())

    async def session(request):
        local(request)
        controller = lease.acquire(
            request.query.get("controller"), request.query.get("document")
        )
        return web.json_response(
            {"credential": credential, "controller": controller},
            headers={"Cache-Control": "no-store"},
        )

    async def action(request):
        local(request)
        if request.headers.get("Origin") != f"{request.scheme}://{request.host}":
            raise web.HTTPForbidden(text="Same-origin control required")
        if not secrets.compare_digest(
            request.headers.get("X-EucWatch-Key", ""), credential
        ):
            raise web.HTTPForbidden(text="Launch credential required")
        try:
            payload = await request.json()
            return web.json_response(await lease.act(payload))
        except ControllerExpired as exc:
            raise web.HTTPForbidden(text=str(exc)) from None
        except Conflict as exc:
            return web.json_response({"error": str(exc)}, status=409)
        except (KeyError, TypeError, ValueError, OSError) as exc:
            return web.json_response({"error": str(exc)}, status=400)

    async def index(request):
        local(request)
        path = ROOT / "frontend/dist/index.html"
        if not path.is_file():
            return web.Response(
                text="Build frontend assets with ./scripts/setup.sh", status=503
            )
        return web.FileResponse(path, headers={"Cache-Control": "no-store"})

    async def recording(request):
        local(request)
        if not secrets.compare_digest(
            request.headers.get("X-EucWatch-Key", ""), credential
        ):
            raise web.HTTPForbidden(text="Launch credential required")
        if recorder is None:
            raise web.HTTPNotFound(text="Recording is not enabled")
        await recorder.drain()
        if recorder.status()["error"]:
            raise web.HTTPServiceUnavailable(text=recorder.status()["error"])
        if not recorder.path.is_file():
            raise web.HTTPNotFound(text="No captured events yet")
        return web.FileResponse(
            recorder.path,
            headers={
                "Content-Disposition": 'attachment; filename="wheel-recording.jsonl"'
            },
        )

    async def lifetime(app):
        async def run():
            while True:
                lease.tick()
                behavior.tick()
                live.tick()
                control.tick()
                await asyncio.sleep(0.02)

        async def write_recording():
            assert recorder is not None
            while True:
                await recorder.drain()
                await asyncio.sleep(0.05)

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
    app.add_routes(
        [
            web.get("/api/state", state),
            web.get("/api/session", session),
            web.post("/api/action", action),
            web.get("/api/recording", recording),
            web.get("/", index),
        ]
    )
    assets = ROOT / "frontend/dist/assets"
    if assets.is_dir():
        app.router.add_static("/assets/", assets)
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    web.run_app(
        create_app(
            recorder=Recorder(), store=FileStore(), scenario_store=FileScenarioStore()
        ),
        host="127.0.0.1",
        port=args.port,
        print=None,
        handle_signals=True,
    )


if __name__ == "__main__":
    main()
