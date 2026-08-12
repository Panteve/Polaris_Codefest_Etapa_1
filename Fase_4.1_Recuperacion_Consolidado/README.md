# Fase 4.1 — Recuperación consolidada

Cada configuración contiene un `recuperar_V1.py` independiente. El script usa
el índice, la metadata y el encoder de su configuración en `Fase_4.1_Recuperacion_Consolidado`.

La recuperación es densa y básica: codifica la pregunta, ejecuta una búsqueda
directa en FAISS y conserva el orden de los vecinos. No aplica reranking,
agrupación de scores, suma, promedio ni generación de texto.

## Configuraciones y encoders

| Configuración | Encoder por defecto |
|---|---|
| `01_bge_m3_corpus` | `BAAI/bge-m3` |
| `03_granite_corpus` | `ibm-granite/granite-embedding-311m-multilingual-r2` |
| `04_bge_m3_overlap_1` | `BAAI/bge-m3` |
| `05_granite_overlap_1` | `ibm-granite/granite-embedding-311m-multilingual-r2` |
| `06_bge_m3_semantic_pdf` | `BAAI/bge-m3` |

## Parámetros configurables

Todos los `recuperar_V1.py` aceptan la misma interfaz:

| Parámetro | Por defecto | Uso |
|---|---|---|
| `--query` | interactivo | Ejecuta una sola pregunta. |
| `--top-k` | `20` | Cantidad máxima de vecinos directos solicitados a FAISS. |
| `--model` | encoder de la tabla | Encoder para codificar la consulta. |
| `--device` | automático | Dispositivo, por ejemplo `cpu` o `cuda`. |
| `--index` | índice de la configuración | Ruta alternativa al índice FAISS. |
| `--metadata` | metadata de la configuración | Ruta alternativa al JSONL. |
| `--output-json` | `resultado.json` | Archivo JSON normal. |
| `--output` | sin archivo | Archivo JSONL opcional. |
| `--threshold` | `-1.0` | Similitud mínima para conservar un vecino. |
| `--fenomeno` | sin filtro | Filtra por fenómeno `1`, `2` o `3`. |
| `--idioma` | sin filtro | Filtra por idioma, por ejemplo `es`. |
| `--formato` | sin filtro | Filtra por formato, por ejemplo `pdf`. |

Los filtros solo descartan resultados después de la búsqueda; no reordenan los
vecinos. `--model` es configurable, pero por defecto debe conservarse el
modelo que corresponde al encoder con el que se generó el índice.

Ejemplo:

```powershell
python .\Fase_4.1_Recuperacion_Consolidado\03_granite_corpus\recuperar_V1.py `
    --query "¿Qué capacidades de inteligencia artificial se destacan?" `
    --top-k 20 `
    --device cpu
```

Los scripts escriben los resultados en la carpeta de su configuración y no
importan ningún otro recuperador.

## Visor local

La carpeta incluye un visor local para consultar los `resultados.json` disponibles,
seleccionar la versión de cada recuperador y comparar dos o más configuraciones.
No requiere instalar dependencias de Node.js.

Desde esta carpeta, inicia el servidor con:

```powershell
node server.js
```

Después abre `http://127.0.0.1:3000`. El servidor solo escucha en la interfaz
local. La ejecución bajo demanda de los scripts Python usa la combinación de
configuración y versión detectada por el servidor; el navegador nunca envía una
ruta de archivo ni un comando.

El visor expone las rutas locales `GET /api/configuraciones`,
`GET /api/resultados`, `GET /api/preguntas`, `GET /api/preguntas-validacion`,
`POST /api/recuperar` y `GET /api/health`. El catálogo
`Validacion_20_Preguntas/preguntas_validacion_20.jsonl` aparece en la interfaz
como preguntas predefinidas e incluye la respuesta esperada para facilitar la
revisión de cada recuperación. Las configuraciones sin `resultados.json` se
pueden consultar bajo demanda si su script y sus dependencias Python están disponibles.

Para comparar versiones, marca las casillas de la sección `Comparar` dentro de
una configuración. Puedes marcar, por ejemplo, `V1` y `V2` de la misma carpeta;
cada ejecución aparecerá en su propia tarjeta y conservará su ranking independiente.

Durante una recuperación se muestra un panel de actividad tipo consola con el
script ejecutado, mensajes del proceso, tiempo transcurrido y errores. El panel
recibe eventos en tiempo real desde el servidor local.

La interfaz principal funciona como un visor comparativo: se puede seleccionar
cualquier cantidad de archivos JSON de resultados encontrados dentro de las
configuraciones. Cada selección
ocupa una columna con la identificación de la configuración arriba y sus
documentos y fragmentos debajo. Los resultados guardados se cargan
automáticamente cuando existen. Las opciones se detectan a partir de nombres
como `resultado.json`, `resultados.json`, `resultado_V1.json` o
`resultados_V2.json`, incluyendo la salida predeterminada de V3
`resultado_v3.json`; no se toman de los scripts Python. La salida de cada JSON
se puede seleccionar como una columna independiente. Esta interfaz no ejecuta
recuperadores Python.

## Visor de métricas de evaluación

El mismo servidor incluye una segunda ruta para consultar los reportes generados
por `evaluar_ndcg_f1.py`:

```text
http://127.0.0.1:3000/evaluacion
```

También se puede abrir directamente `/evaluacion.html`. La página detecta
automáticamente archivos cuyo nombre coincida con `evaluacion*.json` en la raíz
de esta fase y dentro de cada carpeta de configuración. El endpoint
`GET /api/evaluaciones` lista los reportes disponibles y
`GET /api/evaluaciones?reporte=<ruta-relativa>` devuelve el reporte completo.

Para generar un reporte que aparezca en la página:

```powershell
python .\evaluar_ndcg_f1.py `
    --ground-truth .\Validacion_20_Preguntas\ground_truth_15_preguntas.json `
    --results .\03_granite_corpus\resultado_v2.json `
    --metadata .\03_granite_corpus\metadata.jsonl `
    --output .\03_granite_corpus\evaluacion_ndcg_f1.json `
    --csv .\03_granite_corpus\evaluacion_ndcg_f1.csv
```

También existe un modo automático para evaluar todo de una vez. Recorre las
carpetas de configuración, toma cada archivo `resultado*.json`, busca su
`metadata.jsonl` y crea los reportes dentro de la misma carpeta:

```powershell
python .\evaluar_ndcg_f1.py --auto
```

Por ejemplo, `01_bge_m3_corpus\resultado_v2.json` produce
`01_bge_m3_corpus\evaluacion_resultado_v2.json` y
`01_bge_m3_corpus\evaluacion_resultado_v2.csv`. Si el ground truth está en
otra ubicación, se puede indicar explícitamente:

```powershell
python .\evaluar_ndcg_f1.py --auto `
    --ground-truth .\Validacion_20_Preguntas\ground_truth_15_preguntas.json
```

Para no generar los CSV auxiliares, usa `--no-csv`. La ejecución continúa con
las demás carpetas si un resultado individual tiene un error y al final indica
cuántas evaluaciones terminaron correctamente.

La vista muestra el resumen global de `NDCG@10`, `F1@3`, cantidad de consultas
y cobertura; además presenta tablas agrupadas por `fenomeno` y `tipo`, y el
detalle por consulta desde `per_query`. El matching y el cálculo de las
métricas siguen siendo responsabilidad del evaluador Python; el navegador solo
lee y presenta el JSON, por lo que esta ruta no ejecuta evaluaciones ni
recuperadores.
