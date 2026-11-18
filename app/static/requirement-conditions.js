function setupConditionSuggestions(list) {
  list.addEventListener('click', async function (event) {
    if (!event.target.closest('[data-suggest-condition]')) return;
    const row = event.target.closest('[data-req-row]');
    const message = row.querySelector('[data-condition-message]');
    try {
      const body = new URLSearchParams({text: row.querySelector('[name=req_text]').value});
      const response = await fetch('/requisitos/sugerir-condicao', {method: 'POST', body});
      if (!response.ok || !response.headers.get('content-type').includes('application/json')) throw new Error();
      const condition = (await response.json()).condition;
      if (!condition) {
        message.textContent = 'Sem sugestão inequívoca. Configure a regra ou mantenha revisão humana.';
        return;
      }
      let mode = condition.kind;
      if (mode === 'language') mode += ':' + condition.level;
      if (mode === 'education') mode += ':' + condition.completion;
      row.querySelector('[name=req_condition_mode]').value = mode;
      row.querySelector('[name=req_condition_terms]').value = condition.terms.join('; ');
      message.textContent = 'Sugestão preenchida. Revise antes de salvar a vaga.';
    } catch (_) {
      message.textContent = 'Não foi possível sugerir. Você pode configurar manualmente.';
    }
  });
}
