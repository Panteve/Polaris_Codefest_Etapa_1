# Recuperación con BGE-M3 y FAISS

Este módulo consulta el índice generado en la Fase 3 usando el mismo encoder
`BAAI/bge-m3`. La metadata se lee en el orden original y se valida contra el
número de vectores del índice para evitar recuperar un texto equivocado.

## Estrategia de recuperación

Para cada pregunta, el script realiza este flujo:

1. Recupera una cantidad configurable de chunks candidatos desde FAISS.
2. Agrupa los chunks recuperados por `doc_id`.
3. Calcula la puntuación de cada documento usando el promedio (`mean`) de sus
   3 mejores chunks, o la suma (`sum`) de las puntuaciones de sus chunks
   candidatos.
4. Devuelve los 3 documentos con mayor puntuación agregada.
5. Muestra y guarda únicamente los 10 chunks mejor puntuados.

Por defecto se utilizan 20 chunks candidatos y el promedio de puntuaciones:

```text
candidate_chunks = 20
doc_score = mean
mean_top_chunks = 3
fragments_in_output = 10
```

Los 20 chunks se usan para calcular el ranking de documentos, pero nunca se
entregan completos en la salida. La salida queda limitada a 10 fragmentos.
Cuando se usa `mean`, un documento con menos de 3 chunks recuperados utiliza
los que tenga disponibles.

Desde la raíz del proyecto:

```powershell
python .\Fase_4_Recuperacion\01_bge_m3_corpus\recuperar.py
```

El programa abre una consola interactiva. Para una sola pregunta:

```powershell
python .\Fase_4_Recuperacion\01_bge_m3_corpus\recuperar.py `
    --query "¿Qué capacidades de inteligencia artificial se destacan?"
```

Para guardar las respuestas como JSON Lines:

```powershell
python .\Fase_4_Recuperacion\01_bge_m3_corpus\recuperar.py `
    --output .\Fase_4_Recuperacion\resultados.jsonl
```

El programa genera automáticamente `resultados.json` en esta carpeta, como un
arreglo JSON normal. Para elegir otra ruta:

```powershell
python .\Fase_4_Recuperacion\01_bge_m3_corpus\recuperar.py `
    --output-json .\Fase_4_Recuperacion\resultados.json
```

Se pueden usar `--output` y `--output-json` al mismo tiempo.

Los filtros opcionales son `--fenomeno 1`, `--idioma es` y `--formato pdf`.
Por defecto se recuperan 20 chunks candidatos, se agrupan por documento y se
calcula el promedio de sus puntuaciones. La salida muestra siempre solo los 10
mejores fragmentos. Estos valores se pueden controlar así:

```powershell
python .\Fase_4_Recuperacion\01_bge_m3_corpus\recuperar.py `
    --candidate-chunks 20 `
    --doc-score mean
```

Para puntuar cada documento por la suma de sus chunks candidatos usa
`--doc-score sum`. También se puede aplicar un umbral con `--threshold 0.35` y
seleccionar dispositivo con `--device cuda`.

Parámetros principales:

| Parámetro | Por defecto | Descripción |
|---|---:|---|
| `--candidate-chunks` | `20` | Cantidad de chunks usados para puntuar documentos. Debe ser mínimo `10`. |
| `--doc-score` | `mean` | Agregación por documento: promedio de los 3 mejores chunks (`mean`) o suma de todos los chunks candidatos (`sum`). |
| salida de fragmentos | `10` | Cantidad fija de fragmentos mostrados y guardados. |
| `--threshold` | `-1.0` | Umbral mínimo de similitud para aceptar un chunk. |

Por defecto usa los artefactos de `Fase_3_Encoder\01_bge_m3_corpus`:
`index.faiss` y `metadata.jsonl`.

El resto de configuraciones tiene su propia carpeta dentro de
`Fase_4_Recuperacion`, con un `recuperar.py` y un README independientes. La
configuración `02_hibrido` usa un único script para combinar BGE-M3 no-PDF y
Granite late PDF.
