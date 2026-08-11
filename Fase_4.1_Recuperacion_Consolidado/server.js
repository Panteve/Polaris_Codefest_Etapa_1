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

function discover() {
  return fs.readdirSync(ROOT, { withFileTypes: true })
    .filter(isConfigurationDirectory)
    .map((entry) => {
      const id = entry.name;
      const dir = path.join(ROOT, id);
      const versions = fs.readdirSync(dir, { withFileTypes: true })
        .filter((item) => item.isFile())
        .map((item) => versionInfo(item.name))
        .filter(Boolean)
        .sort((a, b) => b.number - a.number || a.label.localeCompare(b.label));
      const latest = versions[0] || null;
      return {
        id,
        nombre: id.replace(/^\d+_/, '').replace(/_/g, ' '),
        rutaResultados: `${id}/resultados.json`,
        tieneResultados: fs.existsSync(path.join(dir, 'resultados.json')),
        tienePreguntas: fs.existsSync(path.join(dir, 'preguntas.json')),
        versiones: versions.map((item) => item.label),
        versionPredeterminada: latest ? latest.label : null
      };
    });
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

function runRetriever(configuration, version, question) {
  const script = resolveScript(configuration, version);
  if (!script) return Promise.reject(new Error('La version solicitada no existe para esta configuracion.'));
  return new Promise((resolve, reject) => {
    const child = spawn(process.env.PYTHON || 'python', [script, '--query', question], {
      cwd: path.dirname(script),
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe']
    });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => child.kill(), RUN_TIMEOUT);
    child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
    child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
    child.on('error', (err) => { clearTimeout(timer); reject(new Error(`No se pudo iniciar Python: ${err.message}`)); });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code !== 0) return reject(new Error(stderr.trim() || `El recuperador termino con codigo ${code}.`));
      const lines = stdout.trim().split(/\r?\n/).filter(Boolean);
      try {
        const result = JSON.parse(lines[lines.length - 1]);
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
  if (req.method === 'GET' && url.pathname === '/api/resultados') {
    const configuration = getConfiguration(url.searchParams.get('configuracion'));
    if (!configuration) return error(res, 404, 'Configuracion no encontrada.');
    const file = path.join(ROOT, configuration.id, 'resultados.json');
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
      return json(res, 200, await runRetriever(configuration, version, payload.pregunta.trim()));
    } catch (err) { return error(res, 400, err.message || 'Peticion invalida.'); }
  }
  if (req.method === 'GET') {
    const requested = decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname);
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
