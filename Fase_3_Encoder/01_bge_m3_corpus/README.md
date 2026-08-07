# BGE-M3 sobre todo el corpus

## Propósito

Construir el índice FAISS de referencia usando `BAAI/bge-m3` sobre todos los
formatos disponibles: JSON, PDF, CSV, TXT, imágenes y PBF convertido a texto.

## Entrada

Colocar en esta carpeta la metadata combinada de la configuración estándar:

```text
metadata.jsonl
```

El script solo lee la metadata. No la modifica ni crea una copia.

## Ejecución

Desde la raíz del proyecto:

```powershell
python .\Fase_3_Encoder\01_bge_m3_corpus\generar_indice.py
```

Opciones principales:

```powershell
--metadata ruta\metadata.jsonl
--output-index ruta\index.faiss
--batch-size 32
--device cuda
--checkpoint-every 10
--fresh
```

## Salida

```text
index.faiss
```

La metadata que acompaña al índice es el `metadata.jsonl` de entrada y debe
mantener exactamente el mismo orden de registros.

## Progreso y reanudación

Muestra registros procesados, porcentaje, velocidad y tiempo transcurrido.
Guarda checkpoints temporales en `.checkpoint/` cada 10 lotes. Si se interrumpe,
la siguiente ejecución continúa desde el último checkpoint compatible. `--fresh`
ignora el checkpoint y comienza desde cero.
