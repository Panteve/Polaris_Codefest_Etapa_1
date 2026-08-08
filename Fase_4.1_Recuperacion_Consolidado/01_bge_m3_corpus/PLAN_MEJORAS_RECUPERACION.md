# Plan de mejoras para la recuperacion

## Criterio normativo

Segun la documentacion tecnica del reto, el re-ranking debe operar con vectores,
puntuaciones de similitud y metadata. No se usaran modelos generativos,
BM25 ni cross-encoders en la entrega final.

## Situacion actual

El recuperador codifica la consulta con BGE-M3, busca 20 chunks en FAISS,
aplica filtros, agrupa por `doc_id` y usa el promedio de los tres mejores
chunks para ordenar documentos.

## Fase 1: recuperacion densa

### Overfetch

Comparar `candidate_chunks` con 50, 100, 150 y 200. La salida final seguira
limitada a 10 fragmentos.

Con filtros de fenomeno, idioma o formato, recorrer una cantidad amplia de
resultados FAISS hasta reunir suficientes candidatos validos.

### Validaciones

- Verificar `index.ntotal == len(metadata)`.
- Confirmar que la posicion FAISS corresponde a la misma linea de metadata.
- Conservar `chunk_id`, `doc_id`, `fuente` y `texto` originales.

## Fase 2: fusion de multiples encoders

Si se utilizan varios indices compatibles, combinar sus rankings con metodos
matematicos permitidos.

### CombSUM

Sumar las puntuaciones de similitud de cada indice para el mismo chunk.

### CombMNZ

Multiplicar la suma por la cantidad de indices donde aparece el chunk, premiando
la consistencia entre encoders.

### Reciprocal Rank Fusion (RRF)

Combinar las posiciones de cada chunk en los rankings, en vez de sumar sus
puntuaciones. Es la primera opcion recomendada porque es robusta ante escalas
de similitud diferentes.

Antes de fusionar, verificar que los indices usan la misma metadata y que cada
chunk puede identificarse por posicion o `chunk_id`.

## Fase 3: integracion del grafo

El grafo puede aportar candidatos vinculados con entidades de la consulta y sus
vecinos directos. Esos candidatos se tratan como un ranking adicional y se
fusionan con FAISS mediante RRF, CombSUM o CombMNZ.

El grafo debe conservar la trazabilidad hacia `doc_id` y `chunk_id` para que
cada candidato tenga evidencia en la metadata.

## Fase 4: agregacion por documento

Comparar las estrategias permitidas:

```text
max_pooling       = max(score_chunk)
suma              = sum(score_chunks)
media_ponderada   = weighted_mean(score_chunks)
```

La opcion inicial recomendada es `media_ponderada` combinada con una media de los
tres mejores chunks. La suma debe limitarse o normalizarse para no favorecer
documentos con muchos chunks.

## Fase 5: post-filtros y diversidad

Aplicar filtros directos sobre metadata y puntuaciones vectoriales:

- fenomeno;
- idioma;
- formato;
- rango de fechas, si existe;
- umbral minimo de similitud coseno.

Para evitar fragmentos repetidos:

- maximo 3 fragmentos por `doc_id`;
- eliminar chunks duplicados;
- limitar posiciones muy cercanas;
- completar hasta 10 con los siguientes candidatos validos.

MMR puede evaluarse como mejora basada unicamente en embeddings y scores, sin
generar texto.

## Tecnicas excluidas de la entrega

### BM25

Construye un indice lexicografico sobre los textos, por lo que no se incluira
en la recuperacion final bajo la interpretacion estricta de la documentacion.

### Cross-encoder

Aunque no es generativo, puntua pares de textos directamente. La documentacion
proporciona como alternativas la fusion matematica de rankings, el grafo, la
agregacion por documento y los post-filtros; por eso el cross-encoder queda
fuera de la entrega final.

## Configuracion inicial

```text
candidate_chunks = 150
document_score = max_pooling + media_ponderada
fragmentos finales = 10
maximo por documento = 3
threshold = -1.0 como baseline
```

## Experimentos

```text
baseline_20_mean
dense_150_mean
dense_150_max
dense_150_weighted
multi_encoder_rrf
multi_encoder_combsum
graph_rrf
graph_combsum
```

## Evaluacion

Medir cada variante sobre las 50 consultas del reto:

- `NDCG@10` para fragmentos;
- `F1@3` para documentos;
- consultas sin resultados;
- documentos unicos recuperados;
- tiempo promedio por consulta.

## Orden de implementacion

1. Implementar overfetch y filtros robustos.
2. Comparar max, suma y media ponderada por documento.
3. Anadir limites de duplicacion y diversidad.
4. Fusionar indices con RRF.
5. Integrar el grafo como ranking adicional, si esta disponible.
6. Seleccionar la variante con mejores metricas y cumplimiento normativo.
