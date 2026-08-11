# Opciones para Mejorar un Sistema de Recuperación (Retrieval)

Panorama general de técnicas que existen en la literatura y en la práctica para mejorar la calidad de un pipeline de recuperación de información (RAG / búsqueda semántica), independientemente de un proyecto en particular.

*Nota: se excluyen técnicas que dependen de modelos generativos/decoder (ej. HyDE, reranking o expansión de consulta vía LLM), ya que muchos reglamentos de retrieval "puro" restringen su uso en el módulo de recuperación. Todas las opciones listadas abajo se basan en modelos encoder, métodos estadísticos/léxicos, o técnicas basadas en reglas.*

---

## 1. Mejoras en la fase de recall (traer más candidatos, mejor)

- **Recuperación híbrida (dense + sparse):** combinar embeddings densos (bi-encoder) con métodos léxicos como **BM25** o **TF-IDF**. Los métodos léxicos capturan coincidencias exactas de términos (siglas, nombres propios, códigos) que los embeddings a veces diluyen semánticamente.
- **Múltiples encoders en paralelo:** usar varios modelos de embeddings (distintos tamaños, distintos idiomas, distintos dominios) y fusionar sus resultados.
- **Ampliar el top-k de recall:** traer un pool más grande de candidatos (30–100) antes de aplicar filtros finos, para no perder documentos relevantes por errores del encoder.

## 2. Mejoras en la fase de precisión (reordenar lo ya recuperado)

- **Reranking con cross-encoder:** modelo tipo encoder (no generativo) que evalúa el par (consulta, documento) conjuntamente, mucho más preciso que la similitud coseno de un bi-encoder, pero más costoso computacionalmente (no escalable a todo el corpus, solo al pool ya filtrado).
  - Candidato: `BAAI/bge-reranker-v2-m3` — arquitectura encoder (no generativa), multilingüe, y coherente con el uso de `bge-m3` como bi-encoder por compartir familia de modelo/tokenizer.
  - Si se usan **múltiples bi-encoders** para el recall (ej. Granite + bge-m3), **no** hace falta un reranker distinto por cada uno. El reranker no depende del bi-encoder que trajo el candidato: procesa directamente el texto de la consulta y el texto del fragmento, sin usar los vectores de origen. El flujo correcto es: recall con cada bi-encoder → fusionar resultados (RRF, eliminando duplicados) → aplicar **un único reranker** sobre ese pool ya combinado → reordenar para obtener el top-final. Usar un reranker por cada bi-encoder solo añade cómputo redundante y una capa extra de fusión innecesaria, sin ganancia real.
- **Diversificación de resultados (MMR — Maximal Marginal Relevance):** evitar que el top-k esté lleno de fragmentos casi idénticos del mismo documento, penalizando redundancia.

## 3. Mejoras en la fase de agregación / presentación de resultados

- **Estrategias de pooling para agregar chunks a nivel documento:** max pooling, suma, promedio ponderado — cada una tiene sesgos distintos (max favorece un solo chunk muy bueno; suma/promedio favorece documentos con muchos chunks moderadamente relevantes).
- **Post-filtros basados en metadata o umbrales de similitud:** descartar candidatos que no cumplan ciertos criterios antes de presentar resultados finales.
- **Explicabilidad / trazabilidad:** mostrar por qué un resultado fue recuperado (qué términos coincidieron, qué score tuvo) ayuda a depurar el sistema y detectar fallos sistemáticos.

## 4. Mejoras basadas en evaluación y iteración

- **Sets de validación manual (QA pairs):** construir un conjunto pequeño de consultas con respuestas/documentos relevantes conocidos, para poder comparar estrategias de forma objetiva antes de comprometerse con una configuración.
- **Análisis de errores por categoría:** revisar en qué tipo de consultas falla el sistema (consultas cortas vs. largas, multilingües, con siglas/jerga, etc.) para priorizar qué mejorar primero.
- **A/B testing de configuraciones:** comparar sistemáticamente variantes (con/sin reranking, distintos tamaños de pool, distintos poolings) usando las mismas métricas.

---

## Resumen rápido: de más simple/barato a más costoso

1. Ajustar top-k de recall y estrategia de pooling (casi gratis, solo repriorizar código existente)
2. Añadir BM25 y fusión híbrida (barato, buena relación costo/beneficio)
3. Diversificación de resultados con MMR (barato, solo cálculos sobre vectores ya existentes)
4. Reranking con cross-encoder (moderado, buena mejora en precisión)
