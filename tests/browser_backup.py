"""Local Watch configuration backup, review, Cancel and restore, and no transfer UI (#27, #40).

overtaken_export: Export reports success when a poll's state read supersedes the action's own (#75).
missing_export: Export that gets no export back says so and downloads nothing (#77).
stale_export: Export whose state read fails downloads this action's export, not an earlier one (#77).
"""
import asyncio
import hashlib
import json
from pathlib import Path

from support import main, served_laptop, start_simulator, write_evidence

# The server answers the state read that the Export action makes after its POST, but the page receives that answer
# only once the next poll has started a read of its own. The poll's answer arrives 300 ms after that. The poll's read
# supersedes the action's, so Export has to wait for the poll's answer before it looks for the export.
# The POST goes out only once a poll's read has been handled, so the page holds a view from before the export and the
# next poll is 200 ms away. If a read is still in flight when the action's read starts, holding the action's read
# would stall the poll behind it: that attempt is let through and reported as missed.
OVERTAKE_EXPORT_READ = """(()=>{
  const send=window.fetch.bind(window);
  let reading=0, pollHandled=null, holdNextRead=false, release=null;
  window.overtake='idle';
  // A state read is in flight until the page has handled its view, in the microtasks after its json() settles:
  // a task queued then runs after them.
  const read=async(input,init)=>{
    reading++;
    let response;
    try { response=await send(input,init); } catch(error){ reading--; throw error; }
    const json=response.json.bind(response);
    response.json=()=>json().finally(()=>setTimeout(()=>{
      reading--;
      if(pollHandled){ const handled=pollHandled; pollHandled=null; handled(); }
    },0));
    return response;
  };
  window.fetch=async(input,init)=>{
    const url=String(input);
    if(init?.method==='POST' && JSON.parse(init.body).action==='configuration_export'){
      await new Promise(resolve=>{pollHandled=resolve;});
      const response=await send(input,init);
      holdNextRead=true;
      return response;
    }
    if(!url.startsWith('/api/state')) return send(input,init);
    if(holdNextRead){
      holdNextRead=false;
      if(reading){ window.overtake='missed'; return read(input,init); }
      const response=await read(input,init);
      await new Promise(resolve=>{release=resolve;});
      return response;
    }
    if(release){
      const response=read(input,init);
      release(); release=null;
      await new Promise(resolve=>setTimeout(resolve,300));
      window.overtake='overtaken';
      return response;
    }
    return read(input,init);
  };
})()"""

# Every answer the page receives, the Export action's and every state read's, comes back without an export.
DROP_EXPORT = """(()=>{
  const send=window.fetch.bind(window);
  window.fetch=async(input,init)=>{
    const url=String(input);
    const response=await send(input,init);
    if(!url.startsWith('/api/state') && !(init?.method==='POST' && JSON.parse(init.body).action==='configuration_export')) return response;
    const view=await response.json();
    return new Response(JSON.stringify({...view,configuration_export:null}),{status:response.status,headers:response.headers});
  };
})()"""

# The state read that the Export action makes after its POST fails, as a dropped connection would.
FAIL_READ_AFTER_EXPORT = """(()=>{
  const send=window.fetch.bind(window);
  let failNextRead=false;
  window.fetch=async(input,init)=>{
    const url=String(input);
    if(init?.method==='POST' && JSON.parse(init.body).action==='configuration_export'){
      const response=await send(input,init);
      failNextRead=true;
      return response;
    }
    if(failNextRead && url.startsWith('/api/state')){ failNextRead=false; throw new TypeError('state read failed'); }
    return send(input,init);
  };
})()"""


async def allow_downloads(page, directory):
    directory.mkdir(parents=True, exist_ok=True)
    await page.browser.call('Browser.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': str(directory)})


async def downloaded(directory):
    async with asyncio.timeout(5):
        while not (directory/'eucwatch-configuration.json').exists():
            await asyncio.sleep(.05)
    return json.loads((directory/'eucwatch-configuration.json').read_text())


async def run():
    async with served_laptop() as laptop:
        page, behavior, output = laptop.page, laptop.app, laptop.output
        await start_simulator(page)
        download_dir=(output/f'downloads-{laptop.run_id}').resolve()
        download_dir.mkdir(exist_ok=True)
        await page.browser.call('Browser.setDownloadBehavior',{'behavior':'allow','downloadPath':str(download_dir)})
        await page.click('#configuration-export')
        await page.wait("document.querySelector('#configuration-status').textContent.includes('Exported')")
        async with asyncio.timeout(5):
            while not (download_dir/'eucwatch-configuration.json').exists():
                await asyncio.sleep(.05)
        exported=json.loads((download_dir/'eucwatch-configuration.json').read_text())
        assert set(exported)=={'version','revision','presets','alerts'}
        before_backup=behavior.view()['config']
        before_commands=len(behavior.view()['command_events'])
        candidate=json.loads(json.dumps(exported))
        candidate['presets'][0]['name']='Backup slot'
        config_file=(output/'import-configuration.json').resolve()
        config_file.write_text(json.dumps(candidate))
        await page.choose_files('#configuration-file', config_file)
        async def review_configuration():
            await page.click('#configuration-review')
            await page.wait("document.querySelector('#configuration-preview').textContent.includes('Backup slot')")
        await review_configuration()
        assert behavior.view()['config']==before_backup
        await page.click('#configuration-cancel')
        await page.wait("document.querySelector('#configuration-preview').textContent===''")
        assert behavior.view()['config']==before_backup
        await review_configuration()
        await page.click('#configuration-restore')
        await page.wait("document.querySelector('#configuration-status').textContent.includes('restored locally')")
        assert behavior.view()['config']['presets'][0]['name']=='Backup slot'
        assert len(behavior.view()['command_events'])==before_commands
        assert behavior.view()['confirmed_preset'] is None
        invalid_file=(output/'invalid-configuration.json').resolve()
        candidate['version']=999
        invalid_file.write_text(json.dumps(candidate))
        await page.choose_files('#configuration-file', invalid_file)
        await page.click('#configuration-review')
        await page.wait("document.querySelector('#message').textContent.includes('Unsupported')")
        assert behavior.view()['config']['presets'][0]['name']=='Backup slot'
        backup_result={'issue':27,'provenance':'actual file download/import/review/Cancel/Restore / HTML / aiohttp',
            'expected':'saved-only export, preview noactivation, Cancelpreserves, explicitrestore, unknownversionrefused, no commands',
            'observed':'passed','migration':'Schema 2 export; schema 1 migration is explicit; compatible updates preserve meaning; unknown versions require review'}
        write_evidence(output/'backup.json', backup_result)
        await page.pointer((120,10),(120,110))
        await page.screen('settings')
        assert await page.evaluate("!document.querySelector('[id^=transfer-],[id^=nordic-]')")
        assert await page.evaluate("!/transfer|synchron|reconcil|conflict/i.test(document.querySelector('.panel').innerText + document.querySelector('#watch').getAttribute('aria-label'))")
        before_removed_touch=behavior.view()
        await page.tap(120,215)
        await page.screen('preset_slots')
        assert behavior.view()['config']==before_removed_touch['config']
        assert behavior.view()['session']==before_removed_touch['session']
        assert behavior.view()['connected']==before_removed_touch['connected']
        await page.pointer((120,215),(120,20))
        await page.screen('settings')
        write_evidence(output/'local-configuration-browser.json', {
            'issue':40,
            'provenance':'built Canvas and HTML panel / Chrome CDP / aiohttp / simulated wheel',
            'expected':'no transfer, synchronization or conflict entries; former touch opens local Presets without changing configuration or wheel session; upward return and local backup/import/restore remain usable',
            'observed':'passed; saved Backup slot and preferences preserved; backup export, review, Cancel, restore and invalid-import refusal exercised earlier in this flow',
            'source_sha256':{source:hashlib.sha256(Path(source).read_bytes()).hexdigest() for source in ['frontend/src/main.ts','frontend/src/backup.ts','laptop/eucwatch/server.py','tests/browser_backup.py']},
            'physical_operation':'none'
        })
        await page.pointer((120,215),(120,20))
        await page.screen('dashboard')
    print('backup: passed')


async def overtaken_export():
    async with served_laptop() as laptop:
        page = laptop.page
        await start_simulator(page)
        await page.browser.call('Browser.setDownloadBehavior', {'behavior': 'deny'})
        await page.evaluate(OVERTAKE_EXPORT_READ)
        for _ in range(5):
            await page.evaluate("window.overtake='idle';document.querySelector('#configuration-status').textContent=''")
            await page.click('#configuration-export')
            await page.wait("window.overtake==='overtaken'||window.overtake==='missed'")
            if await page.evaluate("window.overtake==='overtaken'"):
                break
        else:
            raise AssertionError('a state read was in flight whenever the Export read started')
        await page.wait("document.querySelector('#configuration-status').textContent.includes('Exported')")
    print('backup overtaken export: passed')


async def missing_export():
    async with served_laptop() as laptop:
        page, output = laptop.page, laptop.output
        await start_simulator(page)
        download_dir=(output/f'downloads-missing-{laptop.run_id}').resolve()
        await allow_downloads(page, download_dir)
        await page.evaluate(DROP_EXPORT)
        await page.click('#configuration-export')
        await page.wait("document.querySelector('#configuration-status').textContent.includes('Export did not complete')")
        await asyncio.sleep(.5)
        assert not list(download_dir.iterdir()), list(download_dir.iterdir())
    print('backup missing export: passed')


async def stale_export():
    async with served_laptop() as laptop:
        page, behavior, output = laptop.page, laptop.app, laptop.output
        await start_simulator(page)
        first_dir=(output/f'downloads-first-{laptop.run_id}').resolve()
        await allow_downloads(page, first_dir)
        await page.click('#configuration-export')
        await page.wait("document.querySelector('#configuration-status').textContent.includes('Exported')")
        first=await downloaded(first_dir)
        # Restore a changed configuration, so this Export's content differs from the earlier one.
        candidate=json.loads(json.dumps(first))
        candidate['presets'][0]['name']='Stale check'
        config_file=(output/f'stale-configuration-{laptop.run_id}.json').resolve()
        config_file.write_text(json.dumps(candidate))
        await page.choose_files('#configuration-file', config_file)
        await page.click('#configuration-review')
        await page.wait("document.querySelector('#configuration-preview').textContent.includes('Stale check')")
        await page.click('#configuration-restore')
        await page.wait("document.querySelector('#configuration-status').textContent.includes('restored locally')")
        await page.evaluate("document.querySelector('#configuration-status').textContent=''")
        second_dir=(output/f'downloads-second-{laptop.run_id}').resolve()
        await allow_downloads(page, second_dir)
        await page.evaluate(FAIL_READ_AFTER_EXPORT)
        await page.click('#configuration-export')
        await page.wait("document.querySelector('#configuration-status').textContent.includes('Exported')")
        second=await downloaded(second_dir)
        assert second['presets'][0]['name']=='Stale check', second['presets'][0]['name']
        assert second['revision']==behavior.view()['config']['revision']
    print('backup stale export: passed')


if __name__ == '__main__':
    main(run, overtaken_export, missing_export, stale_export)
