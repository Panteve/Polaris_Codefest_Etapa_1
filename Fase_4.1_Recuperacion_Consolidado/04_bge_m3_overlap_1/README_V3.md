# Recuperación V3 con BGE-M3 y FAISS (overlap 1)

La V3 usa por defecto `Validacion_20_Preguntas/ground_truth_15_preguntas.json` y un recall de **100**. Mantiene el recall ampliado, el reranking, MMR y el mean pooling de la
V2, y añade deduplicación exacta y semántica para evitar resultados repetidos.

El flujo recupera candidatos, aplica filtros, reranking con
`BAAI/bge-reranker-v2-m3`, elimina chunks con el mismo `chunk_id` o texto
normalizado, elimina chunks con similitud coseno mínima de `0.90`, aplica MMR,
devuelve hasta 10 fragmentos y calcula el top 3 documental por mean pooling.

```powershell
python .\Fase_4.1_Recuperacion_Consolidado\04_bge_m3_overlap_1\recuperar_V3.py `
  --query "Escribe aquí la consulta" `
  --recall-top-k 100 `
  --output-top-k 10 `
  --near-duplicate-threshold 0.90 `
  --device cpu
```

Las dependencias están en `requirements.txt` de esta carpeta.

Para procesar un arreglo JSON de preguntas y generar un único JSON de salida:

```powershell
python .\Fase_4.1_Recuperacion_Consolidado\04_bge_m3_overlap_1\recuperar_V3.py `
  --questions .\ground_truth_15_preguntas.json `
  --output-json .\Fase_4.1_Recuperacion_Consolidado\04_bge_m3_overlap_1\resultado_v3_preguntas.json `
  --device cpu
```
