export interface TransferView {
  active: boolean; endpoint: string; status: string; error: string | null;
  watch_revision: number; watch_config: unknown;
  scenario?: { stage: string; commit: string; readback: string };
  preview: null | {
    laptop_revision: number; watch_revision: number; base_revision?: number | null; candidate: unknown;
    changes: { path: string; watch: unknown; proposed: unknown }[];
    conflicts: { path: string; laptop: unknown; watch: unknown }[];
    choices: Record<string, string | null>;
  };
}

export function mountTransfer(action: (name: string, payload?: Record<string, unknown>) => Promise<boolean>, getView: () => TransferView | undefined): (enabled: boolean) => void {
  const section = document.createElement('section');
  section.innerHTML = `<div class="divider"></div><h2>Configuration transfer</h2>
    <p class="intro">Open Transfer configuration in watch Settings while stopped. This endpoint is a simulated watch. Review saved content, choose alert differences, then transfer explicitly. Preset definitions come from the laptop.</p>
    <p id="transfer-status" role="status"></p><p id="transfer-error" role="alert"></p>
    <div id="transfer-choices"></div><pre id="transfer-preview" class="metadata"></pre>
    <details><summary>Saved simulated watch configuration</summary><pre id="transfer-saved" class="metadata"></pre></details>
    <div class="actions"><button id="transfer-review">Refresh preview</button><button id="transfer-send" class="primary">Transfer reviewed configuration</button><button id="transfer-reconcile">Read back unknown outcome</button><button id="transfer-cancel">Cancel transfer</button><button id="transfer-return">Return to riding</button></div>
    <details><summary>Simulated watch edits and transfer failures</summary>
      <p class="metadata">Higher-level test injections affect this simulated endpoint only. Saved edits remain local until explicit review and Transfer.</p>
      <form id="transfer-watch-editor"><label>Watch alert<select id="transfer-watch-alert"><option value="pwm">High PWM</option><option value="speed">High speed</option><option value="battery">Low wheel battery</option><option value="lost">Lost telemetry</option></select></label>
      <label class="check"><input id="transfer-watch-enabled" type="checkbox">Enable on simulated watch</label><label>Threshold<input id="transfer-watch-threshold" type="number" min="0" max="3276.7" step="any"></label><button type="submit">Save on simulated watch</button></form>
      <form id="transfer-scenario"><label>Staging<select id="transfer-stage"><option value="normal">Normal</option><option value="interrupt">Interrupt before activation</option></select></label><label>Commit acknowledgement<select id="transfer-commit"><option value="normal">Normal</option><option value="lost_ack">Lose acknowledgement</option></select></label><label>Readback<select id="transfer-readback"><option value="normal">Normal</option><option value="fail">Unavailable</option></select></label><button type="submit">Set simulated failure</button></form>
    </details>`;
  document.querySelector('.panel')!.append(section);
  for (const [id, name] of [['review', 'preview'], ['send', 'send'], ['reconcile','reconcile'], ['cancel', 'cancel'], ['return', 'return']]) {
    section.querySelector(`#transfer-${id}`)!.addEventListener('click', () => void action(`transfer_${name}`));
  }
  section.querySelector('#transfer-watch-editor')!.addEventListener('submit', event => {
    event.preventDefault();
    const alert=section.querySelector<HTMLSelectElement>('#transfer-watch-alert')!.value;
    const value=section.querySelector<HTMLInputElement>('#transfer-watch-threshold')!.value;
    void action('transfer_watch_edit',{alert,enabled:section.querySelector<HTMLInputElement>('#transfer-watch-enabled')!.checked,...(alert==='lost' ? {} : {threshold:value==='' ? null : Number(value)})});
  });
  section.querySelector('#transfer-scenario')!.addEventListener('submit',event=>{
    event.preventDefault();
    void action('transfer_scenario',{stage:section.querySelector<HTMLSelectElement>('#transfer-stage')!.value,commit:section.querySelector<HTMLSelectElement>('#transfer-commit')!.value,readback:section.querySelector<HTMLSelectElement>('#transfer-readback')!.value});
  });
  let rendered = '';
  return enabled => {
    const view = getView();
    section.querySelectorAll<HTMLButtonElement>('button').forEach(button => button.disabled = !enabled || !view?.active);
    section.querySelectorAll<HTMLInputElement|HTMLSelectElement>('input,select').forEach(input=>input.disabled=!enabled || !view?.active);
    section.querySelector<HTMLButtonElement>('#transfer-send')!.disabled ||= !view?.preview?.candidate || view.status==='unknown';
    section.querySelector<HTMLButtonElement>('#transfer-reconcile')!.disabled ||= view?.status!=='unknown';
    section.querySelector<HTMLButtonElement>('#transfer-review')!.disabled ||= view?.status==='unknown';
    section.querySelector<HTMLButtonElement>('#transfer-cancel')!.disabled ||= view?.status==='unknown';
    section.querySelector<HTMLElement>('#transfer-status')!.textContent = view ? `${view.endpoint} · ${view.status} · saved revision ${view.watch_revision}${view.active ? ' · wheel disconnected' : ''}` : 'Transfer unavailable';
    section.querySelector<HTMLElement>('#transfer-error')!.textContent = view?.error ?? '';
    section.querySelector<HTMLElement>('#transfer-saved')!.textContent = JSON.stringify(view?.watch_config ?? null, null, 2);
    const preview = view?.preview;
    section.querySelector<HTMLElement>('#transfer-preview')!.textContent = preview ? `Laptop revision ${preview.laptop_revision}; watch revision ${preview.watch_revision}; shared base ${preview.base_revision ?? 'absent; review differences'}\n${preview.candidate ? 'Complete candidate validated' : 'Choose each differing alert field before Transfer'}\n${preview.changes.map(change => `${change.path}: ${JSON.stringify(change.watch)} → ${JSON.stringify(change.proposed)}`).join('\n')}` : '';
    const key = JSON.stringify(preview?.conflicts);
    const choices = section.querySelector<HTMLElement>('#transfer-choices')!;
    if (key !== rendered) {
      rendered = key; choices.replaceChildren();
      for (const conflict of preview?.conflicts ?? []) {
        const label = document.createElement('label'); label.textContent = conflict.path;
        const select = document.createElement('select'); select.dataset.path = conflict.path;
        select.add(new Option('Choose a saved value', ''));
        select.add(new Option(`Laptop: ${JSON.stringify(conflict.laptop)}`, 'laptop'));
        select.add(new Option(`Watch: ${JSON.stringify(conflict.watch)}`, 'watch'));
        select.addEventListener('change', () => { if (select.value) void action('transfer_choose', {path: conflict.path, side: select.value}); });
        label.append(select); choices.append(label);
      }
    }
    choices.querySelectorAll<HTMLSelectElement>('select').forEach(select => {
      select.disabled = !enabled || !view?.active;
      select.value = preview?.choices[select.dataset.path!] ?? '';
    });
  };
}
