# Granite con solapamiento de una oración

## Propósito

Evaluar Granite sobre todo el corpus usando chunks con una oración de
solapamiento.

## Entrada

Colocar en esta carpeta la metadata combinada de Granite con solapamiento:

```text
metadata.jsonl
```

La metadata PDF se construyó a partir de:

```text
pdfs_standard_objetivo-200palabras_max-250_solapamiento-1_granite_overlap_1
```

El script no crea el solapamiento; únicamente codifica los chunks existentes.

## Ejecución

```powershell
python .\Fase_3_Encoder\05_granite_overlap_1\generar_indice.py
```

Usa Granite con lotes de 16 por defecto. Acepta `--batch-size`, `--device`,
`--checkpoint-every` y `--fresh`.

## Salida

```text
index.faiss
```

No escribe metadata y no aplica un límite adicional de palabras. El progreso se
guarda temporalmente en `.checkpoint/`.
