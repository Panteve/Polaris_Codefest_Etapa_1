# Fase 3 — Selección y comparación de encoders

## 1. Propósito

Esta fase define la estrategia para seleccionar el encoder de embeddings de la base de conocimiento del CODEFEST AD ASTRA 2026.

La decisión se tomará con una comparación reproducible sobre el corpus real del proyecto. Se utilizará `BAAI/bge-m3` como línea base y se evaluará `ibm-granite/granite-embedding-311m-multilingual-r2` específicamente sobre documentos PDF.

No se deben comparar resultados obtenidos con distintos chunks, distintas limpiezas o distintas reglas de recuperación. La única variable principal debe ser el encoder.

Además de la prueba controlada de Granite sobre PDF, se realizará una prueba
adicional de Granite sobre todo el corpus para comparar su comportamiento en
JSON, PDF, CSV, TXT, imágenes con texto extraído y PBF convertido a texto.

## 2. Requisitos del proyecto

La selección debe respetar las especificaciones disponibles del proyecto:

- El corpus contiene documentos en español, inglés y portugués, aunque el inventario también registra algunos documentos en otros idiomas.
- La recuperación debe utilizar modelos encoder y no modelos generativos decoder.
- La base vectorial obligatoria debe utilizar FAISS.
- Los vectores de consulta deben generarse con el mismo encoder utilizado para el índice correspondiente.
- Cada encoder debe tener su propio índice FAISS y su propio archivo `metadata.jsonl`.
- Los fragmentos deben conservar oraciones completas.
- La salida evaluable limita cada fragmento a 250 palabras.
- Las métricas oficiales son `NDCG@10` para fragmentos y `F1@3` para documentos.
- La selección final debe priorizar calidad de recuperación, reproducibilidad, costo computacional y estabilidad entre fenómenos e idiomas.

Estas reglas se fundamentan en la documentación técnica y las guías Markdown disponibles en el contexto del proyecto.

## 3. Evidencia del corpus

Se revisó una muestra aleatoria de los registros del manifiesto posterior a la limpieza y sus archivos de texto correspondientes.

### 3.1 Volumen por formato

El manifiesto contiene aproximadamente 1.726 documentos:

| Formato | Cantidad aproximada |
|---|---:|
| JSON | 944 |
| PDF | 759 |
| CSV | 18 |
| Imagen | 3 |
| PBF | 1 |
| TXT | 1 |

### 3.2 Idiomas

La distribución observada es aproximadamente:

| Idioma | Documentos |
|---|---:|
| Inglés | 1.010 |
| Español | 604 |
| Portugués | 64 |
| Otros o desconocidos | pocos casos |

### 3.3 Longitud

La distribución de `palabras_limpio` muestra un corpus mixto:

- Mediana aproximada: 1.567 palabras.
- Percentil 75: aproximadamente 6.162 palabras.
- Percentil 90: aproximadamente 18.974 palabras.
- Más de 500 documentos superan 5.000 palabras.

Los JSON contienen desde alertas y registros cortos hasta artículos extensos. Los PDF contienen informes técnicos, documentos institucionales y reportes largos. Los CSV son colecciones tabulares que deben tratarse por fila, no como un único documento semántico.

Nota: el manifiesto contiene `conteo_post` principalmente para caracteres antes y después de la pasada posterior. Por ello, los conteos de palabras deben verificarse nuevamente sobre el texto final si se necesitan como medida exacta para la indexación.

## 4. Encoders candidatos

### 4.1 BGE-M3

Modelo: `BAAI/bge-m3`

Características relevantes:

- Más de 100 idiomas.
- Ventana de hasta 8.192 tokens.
- Embeddings densos de 1.024 dimensiones.
- Licencia MIT.
- Recuperación densa, dispersa y multi-vector.
- Buen ajuste para nombres propios, siglas, códigos, municipios, instituciones y vocabulario técnico.
- No requiere una instrucción especial para la consulta.

BGE-M3 será la línea base para todo el corpus y el candidato de respaldo si Granite no demuestra una mejora consistente.

Fuente oficial: [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3).

### 4.2 Granite Embedding Multilingual R2

Modelo: `ibm-granite/granite-embedding-311m-multilingual-r2`

Características relevantes:

- Arquitectura bi-encoder basada en ModernBERT.
- Contexto máximo de 32.768 tokens.
- Embeddings de 768 dimensiones.
- Más de 200 idiomas en el preentrenamiento y soporte reforzado para español y portugués.
- Licencia Apache 2.0.
- Soporte para reducción Matryoshka a 512, 384, 256 o 128 dimensiones.
- Diseñado para recuperación multilingüe y documentos largos.

Granite se evaluará primero sobre PDF porque allí existe la mayor probabilidad de que el contexto largo aporte una mejora.

Fuente oficial: [Granite Embedding 311M Multilingual R2](https://huggingface.co/ibm-granite/granite-embedding-311m-multilingual-r2).

## 5. Hipótesis experimental

### Hipótesis principal

BGE-M3 puede ofrecer una recuperación más versátil en el corpus completo por su capacidad multilingüe y sus funciones densas y léxicas.

### Hipótesis sobre PDF

Granite puede mejorar la recuperación de PDF largos porque admite una ventana de contexto mucho mayor y está optimizado para recuperación de documentos largos.

### Criterio de decisión

Granite solo se incorporará como segundo encoder si mejora de forma consistente las métricas oficiales, especialmente en consultas cuya respuesta dependa de contexto distribuido en documentos PDF.

Una mejora aislada en una consulta no es suficiente para adoptar un segundo índice.

## 6. Diseño de la comparación

### 6.1 Línea base BGE-M3

Construir una base con BGE-M3 para todos los formatos:

- JSON.
- PDF.
- CSV.
- TXT.
- Imágenes con texto extraído.
- PBF convertido a texto.

Para los PDF se conservarán los resultados de BGE-M3 como referencia directa frente a Granite.

### 6.2 Comparación Granite para PDF

Construir un segundo índice únicamente con los chunks PDF, usando exactamente:

- Los mismos documentos PDF.
- El mismo texto limpio.
- Los mismos límites de chunk.
- El mismo `doc_id`.
- El mismo `chunk_id`.
- La misma posición del fragmento.
- La misma metadata.

La única diferencia será el modelo que genera los vectores.

### 6.3 Comparación Granite para todo el corpus

Como experimento adicional, se construirá un índice Granite para todos los
formatos disponibles.

Esta prueba debe utilizar exactamente los mismos documentos, textos limpios,
límites de chunk, `doc_id`, `chunk_id`, posiciones y metadata que la base
BGE-M3. La única variable que debe cambiar es el encoder.

El índice se guardará de forma independiente:

```text
base_vectorial/
└── encoder_granite_corpus/
    ├── index.faiss
    └── metadata.jsonl
```

El experimento permitirá determinar si Granite mejora solamente en PDF o si
también es competitivo en el corpus completo. Deben medirse por separado
NDCG@10, F1@3, tiempo de indexación, tiempo de consulta, memoria y tamaño del
índice.

## 7. Chunking para la prueba(GUIA NO TOCA SEGUIR AL PIE DE LA LETRA)

Configuración inicial recomendada:

- Objetivo de aproximadamente 150–230 palabras.
- Máximo absoluto de 250 palabras para la salida evaluable.
- Cortes únicamente entre oraciones completas.
- Control adicional por tokens del encoder.
- Mantener encabezado y contenido inmediato cuando sea posible.

## 8. Índices FAISS

Se recomienda utilizar vectores normalizados y `IndexFlatIP`, equivalente a similitud coseno cuando los vectores están normalizados.

Estructura durante la comparación:

```text
base_vectorial/
├── encoder_bge_m3/
│   ├── index.faiss
│   └── metadata.jsonl
└── encoder_granite_pdf/
    ├── index.faiss
    └── metadata.jsonl
```

Si Granite no mejora, la entrega final puede contener solamente:

```text
base_vectorial/
└── encoder_bge_m3/
    ├── index.faiss
    └── metadata.jsonl
```

El orden de `metadata.jsonl` debe coincidir exactamente con los identificadores internos asignados por FAISS.

## 9. Recuperación con dos encoders

Cuando existan ambos índices:

1. Codificar la consulta con BGE-M3.
2. Buscar en el índice BGE-M3.
3. Codificar la misma consulta con Granite.
4. Buscar en el índice Granite de PDF.
5. Combinar los rankings sin utilizar modelos generativos.
6. Eliminar duplicados por `chunk_id` cuando corresponda.
7. Agrupar resultados por `doc_id` para obtener los tres documentos principales.
8. Entregar los diez fragmentos mejor posicionados.

La combinación recomendada es Reciprocal Rank Fusion (RRF), porque las puntuaciones de BGE-M3 y Granite tienen escalas y dimensiones diferentes.

## 10. Evaluación

La comparación debe utilizar el mismo conjunto de consultas y la misma lógica de recuperación.

Registrar como mínimo:

| Medida | Propósito |
|---|---|
| `NDCG@10` | Calidad y orden de los fragmentos recuperados |
| `F1@3` | Calidad de los tres documentos recuperados |
| Tiempo de indexación | Costo de construir cada índice |
| Tiempo de consulta | Costo operativo de cada encoder |
| Memoria | Recurso requerido durante la ejecución |
| Tamaño de FAISS | Costo de almacenamiento |
| Estabilidad por fenómeno | Comprobar F1, F2 y F3 por separado |
| Estabilidad por idioma | Comprobar español, inglés y portugués |

La comparación debe incluir resultados separados para:

- Todos los documentos con BGE-M3.
- PDF con BGE-M3.
- PDF con Granite.
- PDF combinando ambos, si se prueba RRF.

## 11. Tabla de decisión

| Resultado | Decisión |
|---|---|
| Granite no mejora `NDCG@10` ni `F1@3` | Mantener solamente BGE-M3 |
| Granite mejora marginalmente y aumenta mucho el costo | Mantener solamente BGE-M3 |
| Granite mejora PDF, pero no el corpus general | Usar Granite solo para PDF y BGE-M3 para el resto |
| Granite mejora de forma consistente en PDF y la combinación mejora el promedio | Entregar ambos índices y usar RRF |
| Resultados inestables por idioma o fenómeno | Revisar chunking y limpieza antes de seleccionar el encoder |

## 12. Recomendación inicial

La configuración inicial más razonable es:

- BGE-M3 para todo el corpus.
- Granite R2 únicamente para PDF como experimento controlado.
- Mismos chunks para ambos modelos en PDF.
- `IndexFlatIP` con vectores normalizados.
- Selección final basada en `NDCG@10`, `F1@3`, costo y reproducibilidad.

Si Granite no produce una mejora clara y estable, se recomienda entregar únicamente BGE-M3. Esto reduce la complejidad del índice, del generador y de la justificación técnica.

## 13. Fuentes externas consultadas

- [BAAI/bge-m3 — ficha oficial](https://huggingface.co/BAAI/bge-m3)
- [BGE M3-Embedding — artículo técnico](https://arxiv.org/abs/2402.03216)
- [Granite Embedding 311M Multilingual R2 — ficha oficial](https://huggingface.co/ibm-granite/granite-embedding-311m-multilingual-r2)
- [Granite Embedding Multilingual R2 — artículo técnico](https://arxiv.org/abs/2605.13521)
