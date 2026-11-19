"""support.chrome() waits for the whole DevToolsActivePort file (#79).

Chrome creates the file before it writes the port and path. A fake google-chrome on PATH does the same, with a
pause between the two, and serves the DevTools websocket, so no real Chrome is needed.
"""
import asyncio
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support

FAKE_CHROME = '''#!{python}
import asyncio, sys
from pathlib import Path
from aiohttp import web

async def devtools(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    async for _ in ws:
        pass
    return ws

async def main():
    profile = next(arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('--user-data-dir='))
    app = web.Application()
    app.router.add_get('/devtools/browser/fake', devtools)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    port_file = Path(profile) / 'DevToolsActivePort'
    port_file.write_text('')
    await asyncio.sleep(.5)
    port_file.write_text(f'{{port}}\\n/devtools/browser/fake\\n')
    await asyncio.Event().wait()

asyncio.run(main())
'''


class ChromeStartupTests(unittest.TestCase):
    def test_waits_for_port_and_path_after_the_file_appears(self):
        with tempfile.TemporaryDirectory(prefix='eucwatch-fake-chrome-') as bin_dir:
            fake = Path(bin_dir) / 'google-chrome'
            fake.write_text(FAKE_CHROME.format(python=sys.executable))
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

            async def start():
                async with support.chrome() as browser:
                    return browser

            with mock.patch.dict(os.environ, {'PATH': bin_dir + os.pathsep + os.environ['PATH']}):
                browser = asyncio.run(start())
            self.assertIsInstance(browser, support.Browser)


if __name__ == '__main__':
    unittest.main()
