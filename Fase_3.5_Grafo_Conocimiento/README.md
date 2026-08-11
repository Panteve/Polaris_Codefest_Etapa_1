# Fase 3.5 - Grafo de conocimiento

Esta carpeta corresponde al componente bonus de la sección 7 del PDF técnico.
Se ejecuta después de generar la metadata/chunks y antes de integrar la
recuperación de la Fase 4.

## Entrada

Debe usar el mismo `metadata.jsonl` que acompaña al índice FAISS elegido. Cada
registro debe incluir `doc_id`, `chunk_id`, `fuente`, `fenomeno` y `texto`.

## Ejecución

```powershell
python .\Fase_3.5_Grafo_Conocimiento\construir_grafo.py `
  --metadata .\Fase_2_Chunking\metadata_general\corpus_bge_m3_standard\metadata.jsonl `
  --output .\entrega\grafo\grafo.graphml
```

El script valida duplicados y campos faltantes, extrae entidades con reglas
deterministas, conserva la trazabilidad hacia documentos y chunks, y escribe el
GraphML mediante un archivo temporal para evitar salidas incompletas.

Instalación de la dependencia:

```powershell
python -m pip install -r .\Fase_3.5_Grafo_Conocimiento\requirements-grafo.txt
```
