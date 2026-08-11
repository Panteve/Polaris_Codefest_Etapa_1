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
