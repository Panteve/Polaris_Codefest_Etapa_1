const state = { reports: [], selected: '' };
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' }[char]));
const number = (value, digits = 4) => typeof value === 'number' ? value.toFixed(digits) : '—';
const percent = (value) => typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : '—';
const safe = (value, fallback = 'Sin dato') => value === undefined || value === null || value === '' ? fallback : escapeHtml(value);

async function api(url) { const response = await fetch(url); const data = await response.json(); if (!response.ok) throw new Error(data.error || 'No se pudo leer la información.'); return data; }
function showNotice(message, type = '') { const node = $('#notice'); node.textContent = message; node.className = `notice ${type}`; }
function clearNotice() { $('#notice').className = 'notice hidden'; }

function renderReports() {
  $('#report-count').textContent = `${state.reports.length} reporte${state.reports.length === 1 ? '' : 's'}`;
  $('#reports').innerHTML = state.reports.length ? state.reports.map((report) => `<button class="report-option ${state.selected === report.id ? 'active' : ''}" data-report="${escapeHtml(report.id)}"><span class="report-option-head"><strong>${safe(report.nombre, report.archivo)}</strong><span class="pill">Abrir</span></span><small>${safe(report.ruta)}</small></button>`).join('') : '<div class="empty-state"><span class="empty-icon">∑</span><h2>No hay reportes todavía</h2><p>Genera un evaluacion_ndcg_f1.json y vuelve a cargar esta página.</p></div>';
  document.querySelectorAll('[data-report]').forEach((button) => button.addEventListener('click', () => loadReport(button.dataset.report)));
}

function metricCard(label, value, detail) { return `<article class="metric-card"><p>${label}</p><strong>${value}</strong><small>${detail}</small></article>`; }
function groupedTable(groups, emptyLabel) {
  const entries = Object.entries(groups || {});
  if (!entries.length) return `<p class="muted">${emptyLabel}</p>`;
  return `<table class="metric-table"><thead><tr><th>Grupo</th><th>Consultas</th><th>NDCG@10</th><th>F1@3</th></tr></thead><tbody>${entries.map(([key, value]) => `<tr><td>${safe(key)}</td><td>${safe(value.queries, '0')}</td><td>${number(value.ndcg_at_10)}</td><td>${number(value.f1_at_3)}</td></tr>`).join('')}</tbody></table>`;
}
function queryTable(rows) {
  return `<table class="metric-table query-table"><thead><tr><th>ID</th><th>Fenómeno</th><th>Tipo</th><th>Encontrado</th><th>NDCG@10</th><th>F1@3</th></tr></thead><tbody>${rows.map((row) => `<tr title="${escapeHtml(row.query || '')}"><td>${safe(row.query_id)}</td><td>${safe(row.fenomeno)}</td><td>${safe(row.tipo)}</td><td>${row.result_found ? 'Sí' : 'No'}</td><td>${number(row.ndcg_at_10)}</td><td>${number(row.f1_at_3)}</td></tr>`).join('')}</tbody></table>`;
}
function renderDashboard(item) {
  const report = item.reporte;
  const summary = report.summary || {};
  const rows = Array.isArray(report.per_query) ? report.per_query : [];
  $('#dashboard').innerHTML = `<div class="panel"><div class="dashboard-head"><div><p class="eyebrow">Reporte seleccionado</p><h2>${safe(item.nombre, item.archivo)}</h2><p>${safe(item.ruta)} · ${rows.length} filas por consulta</p></div><span class="pill">NDCG@10 · F1@3</span></div><div class="metric-grid">${metricCard('NDCG@10', number(summary.ndcg_at_10), 'promedio global')}${metricCard('F1@3', number(summary.f1_at_3), 'promedio global')}${metricCard('Consultas evaluadas', safe(summary.queries_ground_truth, '0'), 'en ground truth')}${metricCard('Con resultados', safe(summary.queries_with_results, '0'), `${percent(Number(summary.queries_with_results || 0) / Math.max(1, Number(summary.queries_ground_truth || 0)))} de cobertura`)}</div><div class="evaluation-grid"><section class="evaluation-panel"><h3>Por fenómeno</h3>${groupedTable(report.by_fenomeno, 'El reporte no incluye desglose por fenómeno.')}</section><section class="evaluation-panel"><h3>Por tipo de pregunta</h3>${groupedTable(report.by_tipo, 'El reporte no incluye desglose por tipo.')}</section></div></div><section class="panel"><div class="section-heading"><div><p class="eyebrow">Detalle</p><h2>Métricas por consulta</h2><p class="help">Pasa el cursor sobre una fila para ver la pregunta completa.</p></div><span class="pill">${rows.length} consultas</span></div>${rows.length ? queryTable(rows) : '<p class="muted">No hay métricas por consulta en este reporte.</p>'}</section>`;
  $('#dashboard').classList.remove('hidden');
}

async function loadReport(id) { try { clearNotice(); state.selected = id; renderReports(); renderDashboard(await api(`/api/evaluaciones?reporte=${encodeURIComponent(id)}`)); } catch (err) { showNotice(err.message, 'error'); } }
async function load() { try { clearNotice(); state.reports = await api('/api/evaluaciones'); if (!state.reports.some((report) => report.id === state.selected)) state.selected = state.reports[0]?.id || ''; renderReports(); if (state.selected) await loadReport(state.selected); else $('#dashboard').classList.add('hidden'); } catch (err) { showNotice(err.message, 'error'); } }
$('#reload').onclick = load; load();
