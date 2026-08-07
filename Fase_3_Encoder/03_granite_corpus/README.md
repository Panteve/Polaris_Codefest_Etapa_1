# Granite sobre todo el corpus

## Propósito

Construir un índice FAISS con `ibm-granite/granite-embedding-311m-multilingual-r2`
para JSON, PDF, CSV, TXT, imágenes y PBF convertido a texto, usando los chunks
estándar de Granite.

## Entrada

Colocar en esta carpeta:

```text
metadata.jsonl
```

La metadata debe corresponder a:

```text
corpus_granite_standard
```

## Ejecución

```powershell
python .\Fase_3_Encoder\03_granite_corpus\generar_indice.py
```

El tamaño de lote predeterminado es 16. Se puede modificar con `--batch-size`.
También acepta `--metadata`, `--output-index`, `--device`,
`--checkpoint-every` y `--fresh`.

## Salida

```text
index.faiss
```

El script no genera ni modifica metadata y no rechaza chunks por cantidad de
palabras.

## Progreso y reanudación

Muestra el avance por lotes y guarda checkpoints en `.checkpoint/` cada 10 lotes.
Al finalizar correctamente elimina esos checkpoints temporales.
