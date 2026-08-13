# Fase 4.2 — Recuperación seleccionada para mejora

Esta fase contiene las tres configuraciones con mejor potencial observadas en
la evaluación inicial de la Fase 4.1:

| Configuración | Motivo de selección |
|---|---|
| `01_bge_m3_corpus` | Buen equilibrio entre NDCG@10 y F1@3. |
| `04_bge_m3_overlap_1` | Mejor NDCG@10 de la evaluación inicial. |
| `06_bge_m3_semantic_pdf` | Mejor F1@3 de la evaluación inicial. |

Cada carpeta conserva sus datos necesarios: `index.faiss`, `metadata.jsonl`,
los recuperadores V1/V2/V3, requirements, resultados anteriores y reportes de
evaluación disponibles. También se incluye el ground truth común en
`Validacion_20_Preguntas`.

## Evaluar todas las configuraciones

Desde esta carpeta ejecuta:

```powershell
python .\evaluar_ndcg_f1.py --auto
```

El evaluador recorre las tres carpetas, detecta cada `resultado*.json` y genera
`evaluacion_*.json` y `evaluacion_*.csv` dentro de la misma configuración.
Para omitir los CSV:

```powershell
python .\evaluar_ndcg_f1.py --auto --no-csv
```

## Visor de resultados y métricas

Inicia el servidor local:

```powershell
node .\server.js
```

Abre el visor comparativo en `http://127.0.0.1:3000` y el dashboard de métricas
en `http://127.0.0.1:3000/evaluacion`.

La Fase 4.1 original se conserva sin cambios en
`Fase_4.1_Recuperacion_Consolidado`. Esta carpeta 4.2 es una copia de trabajo
independiente para experimentar con las tres configuraciones seleccionadas.
