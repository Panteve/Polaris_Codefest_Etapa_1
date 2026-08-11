const state = { configurations: [], selected: new Set(), active: null, datasets: new Map(), validationQuestions: [], mode: 'individual' };
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' }[char]));
const display = (value, fallback = 'No disponible') => value === undefined || value === null || value === '' ? fallback : escapeHtml(value);

async function api(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'No se pudo completar la operacion.');
  return data;
}

function showNotice(message, type = '') { const element = $('#notice'); element.textContent = message; element.className = `notice ${type}`; }
function clearNotice() { $('#notice').className = 'notice hidden'; }

function selectValidationQuestion(index) {
  const item = state.validationQuestions[Number(index)];
  const expected = $('#expected-answer');
  if (!item) { expected.textContent = ''; expected.classList.add('hidden'); return; }
  $('#question').value = item.pregunta || '';
  expected.textContent = item.respuesta_esperada || 'No hay respuesta esperada registrada.';
  expected.classList.remove('hidden');
}

async function loadValidationQuestions() {
  const select = $('#validation-select');
  try {
    state.validationQuestions = await api('/api/preguntas-validacion');
    select.innerHTML = '<option value="">Selecciona una pregunta predefinida</option>' + state.validationQuestions.map((item, index) => `<option value="${index}">${display(item.query_id)} · F${display(item.fenomeno)} · ${display(item.idioma)}</option>`).join('');
    select.onchange = () => selectValidationQuestion(select.value);
  } catch (err) {
    select.innerHTML = '<option value="">Catálogo no disponible</option>';
    showNotice(err.message, 'error');
  }
}

function renderConfigurations() {
  $('#config-count').textContent = state.configurations.length;
  $('#configurations').innerHTML = state.configurations.map((item) => `
    <article class="config-item ${state.active === item.id ? 'active' : ''}" data-id="${escapeHtml(item.id)}">
      <label class="config-main"><input type="checkbox" data-select="${escapeHtml(item.id)}" ${state.selected.has(item.id) ? 'checked' : ''}><span><span class="config-title">${display(item.nombre)}</span><span class="config-meta">${item.tieneResultados ? 'Resultados disponibles' : 'Sin resultados guardados'} · ${item.versiones.length} version(es)</span></span></label>
      <select class="version-select" data-version="${escapeHtml(item.id)}" aria-label="Version de ${escapeHtml(item.nombre)}">${item.versiones.length ? item.versiones.map((version) => `<option value="${version}" ${version === item.versionPredeterminada ? 'selected' : ''}>${version}</option>`).join('') : '<option>Sin script</option>'}</select>
    </article>`).join('');
  $('#compare').disabled = state.selected.size < 2;
  document.querySelectorAll('[data-select]').forEach((input) => input.addEventListener('change', () => { input.checked ? state.selected.add(input.dataset.select) : state.selected.delete(input.dataset.select); renderConfigurations(); }));
  document.querySelectorAll('.config-item').forEach((card) => card.addEventListener('click', (event) => { if (event.target.matches('input,select,option')) return; activate(card.dataset.id); }));
}

function versionFor(id) { return document.querySelector(`[data-version="${CSS.escape(id)}"]`)?.value || null; }
function activate(id) { state.active = id; state.mode = 'individual'; $('#mode-label').textContent = 'Vista individual'; renderConfigurations(); loadDataset(id); }

async function loadDataset(id) {
  clearNotice(); $('#results').innerHTML = '<div class="empty-state"><span class="empty-icon">…</span><h2>Cargando resultados</h2><p>Estamos leyendo la configuracion seleccionada.</p></div>';
  try { const data = await api(`/api/resultados?configuracion=${encodeURIComponent(id)}`); state.datasets.set(id, data.resultados); renderResults([{ id, results: data.resultados, version: versionFor(id) }]); renderSavedQueries(data.resultados); }
  catch (err) { showNotice(err.message, 'error'); $('#results').innerHTML = `<div class="empty-state"><h2>No hay resultados para mostrar</h2><p>${escapeHtml(err.message)}</p></div>`; $('#saved-queries').classList.add('hidden'); }
}

function renderSavedQueries(results) { const select = $('#query-select'); select.innerHTML = results.map((item, index) => `<option value="${index}">${display(item.query_id)}${item.query ? ` · ${display(item.query).slice(0, 80)}` : ''}</option>`).join(''); $('#saved-queries').classList.toggle('hidden', results.length === 0); select.onchange = () => renderResults([{ id: state.active, results, version: versionFor(state.active) }], Number(select.value)); }
function score(value) { return typeof value === 'number' ? value.toFixed(4) : '—'; }

function resultCard(id, item, version) {
  const configuration = state.configurations.find((config) => config.id === id);
  const integrity = item.documents.length !== 3 || item.fragments.length !== 10 ? `<div class="notice">Advertencia: se esperaban 3 documentos y 10 fragmentos; se encontraron ${item.documents.length} y ${item.fragments.length}.</div>` : '';
  return `<article class="result-card"><div class="result-header"><div><p class="eyebrow">${display(configuration?.nombre, id)}</p><h3>${display(item.query_id)}</h3><p class="result-subtitle">${display(item.query, 'Pregunta no incluida en el resultado')}</p></div><span class="pill">${display(version, 'guardado')}</span></div>${integrity}<div class="stats"><span class="stat">${item.documents.length} documentos</span><span class="stat">${item.fragments.length} fragmentos</span></div><h4>Documentos recuperados</h4><div class="doc-list">${item.documents.map((doc) => `<div class="doc"><span class="rank">#${display(doc.rank)}</span><span class="score">score ${score(doc.score)}</span><div class="doc-id">${display(doc.doc_id)}</div></div>`).join('')}</div><h4>Fragmentos recuperados</h4><div class="fragments">${item.fragments.map((fragment) => `<details class="fragment"><summary><span class="rank">#${display(fragment.rank)}</span> ${display(fragment.chunk_id)} <span class="score">score ${score(fragment.score)}</span></summary><div class="fragment-body"><div class="fragment-meta"><span>doc_id: ${display(fragment.doc_id)}</span>${fragment.fuente ? `<span>fuente: ${display(fragment.fuente)}</span>` : ''}${fragment.idioma ? `<span>idioma: ${display(fragment.idioma)}</span>` : ''}${fragment.fenomeno ? `<span>fenomeno: ${display(fragment.fenomeno)}</span>` : ''}</div><div>${display(fragment.text || fragment.texto, 'Sin texto disponible')}</div></div></details>`).join('')}</div></article>`;
}

function renderResults(groups, queryIndex = 0) { $('#results').innerHTML = groups.map((group) => group.results[queryIndex] ? resultCard(group.id, group.results[queryIndex], group.version) : '').join('') || '<div class="empty-state"><h2>Sin resultados</h2></div>'; }

async function retrieve() {
  const question = $('#question').value.trim(); if (!question) return showNotice('Escribe una pregunta antes de recuperar.', 'error');
  const ids = state.mode === 'comparative' ? [...state.selected] : (state.active ? [state.active] : []); if (!ids.length) return showNotice('Selecciona al menos una configuracion.', 'error');
  clearNotice(); $('#retrieve').disabled = true; $('#results').innerHTML = '<div class="empty-state"><span class="empty-icon">…</span><h2>Ejecutando recuperacion</h2><p>La consulta se esta procesando localmente.</p></div>';
  const results = await Promise.all(ids.map(async (id) => { try { const data = await api('/api/recuperar', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ configuracion:id, version:versionFor(id), pregunta:question }) }); return { id, results:[data], version:data.version }; } catch (err) { return { id, results:[], version:versionFor(id), error:err.message }; } }));
  $('#retrieve').disabled = false; const failures = results.filter((item) => item.error); if (failures.length) showNotice(failures.map((item) => `${item.id}: ${item.error}`).join(' · '), 'error'); renderResults(results);
}

async function load() { try { state.configurations = await api('/api/configuraciones'); renderConfigurations(); if (state.configurations.length) activate(state.configurations[0].id); await loadValidationQuestions(); } catch (err) { showNotice(err.message, 'error'); } }
$('#reload').onclick = load; $('#retrieve').onclick = retrieve; $('#select-all').onclick = () => { state.selected = new Set(state.configurations.map((item) => item.id)); renderConfigurations(); }; $('#clear-all').onclick = () => { state.selected.clear(); renderConfigurations(); }; $('#compare').onclick = () => { if (state.selected.size < 2) return; state.mode = 'comparative'; $('#mode-label').textContent = 'Vista comparativa'; $('#saved-queries').classList.add('hidden'); $('#question').focus(); }; loadValidationQuestions(); load();
