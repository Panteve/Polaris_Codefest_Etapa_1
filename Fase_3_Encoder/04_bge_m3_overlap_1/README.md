# BGE-M3 con solapamiento de una oración

## Propósito

Evaluar el efecto del solapamiento de una oración usando BGE-M3 sobre todo el
corpus.

## Entrada

Colocar la metadata combinada como:

```text
metadata.jsonl
```

La metadata PDF debe provenir de:

```text
pdfs_standard_objetivo-200palabras_max-250_solapamiento-1_bge_m3_overlap_1
```

El solapamiento no lo crea este script. Ya debe estar reflejado en los chunks de
la metadata.

## Ejecución

```powershell
python .\Fase_3_Encoder\04_bge_m3_overlap_1\generar_indice.py
```

Usa BGE-M3 con lotes de 32 por defecto. Acepta `--batch-size`, `--device`,
`--checkpoint-every` y `--fresh`.

## Salida

```text
index.faiss
```

La metadata existente no se modifica. Los checkpoints permiten reanudar la
generación si ocurre una interrupción.
