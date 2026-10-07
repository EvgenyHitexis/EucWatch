export interface TransferView {
  active: boolean; endpoint: string; status: string; error: string | null;
  watch_revision: number; watch_config: unknown;
  preview: null | {
    laptop_revision: number; watch_revision: number; candidate: unknown;
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
    <div class="actions"><button id="transfer-review">Refresh preview</button><button id="transfer-send" class="primary">Transfer reviewed configuration</button><button id="transfer-cancel">Cancel transfer</button><button id="transfer-return">Return to riding</button></div>`;
  document.querySelector('.panel')!.append(section);
  for (const [id, name] of [['review', 'preview'], ['send', 'send'], ['cancel', 'cancel'], ['return', 'return']]) {
    section.querySelector(`#transfer-${id}`)!.addEventListener('click', () => void action(`transfer_${name}`));
  }
  let rendered = '';
  return enabled => {
    const view = getView();
    section.querySelectorAll<HTMLButtonElement>('button').forEach(button => button.disabled = !enabled || !view?.active);
    section.querySelector<HTMLButtonElement>('#transfer-send')!.disabled ||= !view?.preview?.candidate;
    section.querySelector<HTMLElement>('#transfer-status')!.textContent = view ? `${view.endpoint} · ${view.status} · saved revision ${view.watch_revision}${view.active ? ' · wheel disconnected' : ''}` : 'Transfer unavailable';
    section.querySelector<HTMLElement>('#transfer-error')!.textContent = view?.error ?? '';
    section.querySelector<HTMLElement>('#transfer-saved')!.textContent = JSON.stringify(view?.watch_config ?? null, null, 2);
    const preview = view?.preview;
    section.querySelector<HTMLElement>('#transfer-preview')!.textContent = preview ? `Laptop revision ${preview.laptop_revision}; watch revision ${preview.watch_revision}\n${preview.candidate ? 'Complete candidate validated' : 'Choose each differing alert field before Transfer'}\n${preview.changes.map(change => `${change.path}: ${JSON.stringify(change.watch)} → ${JSON.stringify(change.proposed)}`).join('\n')}` : '';
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
