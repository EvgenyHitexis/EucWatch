"""Read-only Wheel recording replay through the file input (#24)."""
from pathlib import Path

from support import main, served_laptop, write_evidence


async def run():
    async with served_laptop() as laptop:
        page, behavior = laptop.page, laptop.app
        before_replay = behavior.view()['diagnostics']['valid_frames']
        await page.choose_files('#replay-file', Path('experiments/laptop-feasibility/evidence/fixture-recording.jsonl').resolve())
        await page.click('#replay-load')
        await page.wait("document.querySelector('#mode').textContent.includes('REPLAY')")
        for count in range(1,14):
            await page.click('#replay-step')
            await page.wait(f"document.querySelector('#replay-progress').textContent.includes('{count} / 13')")
        await page.label('battery 97 percent')
        replay_result = {'issue':24, 'provenance':'actual file import / Canvas / aiohttp / read-only replay',
            'expected':'13 preserved notifications; three valid source frames; final voltage-derived97% and avg4.09V',
            'observed':await page.description(),
            'valid_frames':behavior.view()['diagnostics']['valid_frames']-before_replay,
            'recording':behavior.view()['replay']}
        assert replay_result['valid_frames'] == 3
        assert await page.evaluate("document.querySelector('[data-action=simulator_emit]').disabled")
        await page.evaluate("window.savedFileText=File.prototype.text; File.prototype.text=function(){return new Promise(resolve=>{window.finishFileRead=()=>window.savedFileText.call(this).then(resolve)})}; document.querySelector('#replay-load').click()")
        await page.wait("typeof window.finishFileRead === 'function'")
        await page.evaluate("document.querySelector('[data-action=simulator_start]').click()")
        await page.wait("document.querySelector('#mode').textContent === 'SIMULATOR' && !document.querySelector('[data-action=simulator_start]').disabled")
        newer_session = behavior.view()['session']
        await page.evaluate("window.finishFileRead(); File.prototype.text=window.savedFileText")
        await page.wait("!document.querySelector('#replay-load').disabled")
        assert behavior.view()['mode']=='simulator' and behavior.view()['session']==newer_session
        replay_result['delayed_file_after_new_session']='discarded'
    write_evidence(laptop.output / 'replay.json', replay_result)
    print('replay: passed')


if __name__ == '__main__':
    main(run)
