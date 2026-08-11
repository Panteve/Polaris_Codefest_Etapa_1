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

### 6.4 Late chunking con ambos encoders

Late chunking no debe considerarse exclusivo de Granite. También se probará
con BGE-M3 cuando el documento completo quepa en su ventana de contexto y sea
posible obtener embeddings a nivel de token.

Las comparaciones controladas serán:

- BGE-M3 convencional contra BGE-M3 con late chunking.
- Granite convencional contra Granite con late chunking.
- BGE-M3 contra Granite usando los mismos límites de chunk.

Si un documento supera la ventana de BGE-M3, esa combinación se marcará como
no aplicable para ese documento. No se debe cortar arbitrariamente el texto
solo para forzar la prueba.

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

## 13. Plan de experimentos definido para la Fase 3

La Fase 3 se ejecutará tomando como entrada las distintas metadatas producidas
por los experimentos de chunking. Cada configuración debe conservar sus propios
chunks, metadata e índice FAISS. No se deben mezclar registros provenientes de
configuraciones diferentes dentro de un mismo índice.

### 13.1 Configuraciones principales

#### Principal A — BGE-M3 estándar sobre todo el corpus

Incluye JSON, PDF, CSV, TXT, imágenes y PBF convertido a texto. Para PDF utiliza
la metadata:

```text
pdfs_standard_objetivo-200palabras_max-250_solapamiento-0_bge_m3
```

La metadata combinada correspondiente se identificará como:

```text
corpus_bge_m3_standard
```

Esta será la línea base principal para todas las comparaciones.

#### Principal B — Configuración híbrida BGE-M3 + Granite late chunking

- BGE-M3 para JSON, CSV, TXT, imágenes y PBF.
- Granite con late chunking para PDF.
- PDF basado en:

```text
pdfs_late_chunking_objetivo-200palabras_max-250_solapamiento-0_granite_pdf
```

Esta configuración no se guardará como un único índice, porque BGE-M3 genera
vectores de 1.024 dimensiones y Granite genera vectores de 768 dimensiones. Se
construirán dos índices independientes y la recuperación podrá combinarlos
posteriormente mediante RRF.

La metadata combinada de referencia se identificará como:

```text
corpus_bge_m3_granite_late_pdf
```

Para la construcción física de los índices, cada script deberá filtrar los
registros que le corresponden y escribir un `metadata.jsonl` cuyo orden coincida
exactamente con el índice FAISS respectivo.

### 13.2 Variantes comparables

Las siguientes configuraciones se compararán contra la línea base:

| Configuración | Metadata PDF | Metadata combinada |
|---|---|---|
| Granite estándar sobre todo el corpus | `pdfs_standard_objetivo-200palabras_max-250_solapamiento-0_granite` | `corpus_granite_standard` |
| BGE-M3 estándar con una oración de solapamiento | `pdfs_standard_objetivo-200palabras_max-250_solapamiento-1_bge_m3_overlap_1` | `corpus_bge_m3_overlap_1` |
| Granite estándar con una oración de solapamiento | `pdfs_standard_objetivo-200palabras_max-250_solapamiento-1_granite_overlap_1` | `corpus_granite_overlap_1` |

La variante de Granite con solapamiento requiere una metadata PDF propia. No se
debe reutilizar la metadata generada para BGE-M3 con solapamiento.

### 13.3 Experimento exploratorio semántico

Se evaluará BGE-M3 con chunking semántico en PDF usando:

```text
pdfs_semantic_objetivo-200palabras_max-250_solapamiento-0_bge_m3_semantic
```

La metadata combinada se identificará como:

```text
corpus_bge_m3_semantic_pdf
```

Esta configuración debe entenderse como una variante híbrida del corpus: PDF
semántico y el resto de formatos con sus chunks estándar. No se considera un
experimento semántico completo para JSON, CSV, TXT, imágenes y PBF.

## 14. Estructura de carpetas de metadata

El script `Fase_2_Chunking/metadata_general/combinar_metadata.py` genera la
metadata combinada con nombres estables dentro de `metadata_general/`:

```text
metadata_general/
├── corpus_bge_m3_standard/
├── corpus_bge_m3_granite_late_pdf/
├── corpus_granite_standard/
├── corpus_bge_m3_overlap_1/
├── corpus_granite_overlap_1/
└── corpus_bge_m3_semantic_pdf/
```

Cada carpeta contiene inicialmente:

```text
metadata.json
metadata.jsonl
```

La carpeta PDF estándar de Granite ya está definida como:

```text
pdfs_standard_objetivo-200palabras_max-250_solapamiento-0_granite
```

Esa carpeta es necesaria para construir `corpus_granite_standard` y no debe
reemplazarse por la metadata estándar de BGE-M3.

## 15. Procedimiento de ejecución

El orden de trabajo será:

1. Completar y verificar las metadatas de cada experimento de chunking.
2. Generar la metadata combinada para cada configuración.
3. Ejecutar un script independiente por configuración de encoder y chunking.
4. Generar vectores normalizados con el encoder correspondiente.
5. Construir un `IndexFlatIP` por configuración.
6. Guardar `index.faiss` junto con el `metadata.jsonl` que corresponde al orden
   interno del índice.
7. Registrar tiempo de indexación, memoria, tamaño del índice y cantidad de
   registros.
8. Evaluar NDCG@10 y F1@3 con las mismas consultas y la misma lógica de
   recuperación.

La metadata combinada funciona como insumo de organización del corpus. No
reemplaza la metadata específica que debe acompañar a cada índice FAISS,
especialmente en la configuración híbrida.

Los scripts validan antes de codificar que cada registro contenga los campos
obligatorios `doc_id`, `chunk_id`, `fuente`, `formato`, `fenomeno`, `posicion`,
`num_tokens` y `texto`. No aplican un rechazo por cantidad de palabras: utilizan
los chunks exactamente como fueron entregados en la metadata.

La generación usa checkpoints reanudables. Por defecto se guarda un checkpoint
cada 10 lotes en los experimentos convencionales y cada 10 documentos en late
chunking. Si el proceso se interrumpe, la siguiente ejecución valida la huella
de la metadata y del modelo, carga los vectores ya guardados y continúa desde la
última posición confirmada. `--fresh` permite ignorar un checkpoint existente y
comenzar desde cero.

Los checkpoints son temporales y se eliminan cuando `index.faiss` se escribe
correctamente. No forman parte del entregable.

## 16. Insumos obligatorios para late chunking

El experimento `02_hibrido_granite_late_pdf` no puede ejecutarse únicamente con
el texto de cada chunk. Necesita reconstruir el documento PDF completo y luego
aplicar pooling sobre los tokens que caen dentro de cada rango del chunk.

Antes de distribuir o ejecutar ese script deben estar disponibles estos
insumos:

1. `metadata.jsonl` de la configuración late chunking, con registros PDF que
   incluyan como mínimo:

   - `doc_id`;
   - `chunk_id`;
   - `texto`;
   - `char_start`;
   - `char_end`;
   - `chunking_mode` igual a `late_chunking`.

2. El manifiesto final de limpieza:

```text
Fase_1_Limpieza/output_final_limpio/manifiesto_final_limpio.json
```

3. El texto completo limpio de cada PDF, localizado mediante `archivo_final`
   o `ruta_final` en el manifiesto.

4. La misma normalización de texto utilizada al calcular `char_start` y
   `char_end`. Si se modifica el texto después de crear la metadata, los
   offsets dejan de ser válidos y el índice no debe generarse.

5. Un modelo Granite que pueda procesar el documento completo sin truncarlo.
   Si un documento supera la ventana de contexto del modelo, debe marcarse
   como no aplicable o procesarse con una estrategia definida previamente; no
   se debe truncar silenciosamente.

El script valida la existencia del texto fuente, procesa los documentos
completos, obtiene embeddings a nivel de token, aplica mean pooling sobre cada
rango de caracteres y normaliza los vectores antes de construir FAISS.

La carpeta PDF estándar de Granite con solapamiento ya está disponible:

```text
pdfs_standard_objetivo-200palabras_max-250_solapamiento-1_granite_overlap_1
```

Por tanto, también puede generarse la metadata combinada
`corpus_granite_overlap_1` cuando se ejecute el combinador.

## 17. Convención de salida de cada índice

Cada configuración tendrá una carpeta independiente con esta estructura:

```text
<configuracion>/
├── generar_indice.py
├── index.faiss
└── metadata.jsonl
```

Durante la ejecución puede aparecer temporalmente una carpeta `.checkpoint/`.
El archivo `metadata.jsonl` es un insumo previamente generado y no es modificado
por los scripts. Debe conservar exactamente el orden de los vectores insertados
en `index.faiss`, como exige la especificación técnica.

Los scripts se distribuirán en diferentes equipos. Cada equipo recibirá el
script de su configuración y la metadata correspondiente cuando esta se
encuentre completa. No se ejecutarán scripts de generación hasta cerrar las
metadatas de entrada.

## 18. Comparaciones prioritarias

Las comparaciones se realizarán en este orden:

1. BGE-M3 estándar contra Granite estándar sobre todo el corpus.
2. BGE-M3 estándar contra BGE-M3 con solapamiento.
3. Granite estándar contra Granite con solapamiento.
4. BGE-M3 estándar contra la configuración híbrida con Granite late chunking
   en PDF.
5. BGE-M3 estándar contra BGE-M3 con chunking semántico en PDF.

Las variantes de chunking no deben utilizarse para concluir que un encoder es
mejor que otro, porque en ellas cambian simultáneamente la segmentación y la
representación vectorial. Su objetivo es medir el efecto de la estrategia de
chunking sobre la recuperación.

## 19. Fuentes externas consultadas

- [BAAI/bge-m3 — ficha oficial](https://huggingface.co/BAAI/bge-m3)
- [BGE M3-Embedding — artículo técnico](https://arxiv.org/abs/2402.03216)
- [Granite Embedding 311M Multilingual R2 — ficha oficial](https://huggingface.co/ibm-granite/granite-embedding-311m-multilingual-r2)
- [Granite Embedding Multilingual R2 — artículo técnico](https://arxiv.org/abs/2605.13521)
