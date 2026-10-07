"""Synthetic Python session with a tiny read-only browser view, under Xvfb.

No BLE imports or application command endpoints. No production UI/launcher.
"""

import asyncio
from contextlib import suppress
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time

from aiohttp import ClientSession, web

from probe import CHUNKS, CHARACTERISTIC, Core, clocks

HTML = """<!doctype html><title>Session feasibility probe</title>
<pre id="state">waiting</pre><script>
window.polls = 0; window.events = [];
for (const name of ['visibilitychange', 'freeze', 'resume']) {
  document.addEventListener(name, () => window.events.push({
    name, visibility: document.visibilityState, at: performance.now(), polls: window.polls
  }));
}
async function refresh() {
  const r = await fetch('/state'); window.snapshot = await r.json();
  document.getElementById('state').textContent = JSON.stringify(window.snapshot);
  window.polls++;
}
refresh(); setInterval(refresh, 100);
</script>"""


class CDP:
    """Serial direct protocol client; no focus/lifecycle emulation defaults."""

    def __init__(self, websocket):
        self.websocket = websocket
        self.sequence = 0

    async def call(self, method, params=None, session=None):
        self.sequence += 1
        message = {"id": self.sequence, "method": method, "params": params or {}}
        if session:
            message["sessionId"] = session
        await self.websocket.send_json(message)
        async with asyncio.timeout(10):
            while True:
                response = await self.websocket.receive_json()
                if response.get("id") == self.sequence:
                    if "error" in response:
                        raise RuntimeError(response["error"])
                    return response.get("result", {})

    async def page(self, url):
        target = await self.call("Target.createTarget", {"url": url})
        attached = await self.call("Target.attachToTarget", {
            "targetId": target["targetId"], "flatten": True})
        return Page(self, target["targetId"], attached["sessionId"])


class Page:
    def __init__(self, cdp, target, session):
        self.cdp, self.target, self.session = cdp, target, session

    async def evaluate(self, expression):
        response = await self.cdp.call("Runtime.evaluate", {
            "expression": expression, "returnByValue": True}, self.session)
        if "exceptionDetails" in response:
            raise RuntimeError(response["exceptionDetails"])
        return response["result"].get("value")

    async def wait(self, expression):
        async with asyncio.timeout(10):
            while not await self.evaluate(expression):
                await asyncio.sleep(0.1)

    async def front(self):
        await self.cdp.call("Target.activateTarget", {"targetId": self.target})

    async def close(self):
        await self.cdp.call("Target.closeTarget", {"targetId": self.target})


async def main():
    output = Path("output")
    output.mkdir(exist_ok=True)
    core = Core(clocks)
    started = clocks()[0]
    receipt_times = []
    feed_enabled = True
    log = (output / "browser-recording.jsonl").open("w")

    async def feed():
        seq = 0
        while True:
            core.tick()
            if feed_enabled:
                chunk = CHUNKS[seq % len(CHUNKS)]
                stamp = clocks()[0] - started
                receipt_times.append(stamp)
                log.write(json.dumps({"schema": 1, "source": "synthetic",
                    "session": "browser-probe", "sequence": seq,
                    "characteristic": CHARACTERISTIC,
                    "receipt_elapsed_s": stamp, "raw_hex": chunk.hex()}) + "\n")
                log.flush()
                core.receive(core.epoch, chunk)
                seq += 1
            await asyncio.sleep(0.02)

    async def index(_request):
        return web.Response(text=HTML, content_type="text/html")

    async def state(_request):
        return web.json_response({"session": "browser-probe", "frames": core.frames,
            "notifications": len(receipt_times), "fresh": core.fresh(),
            "values": core.values})

    app = web.Application()
    app.add_routes([web.get("/", index), web.get("/state", state)])
    runner = web.AppRunner(app)
    await runner.setup()
    # Reserve a loopback ephemeral port explicitly, avoiding private aiohttp APIs.
    import socket
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    site = web.SockSite(runner, sock)
    await site.start()
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    task = asyncio.create_task(feed())
    launch_args = ["--no-first-run", "--no-default-browser-check", "--disable-sync",
                   "--disable-background-networking", "--remote-debugging-port=0"]
    result = {"source": "synthetic", "headless": False, "display": "Xvfb",
              "driver": "direct CDP", "chrome_args": launch_args,
              "focus_emulation": False, "background_throttling_disabled": False,
              "actual_system_suspend_tested": False}
    try:
        with tempfile.TemporaryDirectory(prefix="eucwatch-chrome-") as profile:
            browser = subprocess.Popen(
                ["google-chrome", *launch_args, f"--user-data-dir={profile}", "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                port_file = Path(profile) / "DevToolsActivePort"
                async with asyncio.timeout(10):
                    while not port_file.exists():
                        await asyncio.sleep(0.1)
                port, path = port_file.read_text().splitlines()
                async with ClientSession() as client:
                    async with client.ws_connect(f"http://127.0.0.1:{port}{path}") as ws:
                        cdp = CDP(ws)
                        result["browser_version"] = (await cdp.call("Browser.getVersion"))["product"]
                        page = await cdp.page(url)
                        await page.wait("window.snapshot && window.snapshot.fresh")
                        initial = await page.evaluate("window.snapshot")
                        other = await cdp.page("about:blank")
                        await other.front()
                        await page.wait("document.visibilityState === 'hidden'")
                        before_hidden = core.frames
                        await asyncio.sleep(3)
                        visibility = await page.evaluate("document.visibilityState")
                        assert visibility == "hidden"
                        assert core.frames > before_hidden
                        result["hidden"] = {"visibility": visibility, "seconds": 3,
                                            "additional_frames": core.frames - before_hidden}

                        before_freeze = core.frames
                        await cdp.call("Page.setWebLifecycleState", {"state": "frozen"}, page.session)
                        await asyncio.sleep(2)
                        assert core.frames > before_freeze
                        await cdp.call("Page.setWebLifecycleState", {"state": "active"}, page.session)
                        await page.front()
                        await page.wait("window.events.some(e => e.name === 'resume')")
                        events = await page.evaluate("window.events")
                        frozen = next(e for e in events if e["name"] == "freeze")
                        resumed = next(e for e in events if e["name"] == "resume")
                        assert frozen["polls"] == resumed["polls"]
                        result["forced_freeze"] = {"seconds": 2,
                            "additional_frames": core.frames - before_freeze,
                            "events": events, "frontend_polls_stopped": True}

                        before_reload = core.frames
                        await cdp.call("Page.reload", session=page.session)
                        # Wait for the new document to replace the previous snapshot.
                        await asyncio.sleep(0.3)
                        await page.wait("window.snapshot && window.snapshot.fresh")
                        snapshot = await page.evaluate("window.snapshot")
                        assert snapshot["session"] == initial["session"]
                        assert snapshot["frames"] >= before_reload
                        result["reload"] = {"same_session": True,
                            "frames_before": before_reload, "frames_after": snapshot["frames"]}

                        feed_enabled = False
                        await page.wait("window.snapshot && !window.snapshot.fresh")
                        result["paused_feed"] = await page.evaluate("window.snapshot")
                        feed_enabled = True
                        await page.wait("window.snapshot && window.snapshot.fresh")
                        result["resumed_feed_fresh"] = True

                        await page.close()
                        await other.close()
                        before_close = core.frames
                        await asyncio.sleep(1)
                        assert core.frames > before_close
                        result["probe_pages_closed"] = {"additional_frames": core.frames - before_close}
            finally:
                browser.terminate()
                try:
                    await asyncio.to_thread(browser.wait, timeout=5)
                except subprocess.TimeoutExpired:
                    browser.kill()
                    await asyncio.to_thread(browser.wait)
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        log.close()
        await runner.cleanup()
    rows = [json.loads(line) for line in (output / "browser-recording.jsonl").read_text().splitlines()]
    assert len(rows) == len(receipt_times)
    assert all(row["sequence"] == i for i, row in enumerate(rows))
    assert all(row["raw_hex"] == CHUNKS[i % 5].hex() for i, row in enumerate(rows))
    assert all(a <= b for a, b in zip(receipt_times, receipt_times[1:]))
    result.update({"status": "pass", "notifications": len(rows),
        "valid_frames": core.frames, "recording_order_and_bytes_verified": True,
        "recording_sha256": hashlib.sha256((output / "browser-recording.jsonl").read_bytes()).hexdigest(),
        "total_duration_s": clocks()[0] - started})
    (output / "browser.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
