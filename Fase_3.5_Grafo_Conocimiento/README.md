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
  --metadata .\Fase_2_Chunking\metadata_general\corpus_bge_m3_semantic_pdf\metadata.jsonl `
  --output .\entrega\grafo\grafo.graphml
```

El script valida duplicados y campos faltantes, extrae entidades y relaciones
semánticas con GLiNER2, conserva la trazabilidad de cada mención y tripleta
hacia documentos y chunks, y escribe el GraphML mediante un archivo temporal
para evitar salidas incompletas.

El modelo por defecto es `fastino/gliner2-multi-v1`. Puede cambiarse con
`--model`; `--threshold` controla la confianza mínima de las extracciones.
Las relaciones se guardan como aristas dirigidas con los atributos `relation`,
`doc_id`, `chunk_id` y `confidence`.

## Instalación

```powershell
python -m pip install -r .\Fase_3.5_Grafo_Conocimiento\requirements-grafo.txt
```

## Generar un grafo por cada configuración de Fase 4.1

Para la ejecución local, deja únicamente estas carpetas hermanas dentro del
directorio padre:

```text
Fase_3.5_Grafo_Conocimiento/
Fase_4.1_Recuperacion_Consolidado/
```

Ejecuta desde `Fase_3.5_Grafo_Conocimiento`:

```powershell
python .\generar_grafos_4_1.py
```

El script detecta automáticamente cada subcarpeta de Fase 4.1 que contenga
`metadata.jsonl`, reutiliza el modelo cargado y genera:

```text
Fase_4.1_Recuperacion_Consolidado/
├── 01_bge_m3_corpus/grafo.graphml
├── 03_granite_corpus/grafo.graphml
├── 04_bge_m3_overlap_1/grafo.graphml
├── 05_granite_overlap_1/grafo.graphml
└── 06_bge_m3_semantic_pdf/grafo.graphml
```

Para procesar una sola configuración:

```powershell
python .\generar_grafos_4_1.py --configuracion 06_bge_m3_semantic_pdf
```

El archivo `generar_grafos_4_1.py` es el ejecutor local oficial de esta fase.
No depende de las demás fases del proyecto: únicamente necesita encontrar la
carpeta hermana `Fase_4.1_Recuperacion_Consolidado` y sus archivos
`metadata.jsonl`. Las carpetas que no tengan metadata son ignoradas. El
modelo se carga una sola vez y se reutiliza para todas las configuraciones.

Cada GraphML se genera dentro de la configuración de Fase 4.1 correspondiente,
por lo que conserva una relación directa con el índice FAISS y la metadata que
acompañan esa configuración.

El archivo `construir_grafo_kaggle.py` es independiente del ejecutor local y
está destinado exclusivamente a copiarse y pegarse en Kaggle.

## Ejecución en Kaggle

Puedes copiar y pegar `construir_grafo_kaggle.py` como una celda/archivo único.
El script busca automáticamente un único `metadata.jsonl` dentro de
`/kaggle/input` y guarda `grafo.graphml` en `/kaggle/working`. No depende de
`construir_grafo.py`.

```python
%pip install -q "gliner2[local]" networkx
!python construir_grafo_kaggle.py
```

Si el dataset contiene varias metadatas, indica la ruta explícita:

```python
!python /kaggle/input/mi-dataset/Fase_3.5_Grafo_Conocimiento/construir_grafo_kaggle.py \\
  --metadata /kaggle/input/mi-dataset/metadata.jsonl \\
  --output /kaggle/working/grafo.graphml
```
