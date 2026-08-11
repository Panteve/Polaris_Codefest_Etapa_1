# Configuración híbrida: Granite late chunking para PDF

## Propósito

Construir el índice Granite para los PDF de la configuración híbrida. Sus
vectores se combinan con el índice BGE-M3 sin PDF de la carpeta
`02_hibrido_bge_m3_no_pdf`.

## Entradas obligatorias

Colocar en esta carpeta la metadata late chunking únicamente de los PDF que se
van a indexar:

```text
metadata.jsonl
```

Cada registro PDF debe incluir `doc_id`, `chunk_id`, `texto`, `char_start`,
`char_end` y `chunking_mode: late_chunking`.

La metadata debe contener exactamente los registros que tendrán vectores en el
índice y conservar el mismo orden. El script no genera una metadata filtrada.

También se necesita el manifiesto:

```text
Fase_1_Limpieza/output_final_limpio/manifiesto_final_limpio.json
```

El manifiesto debe permitir localizar el texto completo limpio de cada PDF
mediante `archivo_final` o `ruta_final`. Los offsets deben haber sido calculados
sobre esa misma versión normalizada del texto.

## Ejecución

```powershell
python .\Fase_3_Encoder\02_hibrido_granite_late_pdf\generar_indice.py
```

Opciones adicionales:

```powershell
--manifest ruta\manifiesto_final_limpio.json
--device cuda
--checkpoint-every 10
--fresh
```

## Funcionamiento

1. Filtra los registros PDF.
2. Carga el documento completo.
3. Genera embeddings a nivel de token con Granite.
4. Selecciona los tokens dentro de `char_start`–`char_end`.
5. Aplica mean pooling y normaliza cada vector.
6. Construye el índice FAISS.

No se debe modificar el texto ni truncar silenciosamente documentos que superen
la ventana de contexto del modelo.

## Salida

```text
index.faiss
```

La metadata de entrada no se modifica. Durante la ejecución pueden aparecer
checkpoints temporales por documento.
