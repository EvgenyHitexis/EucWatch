"""Loopback-only application host; the browser never owns behavior time."""

import argparse
import asyncio
import hashlib
import secrets
import time
from contextlib import suppress
from pathlib import Path

from aiohttp import web

from eucwatch import Application
from eucwatch.async_transfer import (
    AsyncConfigurationProtocol,
    AsyncConfigurationTransfer,
)
from eucwatch.live import LiveSession
from eucwatch.live_control import LiveControl
from eucwatch.nordic import NusTransport
from eucwatch.persistence import FileStore, MemoryStore
from eucwatch.recording import Recorder, Replay
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
    nus=None,
    nus_transfer_factory=None,
):
    behavior = application or Application(
        store=store, event_sink=None if recorder is None else recorder.record
    )
    live = live or LiveSession(behavior)
    nus = nus or NusTransport(behavior, live)
    simulated_transfer = behavior.transfer
    target_stores = {}
    real_transfers = {}
    scenarios = ScenarioLibrary(scenario_store)
    control = LiveControl(live, behavior)
    behavior.live_command_output = control.submit
    credential = secrets.token_urlsafe(32)
    controllers = set()
    results = {}
    seen = set()
    intent_lock = asyncio.Lock()
    last_ui_seen = time.monotonic()
    nus_cleanup = None

    def expire_controller():
        if controllers and time.monotonic() - last_ui_seen > controller_timeout:
            controllers.clear()
            results.clear()
            seen.clear()
            if behavior.view()["button"]["down"]:
                behavior.action("button_up")

    def snapshot():
        return {
            **behavior.view(),
            "recording": None if recorder is None else recorder.status(),
            "live": live.status(),
            "scenario": scenarios.view(),
            "nordic": nus.status(),
        }

    def target_transfer(address):
        existing = real_transfers.get(address)
        if existing is not None and (
            existing.active
            or existing.pending is not None
            or existing.journal_error is not None
            or existing.status == "return_failed"
        ):
            return existing
        protocol = AsyncConfigurationProtocol(nus.exchange)
        if nus_transfer_factory is not None:
            transfer = nus_transfer_factory(address, protocol)
            real_transfers[address] = transfer
            return transfer
        if address not in target_stores:
            if isinstance(behavior.store, FileStore):
                identity = hashlib.sha256(address.encode()).hexdigest()
                directory = behavior.store.path.parent / "watch-targets" / identity
                target_stores[address] = (
                    FileStore(directory / "shared.json"),
                    FileStore(directory / "journal.json"),
                )
            else:
                target_stores[address] = (MemoryStore(), MemoryStore())
        shared, journal = target_stores[address]
        name = next(
            (
                device["name"]
                for device in nus.status()["devices"]
                if device["address"] == address
            ),
            address,
        )
        transfer = AsyncConfigurationTransfer(
            behavior.store,
            shared,
            protocol,
            endpoint_label=f"Actual watch · {name} · {address}",
            journal_store=journal,
        )
        real_transfers[address] = transfer
        return transfer

    async def finish_real_transfer():
        await nus.disconnect()
        if nus.client is not None:
            behavior.transfer.active = True
            behavior.transfer.status = "return_failed"
            behavior.transfer.error = "Watch disconnect remains uncertain; complete explicit disconnect before returning to wheel mode"
            return
        behavior.action("transfer_exit")
        if behavior.mode == "live" and live.selected:
            await live.connect(live.selected)

    async def real_transfer_action(name, payload):
        transfer = behavior.transfer
        if (
            not isinstance(transfer, AsyncConfigurationTransfer)
            or behavior.mode != "transfer"
            or not transfer.active
        ):
            raise ValueError("Select a real watch inside configuration transfer first")
        committed = None
        if name == "transfer_preview":
            await transfer.areview(behavior.config)
        elif name == "transfer_send":
            committed = await transfer.asend(behavior.config)
        elif name == "transfer_reconcile":
            committed = await transfer.areconcile(behavior.config)
        elif name == "transfer_cancel":
            await transfer.acancel()
        elif name == "transfer_return":
            await transfer.areturn()
        else:
            raise ValueError("Unknown asynchronous transfer action")
        if committed is not None:
            behavior.action("transfer_activate", config=committed)
        elif (
            transfer.local_saved is not None and transfer.local_saved != behavior.config
        ):
            behavior.action("transfer_activate", config=transfer.local_saved)
        behavior.feedback = transfer.error or (
            "Configuration transferred · saved readback verified"
            if transfer.verified_saved is not None
            else "Configuration transfer"
        )
        if not transfer.active:
            await finish_real_transfer()
        return snapshot()

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
        nonlocal last_ui_seen
        local(request)
        expire_controller()
        if (
            request.query.get("controller")
            and request.query["controller"] not in controllers
        ):
            raise web.HTTPForbidden(text="Controller expired; reacquire current state")
        if request.query.get("controller") in controllers:
            last_ui_seen = time.monotonic()
        return web.json_response(snapshot())

    async def session(request):
        nonlocal last_ui_seen
        local(request)
        expire_controller()
        controller = request.query.get("controller")
        if controller not in controllers:
            if controllers:
                controller = None
            else:
                controller = secrets.token_urlsafe(16)
                controllers.add(controller)
        if controller is not None:
            last_ui_seen = time.monotonic()
        return web.json_response(
            {"credential": credential, "controller": controller},
            headers={"Cache-Control": "no-store"},
        )

    async def action(request):
        nonlocal last_ui_seen
        local(request)
        if request.headers.get("Origin") != f"{request.scheme}://{request.host}":
            raise web.HTTPForbidden(text="Same-origin control required")
        if not secrets.compare_digest(
            request.headers.get("X-EucWatch-Key", ""), credential
        ):
            raise web.HTTPForbidden(text="Launch credential required")
        try:
            payload = await request.json()
            expire_controller()
            controller, identity = payload.pop("controller"), payload.pop("id")
            name = payload.pop("action")
            if not isinstance(name, str) or len(name) > 64:
                raise ValueError("Application action name required")
            if name in (
                "live_start",
                "live_connected",
                "live_disconnected",
                "command_result",
                "horn_result",
                "transfer_activate",
                "transfer_exit",
            ):
                raise ValueError("Transport callbacks are internal application inputs")
            if (
                controller not in controllers
                or not isinstance(identity, str)
                or not identity
                or len(identity) > 128
            ):
                raise ValueError("Valid controller and request identity required")
            last_ui_seen = time.monotonic()
            key = (controller, identity)
            async with intent_lock:
                if controller not in controllers:
                    raise web.HTTPForbidden(
                        text="Controller expired while action was waiting"
                    )
                if key in results:
                    return web.json_response(results[key])
                if key in seen:
                    return web.json_response(
                        {
                            "error": "Duplicate action was already processed; its response expired"
                        },
                        status=409,
                    )
                epoch = payload.pop("epoch", None)
                if type(epoch) is not int or epoch != behavior.session:
                    return web.json_response(
                        {"error": "Application session changed; refresh before acting"},
                        status=409,
                    )
                if behavior.transfer.active and (
                    name.startswith("live_")
                    or name
                    in (
                        "simulator_start",
                        "connect",
                        "stop",
                        "disconnect",
                        "replay_start",
                        "scenario_start",
                        "scenario_step",
                    )
                ):
                    raise ValueError(
                        "Return from configuration transfer before changing input roles"
                    )
                if name.startswith("nordic_"):
                    if (
                        behavior.mode != "transfer"
                        or not behavior.transfer.active
                        or live.client is not None
                        or live.desired
                    ):
                        raise ValueError(
                            "Enter stopped transfer and complete the wheel disconnect first"
                        )
                    if name == "nordic_discover":
                        await nus.discover()
                    elif name == "nordic_select":
                        previous = behavior.transfer
                        await nus.connect(payload["address"])
                        transfer = target_transfer(payload["address"])
                        if previous is not transfer:
                            previous.leave()
                        transfer.begin(
                            behavior.config,
                            previous.previous_mode,
                            previous.previous_simulating,
                        )
                        behavior.transfer = transfer
                        if (
                            transfer.pending is None
                            and transfer.journal_error is None
                            and transfer.verified_saved is None
                        ):
                            await transfer.areview(behavior.config)
                    elif name == "nordic_disconnect":
                        await nus.disconnect()
                    else:
                        raise ValueError("Unknown Nordic UART action")
                    result = snapshot()
                elif isinstance(
                    behavior.transfer, AsyncConfigurationTransfer
                ) and name in (
                    "transfer_preview",
                    "transfer_send",
                    "transfer_reconcile",
                    "transfer_cancel",
                    "transfer_return",
                ):
                    result = await real_transfer_action(name, payload)
                elif name.startswith("scenario_"):
                    if name == "scenario_save":
                        scenarios.save_current(
                            behavior.simulator.values,
                            payload.get("name"),
                            payload.get("steps"),
                        )
                    elif name == "scenario_review":
                        scenarios.review(payload.get("content"))
                    elif name == "scenario_export":
                        scenarios.export()
                    elif name == "scenario_start":
                        scenarios.export()  # Validate a complete definition before disconnecting.
                        if behavior.transfer.active:
                            raise ValueError(
                                "Return from transfer before starting a scenario"
                            )
                        await live.disconnect()
                        scenarios.start(behavior)
                    elif name == "scenario_step":
                        scenarios.step(behavior)
                    else:
                        raise ValueError("Unknown scenario action")
                    result = snapshot()
                elif name == "live_discover":
                    await live.discover()
                    result = snapshot()
                elif name == "live_select":
                    await live.connect(payload["address"])
                    result = snapshot()
                elif name == "live_disconnect":
                    await live.disconnect()
                    result = snapshot()
                elif name == "transfer_begin":
                    if behavior.transfer.active:
                        raise ValueError("Configuration transfer is already active")
                    behavior.transfer = simulated_transfer
                    # Validate the fresh stopped entry before ending the wheel link.
                    behavior.action(name, **payload)
                    await live.disconnect()
                    result = snapshot()
                else:
                    if name in (
                        "simulator_start",
                        "connect",
                        "stop",
                        "disconnect",
                        "replay_start",
                    ):
                        await live.disconnect()
                    if name == "replay_start":
                        payload["recording"] = Replay.from_text(
                            payload["recording"],
                            name=payload.pop("name", "Imported recording"),
                        )
                    if name.startswith("transfer_") and live.client is not None:
                        raise ValueError(
                            "Wheel disconnect outcome is uncertain; complete disconnect before configuration transfer"
                        )
                    behavior.action(name, **payload)
                    result = snapshot()
                    if (
                        name
                        in ("transfer_send", "transfer_return", "transfer_reconcile")
                        and not behavior.transfer.active
                        and behavior.mode == "live"
                        and live.selected
                    ):
                        await live.connect(live.selected)
                        result = snapshot()
                results[key] = result
                seen.add(key)
                if len(results) > result_limit:
                    del results[next(iter(results))]
                return web.json_response(result)
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

    async def websocket(request):
        local(request)
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        try:
            while not ws.closed:
                await ws.send_json(snapshot())
                await asyncio.sleep(0.2)
        finally:
            await ws.close()
        return ws

    async def lifetime(app):
        async def run():
            nonlocal nus_cleanup
            while True:
                expire_controller()
                if (
                    time.monotonic() - last_ui_seen > 2
                    and behavior.view()["button"]["down"]
                ):
                    behavior.action("button_up")
                behavior.tick()
                live.tick()
                control.tick()
                nus.tick()
                if (
                    nus.session is not None
                    and nus_cleanup is not None
                    and nus_cleanup.done()
                ):
                    nus_cleanup = None
                if (
                    nus.client is not None
                    and nus.session is None
                    and nus_cleanup is None
                ):
                    nus_cleanup = asyncio.create_task(nus.disconnect())
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
        if nus_cleanup is not None:
            with suppress(asyncio.CancelledError):
                await nus_cleanup
        await nus.close()
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
            web.get("/api/ws", websocket),
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
