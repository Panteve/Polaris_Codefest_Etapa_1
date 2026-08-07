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

## Versión para Kaggle con dos T4

Para Kaggle se incluye `generar_indice_kaggle.py`. Es autónoma y no depende de
las rutas locales del proyecto. Busca automáticamente un único `metadata.jsonl`
dentro de `/kaggle/input` y genera el índice en `/kaggle/working/index.faiss`.

En una celda de Kaggle:

```python
!python /kaggle/working/generar_indice_kaggle.py --gpus 2
```

Si el script está dentro del dataset montado en otra ruta, usa la ruta explícita:

```python
!python /kaggle/input/mi-dataset/generar_indice_kaggle.py `
    --metadata /kaggle/input/mi-dataset/metadata.jsonl `
    --gpus 2
```

El script detecta las T4, usa ambas mediante procesamiento multiproceso y muestra
el avance. Por defecto usa lotes de 64; si aparece un error de memoria, prueba:

```python
!python /kaggle/working/generar_indice_kaggle.py --gpus 2 --batch-size 32
```

También conserva checkpoints en `/kaggle/working/.checkpoint_bge_m3`. El índice
final generado es únicamente `index.faiss`; la metadata de entrada no se modifica.
