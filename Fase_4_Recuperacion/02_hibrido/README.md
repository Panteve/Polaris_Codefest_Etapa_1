# Recuperación — configuración híbrida 02

Esta configuración usa un único script para combinar sus dos componentes:

- BGE-M3 sobre los registros no-PDF.
- Granite late sobre los registros PDF.

Cada componente usa su propio índice, metadata y encoder. Los resultados se
combinan mediante Reciprocal Rank Fusion (RRF), porque las puntuaciones de BGE
y Granite no deben sumarse directamente. Después se agrupan los candidatos por
`doc_id`; por defecto cada documento se puntúa con el promedio de sus 3 mejores
chunks fusionados. La salida muestra siempre solo 10 fragmentos.

```powershell
python .\Fase_4_Recuperacion\02_hibrido\recuperar.py `
  --query "..." `
  --candidate-chunks 20 `
  --doc-score mean
```

Para usar suma por documento:

```powershell
python .\Fase_4_Recuperacion\02_hibrido\recuperar.py --query "..." --doc-score sum
```

Por defecto lee:

```text
Fase_3_Encoder/02_hibrido_bge_m3_no_pdf/index.faiss
Fase_3_Encoder/02_hibrido_bge_m3_no_pdf/metadata.jsonl
Fase_3_Encoder/02_hibrido_granite_late_pdf/index.faiss
Fase_3_Encoder/02_hibrido_granite_late_pdf/metadata.jsonl
```

Los índices deben existir y cada uno debe tener su metadata en el mismo orden.
El resultado se guarda automáticamente en `Fase_4_Recuperacion/02_hibrido/resultados.json`.
