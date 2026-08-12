# Recuperación V3 con BGE-M3 y FAISS

La V3 mantiene el recall ampliado, el reranking, MMR y el mean pooling de la
V2, y añade deduplicación exacta y semántica para evitar resultados repetidos.

Flujo:

1. FAISS recupera hasta 50 candidatos por defecto.
2. Se aplican los filtros opcionales.
3. El cross-encoder `BAAI/bge-reranker-v2-m3` asigna scores de relevancia.
4. Se eliminan chunks con el mismo `chunk_id` o el mismo texto normalizado.
5. Se eliminan chunks con similitud coseno de al menos `0.90` frente a uno de mayor score.
6. MMR selecciona como máximo 10 fragmentos diversos.
7. Mean pooling sobre esos 10 fragmentos determina los 3 documentos.

```powershell
python .\Fase_4.1_Recuperacion_Consolidado\01_bge_m3_corpus\recuperar_V3.py `
  --query "Escribe aquí la consulta" `
  --recall-top-k 50 `
  --output-top-k 10 `
  --near-duplicate-threshold 0.90 `
  --device cpu
```

`--near-duplicate-threshold` acepta valores entre `0` y `1`; por defecto es
`0.90`. Un valor menor elimina más chunks parecidos.

## Procesar un archivo de preguntas

```powershell
python .\Fase_4.1_Recuperacion_Consolidado\01_bge_m3_corpus\recuperar_V3.py `
  --questions .\ground_truth_15_preguntas.json `
  --output-json .\Fase_4.1_Recuperacion_Consolidado\01_bge_m3_corpus\resultado_v3_preguntas.json `
  --recall-top-k 50 `
  --output-top-k 10 `
  --device cpu
```

El archivo debe ser un arreglo JSON de objetos con `query_id` y `query`. La
salida es un único arreglo JSON con una respuesta por pregunta, en el mismo
orden de entrada.
