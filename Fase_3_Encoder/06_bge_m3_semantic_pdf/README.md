# BGE-M3 con chunking semántico en PDF

## Propósito

Evaluar BGE-M3 cuando los PDF utilizan chunks semánticos y los demás formatos
conservan sus chunks estándar.

Es una variante de chunking, no un script que vuelva a calcular la semántica.

## Entrada

Colocar la metadata combinada como:

```text
metadata.jsonl
```

La metadata PDF debe provenir de:

```text
pdfs_semantic_objetivo-200palabras_max-250_solapamiento-0_bge_m3_semantic
```

El chunking semántico ya debe estar terminado antes de ejecutar este script.

## Ejecución

```powershell
python .\Fase_3_Encoder\06_bge_m3_semantic_pdf\generar_indice.py
```

Usa BGE-M3 con lotes de 32 por defecto. Acepta `--batch-size`, `--device`,
`--checkpoint-every` y `--fresh`.

## Salida

```text
index.faiss
```

Solo se genera el índice FAISS. La metadata permanece intacta y los checkpoints
temporales permiten continuar después de una interrupción.
