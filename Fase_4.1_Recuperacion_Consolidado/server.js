const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');

const ROOT = __dirname;
const PUBLIC = path.join(ROOT, 'public');
const HOST = '127.0.0.1';
const PORT = Number(process.env.PORT || 3000);
const MAX_BODY = 64 * 1024;
const RUN_TIMEOUT = 10 * 60 * 1000;

function json(res, status, value) {
  const body = JSON.stringify(value);
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(body);
}

function error(res, status, message) {
  json(res, status, { error: message });
}

function isConfigurationDirectory(entry) {
  return entry.isDirectory() && entry.name !== 'Validacion_20_Preguntas' && /^[A-Za-z0-9_-]+$/.test(entry.name);
}

function versionInfo(fileName) {
  if (fileName === 'recuperar.py') return { label: 'base', number: -1, file: fileName };
  const match = /^recuperar_V(\d+)\.py$/.exec(fileName);
  return match ? { label: `V${match[1]}`, number: Number(match[1]), file: fileName } : null;
}

function resultInfo(fileName) {
  const match = /^(?:resultado|resultados)(?:_(v\d+))?\.json$/i.exec(fileName);
  if (!match) return null;
  return { label: fileName, number: match[1] ? Number(match[1].slice(1)) : -1, file: fileName };
}

function evaluationInfo(fileName) {
  return /^evaluacion(?:_.*)?\.json$/i.test(fileName)
    ? { file: fileName }
    : null;
}

function resultFileFor(directory, version = null) {
  const files = fs.readdirSync(directory, { withFileTypes: true }).filter((item) => item.isFile()).map((item) => resultInfo(item.name)).filter(Boolean);
  const selected = version ? files.find((item) => item.file === version || item.label === version) : files.sort((a, b) => b.number - a.number || a.file.localeCompare(b.file))[0];
  if (selected) return { file: path.join(directory, selected.file), relative: selected.file };
  return { file: path.join(directory, 'resultados.json'), relative: 'resultados.json' };
}

function discover() {
  return fs.readdirSync(ROOT, { withFileTypes: true })
    .filter(isConfigurationDirectory)
    .map((entry) => {
      const id = entry.name;
      const dir = path.join(ROOT, id);
      const resultFiles = fs.readdirSync(dir, { withFileTypes: true }).map((item) => item.isFile() ? resultInfo(item.name) : null).filter(Boolean).sort((a, b) => b.number - a.number || a.file.localeCompare(b.file));
      const result = resultFiles[0] ? { file: path.join(dir, resultFiles[0].file), relative: resultFiles[0].file } : resultFileFor(dir);
      const versions = fs.readdirSync(dir, { withFileTypes: true })
        .filter((item) => item.isFile())
        .map((item) => versionInfo(item.name))
        .filter(Boolean)
        .sort((a, b) => b.number - a.number || a.label.localeCompare(b.label));
      const latest = versions[0] || null;
      return {
        id,
        nombre: id.replace(/^\d+_/, '').replace(/_/g, ' '),
        rutaResultados: `${id}/${result.relative}`,
        tieneResultados: fs.existsSync(result.file),
        tienePreguntas: fs.existsSync(path.join(dir, 'preguntas.json')),
        versiones: resultFiles.map((item) => item.label),
        versionPredeterminada: resultFiles[0]?.label || null,
        archivosResultados: resultFiles.map((item) => item.file)
      };
    });
}

function discoverEvaluationReports() {
  const reports = [];
  const addDirectory = (directory, configurationId = null) => {
    fs.readdirSync(directory, { withFileTypes: true })
      .filter((item) => item.isFile() && evaluationInfo(item.name))
      .forEach((item) => {
        const relative = path.relative(ROOT, path.join(directory, item.name));
        reports.push({
          id: relative.replace(/\\/g, '/'),
          archivo: item.name,
          configuracion: configurationId,
          nombre: configurationId ? configurationId.replace(/^\d+_/, '').replace(/_/g, ' ') : item.name,
          ruta: relative.replace(/\\/g, '/')
        });
      });
  };

  addDirectory(ROOT);
  fs.readdirSync(ROOT, { withFileTypes: true })
    .filter(isConfigurationDirectory)
    .forEach((entry) => addDirectory(path.join(ROOT, entry.name), entry.name));
  return reports.sort((a, b) => a.id.localeCompare(b.id));
}

function getEvaluationReport(id) {
  const report = discoverEvaluationReports().find((item) => item.id === id);
  if (!report) return null;
  return { ...report, file: path.join(ROOT, report.ruta) };
}

function readEvaluationReport(file) {
  const report = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (!report || typeof report !== 'object' || !report.summary || !Array.isArray(report.per_query)) {
    throw new Error('El reporte debe incluir summary y per_query.');
  }
  return report;
}

function getConfiguration(id) {
  if (typeof id !== 'string' || !/^[A-Za-z0-9_-]+$/.test(id)) return null;
  const found = discover().find((item) => item.id === id);
  return found || null;
}

function resolveScript(configuration, requestedVersion) {
  const dir = path.join(ROOT, configuration.id);
  const files = fs.readdirSync(dir, { withFileTypes: true })
    .filter((item) => item.isFile())
    .map((item) => versionInfo(item.name))
    .filter(Boolean);
  const selected = requestedVersion ? files.find((item) => item.label === requestedVersion) : files.sort((a, b) => b.number - a.number)[0];
  return selected ? path.join(dir, selected.file) : null;
}

function readJsonFile(file) {
  const raw = fs.readFileSync(file, 'utf8');
  const parsed = JSON.parse(raw);
  return Array.isArray(parsed) ? parsed : (Array.isArray(parsed.results) ? parsed.results : parsed);
}

function readJsonLines(file) {
  return fs.readFileSync(file, 'utf8')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      try { return JSON.parse(line); }
      catch { throw new Error(`La linea ${index + 1} no contiene JSON valido.`); }
    });
}

function normalizeResults(value) {
  if (!Array.isArray(value)) throw new Error('El resultado debe ser un arreglo JSON.');
  return value.map((item, index) => {
    if (!item || typeof item !== 'object' || !item.query_id || !Array.isArray(item.documents) || !Array.isArray(item.fragments)) {
      throw new Error(`La consulta en la posicion ${index + 1} no cumple el esquema esperado.`);
    }
    return item;
  });
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', (chunk) => {
      data += chunk;
      if (Buffer.byteLength(data) > MAX_BODY) reject(new Error('La peticion es demasiado grande.'));
    });
    req.on('end', () => resolve(data));
    req.on('error', reject);
  });
}

function runRetriever(configuration, version, question, onEvent = () => {}) {
  const script = resolveScript(configuration, version);
  if (!script) return Promise.reject(new Error('La version solicitada no existe para esta configuracion.'));
  return new Promise((resolve, reject) => {
    const child = spawn(process.env.PYTHON || 'python', [script, '--query', question], {
      cwd: path.dirname(script),
      windowsHide: true,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
      stdio: ['ignore', 'pipe', 'pipe']
    });
    let stdout = '';
    let stderr = '';
    const startedAt = Date.now();
    const timer = setTimeout(() => child.kill(), RUN_TIMEOUT);
    const heartbeat = setInterval(() => onEvent(`En ejecucion... ${Math.round((Date.now() - startedAt) / 1000)} s`), 2000);
    onEvent(`Proceso iniciado: ${path.basename(script)}`);
    child.stdout.on('data', (chunk) => { const text = chunk.toString(); stdout += text; text.split(/\r?\n/).filter(Boolean).forEach((line) => onEvent(line)); });
    child.stderr.on('data', (chunk) => { const text = chunk.toString(); stderr += text; text.split(/\r?\n/).filter(Boolean).forEach((line) => onEvent(`[stderr] ${line}`)); });
    child.on('error', (err) => { clearTimeout(timer); clearInterval(heartbeat); reject(new Error(`No se pudo iniciar Python: ${err.message}`)); });
    child.on('close', (code) => {
      clearTimeout(timer);
      clearInterval(heartbeat);
      if (code !== 0) return reject(new Error(stderr.trim() || `El recuperador termino con codigo ${code}.`));
      const lines = stdout.trim().split(/\r?\n/).filter(Boolean);
      try {
        const result = JSON.parse(lines[lines.length - 1]);
        onEvent('Resultado JSON recibido.');
        resolve({ ...result, version });
      } catch {
        reject(new Error('El recuperador no devolvio un objeto JSON valido.'));
      }
    });
  });
}

async function route(req, res) {
  const url = new URL(req.url, `http://${HOST}:${PORT}`);
  if (req.method === 'GET' && url.pathname === '/api/health') return json(res, 200, { ok: true });
  if (req.method === 'GET' && url.pathname === '/api/configuraciones') return json(res, 200, discover());
  if (req.method === 'GET' && url.pathname === '/api/evaluaciones') {
    const reports = discoverEvaluationReports();
    if (!url.searchParams.has('reporte')) {
      return json(res, 200, reports.map(({ file, ...item }) => item));
    }
    const report = getEvaluationReport(url.searchParams.get('reporte'));
    if (!report || !fs.existsSync(report.file)) return error(res, 404, 'Reporte de evaluacion no encontrado.');
    try {
      const { file, ...metadata } = report;
      return json(res, 200, { ...metadata, reporte: readEvaluationReport(file) });
    }
    catch (err) { return error(res, 422, `No se pudo leer el reporte de evaluacion: ${err.message}`); }
  }
  if (req.method === 'GET' && url.pathname === '/api/resultados') {
    const configuration = getConfiguration(url.searchParams.get('configuracion'));
    if (!configuration) return error(res, 404, 'Configuracion no encontrada.');
    const file = resultFileFor(path.join(ROOT, configuration.id), url.searchParams.get('version')).file;
    if (!fs.existsSync(file)) return error(res, 404, 'Esta configuracion aun no tiene resultados.json.');
    try { return json(res, 200, { configuracion: configuration.id, resultados: normalizeResults(readJsonFile(file)) }); }
    catch (err) { return error(res, 422, `No se pudo leer resultados.json: ${err.message}`); }
  }
  if (req.method === 'GET' && url.pathname === '/api/preguntas') {
    const configuration = getConfiguration(url.searchParams.get('configuracion'));
    if (!configuration) return error(res, 404, 'Configuracion no encontrada.');
    const file = path.join(ROOT, configuration.id, 'preguntas.json');
    if (!fs.existsSync(file)) return json(res, 200, []);
    try { return json(res, 200, readJsonFile(file)); } catch (err) { return error(res, 422, `No se pudo leer preguntas.json: ${err.message}`); }
  }
  if (req.method === 'GET' && url.pathname === '/api/preguntas-validacion') {
    const file = path.join(ROOT, 'Validacion_20_Preguntas', 'preguntas_validacion_20.jsonl');
    if (!fs.existsSync(file)) return error(res, 404, 'No se encontro el catalogo de validacion.');
    try { return json(res, 200, readJsonLines(file)); }
    catch (err) { return error(res, 422, `No se pudo leer el catalogo de validacion: ${err.message}`); }
  }
  if (req.method === 'POST' && url.pathname === '/api/recuperar') {
    try {
      const payload = JSON.parse(await readBody(req));
      const configuration = getConfiguration(payload.configuracion);
      if (!configuration) return error(res, 404, 'Configuracion no encontrada.');
      if (typeof payload.pregunta !== 'string' || !payload.pregunta.trim()) return error(res, 400, 'La pregunta no puede estar vacia.');
      const version = payload.version || configuration.versionPredeterminada;
      if (!version) return error(res, 422, 'La configuracion no contiene un script de recuperacion.');
      if (url.searchParams.get('stream') === '1') {
        res.writeHead(200, { 'Content-Type': 'application/x-ndjson; charset=utf-8', 'Cache-Control': 'no-store', 'Transfer-Encoding': 'chunked' });
        const send = (type, value) => res.write(`${JSON.stringify({ type, value })}\n`);
        send('status', `Preparando ${configuration.id} · ${version}`);
        try { send('result', await runRetriever(configuration, version, payload.pregunta.trim(), (message) => send('log', message))); }
        catch (err) { send('error', err.message); }
        return res.end();
      }
      return json(res, 200, await runRetriever(configuration, version, payload.pregunta.trim()));
    } catch (err) { return error(res, 400, err.message || 'Peticion invalida.'); }
  }
  if (req.method === 'GET') {
    const requested = decodeURIComponent(url.pathname === '/' ? '/index.html' : (url.pathname === '/evaluacion' ? '/evaluacion.html' : url.pathname));
    const file = path.resolve(PUBLIC, `.${requested}`);
    if (!file.startsWith(`${PUBLIC}${path.sep}`) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return error(res, 404, 'Recurso no encontrado.');
    const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8' };
    res.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream' });
    return fs.createReadStream(file).pipe(res);
  }
  return error(res, 405, 'Metodo no permitido.');
}

http.createServer((req, res) => route(req, res).catch((err) => error(res, 500, err.message))).listen(PORT, HOST, () => {
  console.log(`Visor disponible en http://${HOST}:${PORT}`);
});
