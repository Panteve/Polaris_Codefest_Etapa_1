# Experimentos de chunking para PDF

Este documento se fundamenta en la documentación técnica y en el plan del
encoder disponibles en el contexto del proyecto CODEFEST AD ASTRA 2026.

El objetivo es preparar cuatro configuraciones comparables para los documentos PDF
provenientes de PDF. El script de esta fase solo limpia la estructura mínima,
divide en oraciones completas y genera metadata. La generación de embeddings,
FAISS y la evaluación pertenecen a Fase 3.

## Reglas comunes

Todos los experimentos usan:

- objetivo de 200 palabras por chunk;
- minimo de 16 palabras por chunk; los chunks de 15 palabras o menos se omiten;
- se filtran tablas de contenido, índices y entradas de navegación con números de página;
- también se filtran índices aplanados por el extractor, aunque no conserven la sección `Table of Contents`;
- las tablas informativas no se eliminan por su formato; deben mostrar además señales de índice y números de página para ser filtradas;
- se eliminan duplicados consecutivos generados por callouts o repeticiones de formato cuando un bloque es igual o está contenido en el anterior;
- se omiten chunks compuestos solo por números sin porcentaje, moneda, fecha/año o unidad contextual;
- máximo absoluto de 250 palabras;
- cortes únicamente después de oraciones completas;
- documentos cuyo formato original es PDF, registrados en
  `Fase_1_Limpieza/output_final_limpio/manifiesto_final_limpio.json`;
- salida separada por configuración;
- `metadata.json`, `metadata.jsonl` y `reporte_chunking_pdf.json`.

La salida separada por configuración se crea automáticamente con el nombre de
la configuración. No es necesario agregar un argumento especial para crear la
subcarpeta del experimento.

El reporte agrupa las alertas en `alertas_por_documento`, usando el `doc_id`
del documento padre. Cada alerta incluye el `chunk_id` correspondiente.

Los parrafos consecutivos solo se agrupan cuando existe una señal de
continuidad tematica, por ejemplo conectores como "ademas" o "asimismo",
referencias anaforicas o terminos relevantes compartidos. Si el siguiente
parrafo introduce un tema nuevo o usa un conector de cambio, queda separado
aunque tenga pocas palabras. Esta regla aplica con y sin solapamiento.

Para comparar BGE-M3 y Granite de forma válida, las configuraciones 1 y 2
deben conservar exactamente los mismos chunks, textos, `chunk_id` y posiciones.
Solo debe cambiar el encoder.

Los comandos se ejecutan desde la raíz del proyecto:

```powershell
cd D:\dev\Polaris_Codefest_Etapa_1
```

## Experimento 1 — Línea base BGE-M3

### Configuración

```text
standard + 200 palabras + 0 solapamiento + BGE-M3
```

### Ejecución

```powershell
python .\Fase_2_Chunking\chunk_pdfs.py `
  --modo standard `
  --objetivo 200 `
  --maximo 250 `
  --solapamiento 0 `
  --etiqueta bge_m3
```

### Salida esperada

```text
Fase_2_Chunking/salida_pdf/
└── pdfs_standard_objetivo-200palabras_max-250_solapamiento-0_bge_m3/
    ├── metadata.json
    ├── metadata.jsonl
    └── reporte_chunking_pdf.json
```

### Por qué se hace

Es la línea base más simple, reproducible y recomendada por la documentación:
chunks de tamaño medio, sin redundancia y respetando oraciones completas.
Permite medir la recuperación de BGE-M3 sin que el solapamiento introduzca
duplicados en el top-10.

En Fase 3 se generan los embeddings BGE-M3 y el índice FAISS correspondiente.

## Experimento 2 — Granite con los mismos chunks

### Configuración

```text
standard + 200 palabras + 0 solapamiento + Granite
```

### Ejecución

```powershell
python .\Fase_2_Chunking\chunk_pdfs.py `
  --modo standard `
  --objetivo 200 `
  --maximo 250 `
  --solapamiento 0 `
  --etiqueta granite
```

### Por qué se hace

Este experimento aísla la variable encoder. Granite y BGE-M3 deben recibir el
mismo texto fragmentado para que una diferencia en `NDCG@10` o `F1@3` pueda
atribuirse al modelo y no a otra estrategia de chunking.

La carpeta se genera de nuevo para conservar una configuración explícita,
pero antes de indexar se debe comprobar que sus `metadata.jsonl` sean
equivalentes al experimento 1 en `doc_id`, `chunk_id`, `posicion` y `texto`.

En Fase 3 se genera un índice separado, por ejemplo:

```text
base_vectorial/encoder_granite_pdf/
├── index.faiss
└── metadata.jsonl
```

## Experimento 3 — BGE-M3 con una oración de solapamiento

### Configuración

```text
standard + 200 palabras + 1 oración de solapamiento + BGE-M3
```

### Ejecución

```powershell
python .\Fase_2_Chunking\chunk_pdfs.py `
  --modo standard `
  --objetivo 200 `
  --maximo 250 `
  --solapamiento 1 `
  --etiqueta bge_m3_overlap_1
```

### Salida esperada

```text
Fase_2_Chunking/salida_pdf/
└── pdfs_standard_objetivo-200palabras_max-250_solapamiento-1_bge_m3_overlap_1/
    ├── metadata.json
    ├── metadata.jsonl
    └── reporte_chunking_pdf.json
```

### Por qué se hace

Una oración repetida puede conservar continuidad entre dos ideas que quedaron
en la frontera de un chunk. Se prueba solo una oración porque un solapamiento
mayor aumentaría el tamaño del índice y el riesgo de recuperar fragmentos
duplicados.

Este resultado se compara contra el experimento 1. Si no mejora la calidad o
produce demasiados duplicados, se conserva la línea base sin solapamiento.

Este experimento no debe compararse directamente contra Granite para decidir
qué encoder es mejor: cambia simultáneamente la segmentación. Si demuestra una
mejora clara, puede repetirse con Granite como experimento adicional.

## Experimento 4 — Late chunking con Granite

### Configuración

```text
late_chunking + 200 palabras + 0 solapamiento + Granite
```

### Ejecución

```powershell
python .\Fase_2_Chunking\chunk_pdfs.py `
  --modo late_chunking `
  --objetivo 200 `
  --maximo 250 `
  --solapamiento 0 `
  --etiqueta granite_pdf
```

### Salida esperada

```text
Fase_2_Chunking/salida_pdf/
└── pdfs_late_chunking_objetivo-200palabras_max-250_solapamiento-0_granite_pdf/
    ├── metadata.json
    ├── metadata.jsonl
    └── reporte_chunking_pdf.json
```

Los registros de `metadata.jsonl` incluyen además:

```json
{
  "chunking_mode": "late_chunking",
  "char_start": 0,
  "char_end": 1240,
  "offsets_base": "texto_normalizado_del_documento"
}
```

### Por qué se hace

Granite admite una ventana de contexto mayor y, según el plan de Fase 3, es el
candidato más adecuado para probar contexto distribuido en PDF largos.

El script todavía no calcula embeddings de tokens. En esta etapa solo deja
preparados los límites y offsets. En Fase 3 se debe:

1. cargar el texto completo del PDF limpio;
2. procesarlo con Granite dentro de su ventana de contexto;
3. obtener embeddings a nivel de token;
4. aplicar mean pooling sobre los tokens de cada rango `char_start`–`char_end`;
5. normalizar los vectores;
6. construir el índice FAISS.

`late_chunking` debe compararse inicialmente contra el experimento 2, usando
Granite en ambos casos. Así se aísla el efecto del método de vectorización.

## Orden recomendado de ejecución conceptual

1. Preparar el experimento 1.
2. Reutilizar o verificar sus mismos chunks para el experimento 2.
3. Comparar el experimento 3 contra el experimento 1 usando BGE-M3.
4. Comparar el experimento 4 contra el experimento 2 usando Granite.
5. Medir `NDCG@10`, `F1@3`, duplicados, tiempo, memoria y tamaño del índice.

## Experimento 5 - Fragmentacion semantica

### Configuracion

```text
semantic + BAAI/bge-m3 + 200 palabras objetivo + 250 maximo + 0 solapamiento
```

### Ejecucion

```powershell
python .\Fase_2_Chunking\chunking-pdfs\chunk_pdfs.py `
  --modo semantic `
  --objetivo 200 `
  --maximo 250 `
  --solapamiento 0 `
  --encoder BAAI/bge-m3 `
  --umbral-semantic 0.80 `
  --etiqueta bge_m3_semantic
```

La salida se crea automaticamente en:

```text
Fase_2_Chunking/chunking-pdfs/
└── pdfs_semantic_objetivo-200palabras_max-250_solapamiento-0_bge_m3_semantic/
    ├── metadata.json
    ├── metadata.jsonl
    └── reporte_chunking_pdf.json
```

### Metodo

El script divide cada seccion en oraciones, genera un embedding por oracion y
calcula la similitud coseno entre oraciones consecutivas. Cuando la distancia
`1 - coseno` supera el umbral y el chunk ya alcanzo el tamano objetivo, se
propone un corte. Siempre se impone el maximo de 250 palabras y los cortes se
realizan unicamente despues de una oracion completa.

`BAAI/bge-m3` es el encoder recomendado para esta prueba porque su ficha
oficial documenta soporte multilingue de mas de 100 idiomas y hasta 8192 tokens.
Como comparacion posterior puede usarse `intfloat/multilingual-e5-large`, que
soporta 94 idiomas y esta entrenado con datos multilingues de similitud y
recuperacion. La eleccion final debe hacerse con las metricas propias del
corpus, no asumir que existe un encoder universalmente mejor.

El modo semantic requiere `sentence-transformers` y `numpy`. No usa modelos
generativos ni modifica el texto original. `--umbral-semantic` controla la
sensibilidad: un valor menor genera mas cortes y uno mayor exige un cambio
tematico mas fuerte.

## Nota sobre tokens

El script registra una estimación determinista de tokens mientras no se haya
seleccionado definitivamente el tokenizer. Cuando Fase 3 defina el tokenizer
de BGE-M3 y Granite, se debe validar el conteo real antes de construir los
índices. No se debe cambiar silenciosamente el límite de palabras entre los
experimentos comparables.
