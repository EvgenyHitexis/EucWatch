"""Host suspend and resume while a Riding preset is applying (#30)."""
from support import (main, save_ab_2, select_second_preset, send_readings, served_laptop,
                     start_simulator, write_evidence)


async def run():
    async with served_laptop() as laptop:
        page, behavior, host_clock = laptop.page, laptop.app, laptop.clock
        save_ab_2(behavior)
        await start_simulator(page)
        await send_readings(page, 25, 138, 45)
        await select_second_preset(page)
        await page.wait("document.querySelector('#preset-outcome').textContent.includes('Applying')")
        before_resume=behavior.view()
        host_clock.advance(60,suspended=True)
        await page.wait("document.querySelector('#watch').dataset.fresh==='false' && !document.querySelector('#preset-outcome').textContent.includes('Applying')")
        after_resume=behavior.view()
        assert after_resume['session']>before_resume['session']
        assert after_resume['elapsed_s']==before_resume['elapsed_s']
        assert len(after_resume['command_events'])>=len(before_resume['command_events'])
        submitted_before=[row for row in before_resume['command_events'] if row['event']=='submission']
        submitted_after=[row for row in after_resume['command_events'] if row['event']=='submission']
        assert submitted_after==submitted_before
        behavior.receive(before_resume['session'],b''.join(behavior.simulator.notifications(now=after_resume['elapsed_s'])))
        assert not behavior.view()['fresh']
        resume_result={'issue':30,'provenance':'actual Canvas pending preset / controlled simulator clock / independent synthetic host suspend / aiohttp',
            'expected':'host resume invalidates source and pending intent even with paused virtual time; late old frame cannot recover; no overdue command',
            'observed':'passed','physical_suspend':'omitted by owner'}
    write_evidence(laptop.output/'resume.json', resume_result)
    print('resume: passed')


if __name__ == '__main__':
    main(run)
