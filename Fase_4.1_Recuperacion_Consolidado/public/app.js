const state = { configurations: [], selected: [], datasets: new Map(), queryIndex: 0 };
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' }[char]));
const display = (value, fallback = 'No disponible') => value === undefined || value === null || value === '' ? fallback : escapeHtml(value);
const runKey = (id, version) => `${id}::${version}`;
const getConfig = (id) => state.configurations.find((item) => item.id === id);
const selectedRuns = () => state.selected.map((value) => { const [id, version] = value.split('::'); return { id, version }; });

async function api(url) { const response = await fetch(url); const data = await response.json(); if (!response.ok) throw new Error(data.error || 'No se pudo leer la información.'); return data; }
function showNotice(message, type = '') { const node = $('#notice'); node.textContent = message; node.className = `notice ${type}`; }
function clearNotice() { $('#notice').className = 'notice hidden'; }

function renderConfigurations() {
  $('#configurations').innerHTML = state.configurations.map((item) => `<article class="config-card"><div class="config-card-head"><div><p class="config-title">${display(item.nombre)}</p><p class="config-meta">${item.tieneResultados ? 'JSON de resultados disponible' : 'Sin JSON de resultados'}</p></div><span class="version-count">${item.versiones.length} archivo(s)</span></div><div class="version-list">${item.versiones.length ? item.versiones.map((version, index) => `<label class="version-option"><input type="checkbox" data-run="${escapeHtml(item.id)}" value="${escapeHtml(version)}" ${state.selected.includes(runKey(item.id, version)) ? 'checked' : ''}><span><strong>${escapeHtml(version)}</strong><small>${display(item.archivosResultados?.[index], item.id)}</small></span></label>`).join('') : '<span class="muted">No hay JSON de resultados detectado</span>'}</div></article>`).join('');
  document.querySelectorAll('[data-run]').forEach((input) => input.addEventListener('change', () => toggleSelection(input.dataset.run, input.value, input.checked)));
  $('#selected-count').textContent = `${state.selected.length} seleccionadas`;
}

function toggleSelection(id, version, checked) { const value = runKey(id, version); if (checked && !state.selected.includes(value)) state.selected.push(value); if (!checked) state.selected = state.selected.filter((item) => item !== value); renderConfigurations(); loadSelectedResults(); }

async function loadSelectedResults() {
  clearNotice();
  const runs = selectedRuns();
  if (!runs.length) { $('#query-select').innerHTML = '<option value="">Selecciona una recuperación</option>'; $('#query-text').textContent = 'Selecciona una configuración para cargar sus resultados.'; $('#results').innerHTML = '<div class="empty-state"><span class="empty-icon">⇄</span><h2>Selecciona resultados para comparar</h2><p>Cada selección aparecerá en una columna independiente.</p></div>'; return; }
  const responses = await Promise.all(runs.map(async (run) => { try { const data = await api(`/api/resultados?configuracion=${encodeURIComponent(run.id)}&version=${encodeURIComponent(run.version)}`); state.datasets.set(runKey(run.id, run.version), data.resultados); return null; } catch (err) { return `${run.id} · ${run.version}: ${err.message}`; } }));
  const errors = responses.filter(Boolean); if (errors.length) showNotice(errors.join(' | '), 'error');
  const first = state.datasets.get(runKey(runs[0].id, runs[0].version)) || [];
  $('#query-select').innerHTML = first.length ? first.map((item, index) => `<option value="${index}">${display(item.query_id)}${item.query ? ` · ${display(item.query).slice(0, 90)}` : ''}</option>`).join('') : '<option value="">Sin resultados guardados</option>';
  $('#query-select').value = String(Math.min(state.queryIndex, Math.max(0, first.length - 1))); state.queryIndex = Number($('#query-select').value) || 0; $('#query-select').onchange = () => { state.queryIndex = Number($('#query-select').value); renderComparison(); }; renderComparison();
}

function score(value) { return typeof value === 'number' ? value.toFixed(4) : '—'; }
function resultColumn(run, item) { const title = getConfig(run.id)?.nombre || run.id; if (!item) return `<article class="result-column"><header class="result-column-head"><p class="eyebrow">${display(title)}</p><h3>${display(run.version)}</h3><p class="result-id">Sin resultado para esta consulta</p></header></article>`; return `<article class="result-column"><header class="result-column-head"><p class="eyebrow">${display(title)}</p><h3>${display(run.version)}</h3><p class="result-id">${display(item.query_id)} · resultado guardado</p></header><div class="column-stats"><span>${item.documents.length} documentos</span><span>${item.fragments.length} fragmentos</span></div><h4>Documentos</h4><div class="doc-list">${item.documents.map((doc) => `<div class="doc"><b>#${display(doc.rank)}</b><span>score ${score(doc.score)}</span><strong>${display(doc.doc_id)}</strong></div>`).join('')}</div><h4>Fragmentos</h4><div class="fragments">${item.fragments.map((fragment) => `<details class="fragment"><summary><b>#${display(fragment.rank)}</b> · ${display(fragment.chunk_id)} <span class="fragment-score">score ${score(fragment.score)}</span></summary><div class="fragment-body"><small>doc_id: ${display(fragment.doc_id)}${fragment.fuente ? ` · ${display(fragment.fuente)}` : ''}</small><p>${display(fragment.text || fragment.texto, 'Sin texto disponible')}</p></div></details>`).join('')}</div></article>`; }
function renderComparison() { const runs = selectedRuns(); const query = runs[0] ? state.datasets.get(runKey(runs[0].id, runs[0].version))?.[state.queryIndex] : null; $('#query-text').textContent = query?.query || 'La pregunta no está incluida en el resultado guardado.'; $('#results').innerHTML = runs.map((run) => resultColumn(run, state.datasets.get(runKey(run.id, run.version))?.[state.queryIndex])).join('') || '<div class="empty-state"><h2>Selecciona resultados para comparar</h2></div>'; }

async function load() { try { state.configurations = await api('/api/configuraciones'); renderConfigurations(); await loadSelectedResults(); } catch (err) { showNotice(err.message, 'error'); } }
$('#reload').onclick = load; $('#select-all').onclick = () => { state.selected = state.configurations.flatMap((item) => item.versiones.map((version) => runKey(item.id, version))); renderConfigurations(); loadSelectedResults(); }; $('#clear-all').onclick = () => { state.selected = []; renderConfigurations(); loadSelectedResults(); }; load();
