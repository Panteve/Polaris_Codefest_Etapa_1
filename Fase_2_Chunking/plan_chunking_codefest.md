# Plan de comparación de estrategias de chunking

**Proyecto:** CODEFEST AD ASTRA 2026 — Etapa 1, Base de Conocimiento
**Alcance:** Sección 3 (Chunking) de la especificación técnica del reto

---

## Resumen ejecutivo

No existe una única estrategia de chunking que sea correcta por defecto: la evidencia disponible sobre sistemas de recuperación muestra que el tamaño y método de fragmentación puede cambiar la calidad de recuperación tanto o más que el propio modelo de embeddings, y el punto óptimo depende del corpus concreto. Por eso este documento no fija una estrategia definitiva, sino que:

1. Resume qué dice la evidencia empírica disponible sobre chunking para sistemas de recuperación.
2. Identifica qué técnicas quedan descartadas por las reglas específicas de este reto.
3. Define dos candidatos concretos y comparables para el corpus de este reto.
4. Propone una metodología para decidir entre ellos con datos propios, no por intuición.

---

## 1. Restricciones que condicionan las opciones disponibles

Antes de evaluar técnicas hay que fijar el espacio de opciones permitido, según la especificación técnica del reto:

- **Prohibición de modelos generativos.** La especificación prohíbe explícitamente el uso de modelos decoder (GPT, LLaMA, Gemini, Claude, etc.) tanto en la etapa de construcción del índice como en la de recuperación. Esto descarta de entrada cualquier técnica de chunking que dependa de un LLM para decidir los cortes, aunque dicha técnica rinda bien en evaluaciones generales de la industria (ver sección 3).
- **Completitud lingüística obligatoria.** Ningún fragmento puede cortar una oración a la mitad. Cualquier estrategia candidata debe garantizar cortes solo en fronteras de oración completas.
- **Límite de 250 palabras por fragmento en la respuesta final.** Este límite aplica al formato de salida (`resultados.jsonl`), no directamente al chunking, pero conviene que el tamaño de los chunks indexados esté ya cerca de ese límite para minimizar el riesgo de que el texto reportado no coincida con el que generó el match vectorial.
- **Métrica de evaluación NDCG@10 a nivel de fragmento.** A diferencia de otras aplicaciones de recuperación donde el orden de los resultados importa poco (porque un LLM consume todo el contexto igual), aquí el orden de los 10 fragmentos devueltos sí se pondera explícitamente en la nota. Esto favorece estrategias que maximicen la probabilidad de que los primeros puestos del ranking sean genuinamente los más relevantes, más que estrategias que solo maximizan cobertura total (recall) del corpus.

---

## 2. Qué dice la evidencia empírica general sobre chunking

### 2.1 Tamaño de chunk: el trade-off central

La guía práctica más citada en la industria sugiere rangos de 128 a 512 tokens según el caso de uso, con chunks más pequeños favoreciendo consultas puntuales y chunks más grandes favoreciendo tareas que requieren contexto amplio [1].

El trabajo más riguroso disponible sobre el tema es un estudio de Chroma que evalúa relevancia a nivel de token (no solo de documento), lo cual es más representativo de cómo se usa la recuperación en aplicaciones de IA [2]. Sus hallazgos principales:

- Una estrategia heurística simple (dividir por oraciones/caracteres) con un tamaño de chunk de ~200 tokens y **sin solapamiento** tuvo un desempeño consistentemente alto en todas las métricas evaluadas (recall, precisión, eficiencia).
- Reducir el solapamiento entre chunks mejora las métricas de eficiencia, porque el solapamiento introduce contenido redundante que "cuenta doble" en la recuperación.
- El recall tiende a subir con chunks más grandes hasta cierto punto, después del cual la información relevante se diluye dentro del chunk y se vuelve más difícil de recuperar con precisión. Chunks demasiado pequeños, por otro lado, fallan en capturar el contexto necesario para representar una idea completa.
- La elección de estrategia de chunking puede generar diferencias de hasta un 9% en recall entre la mejor y la peor configuración — una diferencia del mismo orden de magnitud, o mayor, que la que suele atribuirse a la elección del modelo de embeddings.

Un estudio independiente presentado en NAACL 2025, que evaluó 25 configuraciones de chunking contra 48 modelos de embeddings distintos, llegó a una conclusión similar: la configuración de chunking influye en la calidad de recuperación tanto o más que el modelo de embeddings elegido [3].

**Implicación para este reto:** vale la pena invertir tiempo real en esta decisión — no es un parámetro secundario frente a la elección del encoder, es comparable en impacto.

### 2.2 Una técnica que rinde bien pero está descartada aquí

En el mismo estudio de Chroma, la estrategia con mejor recall de todas las evaluadas fue un chunker que usa directamente un LLM para decidir dónde cortar el texto. Es una opción real en el estado del arte general de RAG — pero, como se estableció en la Sección 1, queda fuera de las reglas de este reto por el uso de un modelo generativo en la etapa de construcción del índice. Lo mismo aplica a técnicas más recientes como "contextual retrieval", que usan un LLM para generarle a cada chunk una oración de contexto antes de vectorizarlo. Ninguna de estas es una opción viable aquí, independientemente de su rendimiento reportado en otros contextos.

### 2.3 Una técnica de vectorización compatible con las reglas: "late chunking"

Existe una técnica que resuelve parte del trade-off de la sección 2.1 (chunks pequeños = más precisos pero con menos contexto) sin usar ningún modelo generativo. Se llama *late chunking* [4][5]: en vez de cortar el texto primero y vectorizar cada trozo aislado, se codifica el documento completo de una sola vez con un encoder de contexto largo, obteniendo una representación a nivel de token que ya conoce todo el documento; solo después se decide dónde estarían los límites de cada chunk, y se calcula el vector de cada uno promediando (pooling) la porción correspondiente de esa representación ya contextualizada.

El resultado: cada chunk pequeño obtiene un vector que "sabe" en qué contexto aparece dentro del documento completo, sin necesidad de agrandar el chunk ni de usar solapamiento agresivo para compensar la pérdida de contexto.

Es importante aclarar una distinción de diseño: el *late chunking* **no es una forma alternativa de decidir dónde cortar el texto** — es una forma alternativa de decidir **cómo vectorizar** los cortes ya decididos por cualquiera de las estrategias de las secciones 4.1 o 4.2 más abajo. Son dos ejes independientes del diseño, no opciones mutuamente excluyentes.

**Requisito técnico:** esta técnica exige un encoder que soporte contextos largos (los encoders BERT clásicos, tope ~512 tokens, no alcanzan). Un candidato con soporte multilingüe fuerte y contexto de hasta 8192 tokens es BGE-M3 (BAAI), de licencia MIT, que soporta más de 100 idiomas [6] — lo cual cubre holgadamente el requisito de soporte para español, inglés y portugués del corpus de este reto. Nota de implementación: la disponibilidad de *late chunking* "llave en mano" depende del proveedor del encoder — algunos modelos comerciales (p. ej. Jina) exponen esto como un parámetro directo de su API; con un modelo open source como BGE-M3 habría que implementar manualmente el acceso a los embeddings previos al pooling final, lo cual añade complejidad de desarrollo no trivial.

---

## 3. Candidatos a comparar

Se proponen dos estrategias para decidir **dónde cortar el texto**, ambas compatibles con las reglas del reto y con complejidad de implementación distinta. El *late chunking* de la sección 2.3 se trata por separado como una mejora opcional de **cómo vectorizar**, aplicable en principio a cualquiera de las dos.

### 3.1 Candidato A — Estructural + límite por oración

**Lógica:**
1. El texto de cada documento se separa en bloques estructurales: encabezados (para Markdown/HTML) o párrafos, según haya o no señales estructurales disponibles.
2. Dentro de cada bloque, el texto se divide en oraciones completas.
3. Las oraciones se agrupan secuencialmente hasta acercarse a un tamaño objetivo (medido en palabras, no en tokens, para que se corresponda directamente con el límite de 250 palabras del formato de salida).
4. Al llegar al límite, se cierra el chunk. Para no perder contexto en la frontera, se puede arrastrar un pequeño número de oraciones finales (solapamiento ligero) como inicio del siguiente chunk.
5. Nunca se corta una oración a la mitad, en cumplimiento del requisito de completitud lingüística.

**Parámetros a probar:** tamaño objetivo (candidatos: 150, 200 y 230 palabras) y solapamiento (0 vs. 1 oración).

**Ventajas:** simple, determinístico, barato computacionalmente — solo requiere una pasada del encoder por chunk final, sin cómputo adicional.

**Limitación conocida:** al depender solo de posición y tamaño (no del contenido), puede terminar agrupando dentro de un mismo chunk el final de una idea y el inicio de otra completamente distinta, si ambas caen dentro del mismo bloque estructural y por debajo del límite de tamaño.

### 3.2 Candidato B — Punto de quiebre semántico

**Lógica:**
1. El texto se divide en oraciones (mismo paso de segmentación que el Candidato A).
2. Se calcula el embedding de cada oración (o de una ventana pequeña de 2-3 oraciones consecutivas, para reducir el ruido de oraciones muy cortas) usando el mismo encoder que se usará para el índice.
3. Se calcula la distancia (1 − similitud coseno) entre cada par de oraciones consecutivas, obteniendo una secuencia de "distancias locales" a lo largo del documento.
4. Se identifican discontinuidades: puntos donde esa distancia supera un umbral. Un umbral práctico y adaptable es un percentil alto (90-95) sobre todas las distancias locales de ese documento — se ajusta automáticamente al estilo de escritura de cada texto en vez de depender de un número mágico fijo.
5. Se corta un nuevo chunk en cada discontinuidad detectada. Adicionalmente, se impone un techo duro de tamaño (p. ej. 200-230 palabras): si se acumulan suficientes oraciones para llegar a ese techo antes de que aparezca una discontinuidad natural, se fuerza el corte de todos modos en la última frontera de oración disponible — nunca se viola el requisito de completitud lingüística.

**Resultado:** chunks de longitud variable que siguen la estructura temática real del texto, con una garantía de que ninguno crecerá sin control.

**Parámetros a probar:** percentil del umbral (90 vs. 95), unidad mínima para el cálculo de similitud (oración individual vs. ventana de 2-3 oraciones), techo máximo de palabras.

**Costo:** requiere calcular un embedding por cada oración (o ventana) durante la indexación, no solo uno por chunk final — significativamente más cómputo que el Candidato A. Dado que la especificación del reto señala explícitamente la eficiencia computacional como criterio relevante de diseño (los equipos cuentan con recursos limitados), este costo adicional debe sopesarse contra la mejora en calidad que efectivamente se observe, no asumirse como beneficioso por defecto.

### 3.3 Mejora opcional — Late chunking como método de vectorización

Independientemente de si se elige el Candidato A o B para decidir los cortes, se puede evaluar en una segunda fase si vectorizar mediante *late chunking* (sección 2.3) mejora los resultados lo suficiente como para justificar su costo de implementación adicional.

---

## 4. Metodología de comparación con datos propios

El ground truth real de las 50 consultas de evaluación es oculto hasta después de la entrega, así que no se puede optimizar directamente contra él. La alternativa es construir un conjunto de validación propio:

1. **Redactar manualmente entre 10 y 15 preguntas** de prueba, cubriendo los tres fenómenos del reto y, en la medida de lo posible, los tres idiomas del corpus.
2. **Identificar a mano, leyendo el corpus, qué documento y qué pasaje específico responde cada pregunta.** Este es el mismo principio que sigue la metodología de Chroma para construir su propio conjunto de evaluación [2], adaptado a un proceso manual dado que el uso de un LLM para generar este set de validación interno no forma parte del sistema que se entrega, y por tanto no está sujeto a la restricción de la Sección 8.3.
3. **Ejecutar cada candidato** (empezando por A y B con sus distintas combinaciones de parámetros) contra ese conjunto y medir métricas simples: ¿aparece el documento correcto en el top-3? ¿aparece el pasaje correcto en el top-10? Con el ground truth propio ya definido, es posible calcular incluso un NDCG@10 casero para cada configuración.
4. **Elegir la configuración ganadora** con esa evidencia como respaldo, documentando la comparación en el informe técnico — la especificación exige justificar explícitamente la estrategia de chunking elegida, y una comparación empírica propia es una justificación considerablemente más sólida que apoyarse únicamente en literatura general.

---

## 5. Plan de trabajo recomendado

1. Confirmar la implementación del Candidato A (estructural + oracional) — ya existe una primera versión funcional.
2. Implementar el Candidato B (punto de quiebre semántico).
3. Construir el conjunto de validación propio (10-15 preguntas con respuesta conocida).
4. Comparar A y B, incluyendo un barrido de al menos 2-3 combinaciones de parámetros por candidato, contra el conjunto propio.
5. Seleccionar la estrategia de corte ganadora.
6. Solo si el tiempo disponible lo permite y los errores observados apuntan específicamente a pérdida de contexto entre chunks (p. ej. fallos en preguntas que dependen de referencias resueltas en otro párrafo), evaluar agregar *late chunking* como mejora de vectorización sobre la estrategia ganadora, y volver a medir contra el mismo conjunto de validación.
7. Documentar la decisión final, los candidatos descartados y la razón de la elección en el documento técnico de entrega.

---

## 6. Fuentes consultadas

[1] Milvus — "What is the optimal chunk size for RAG applications?" — https://milvus.io/ai-quick-reference/what-is-the-optimal-chunk-size-for-rag-applications

[2] Chroma Research — "Evaluating Chunking Strategies for Retrieval" — https://www.trychroma.com/research/evaluating-chunking

[3] Fast.io — "Best Chunking Strategies for RAG Pipelines (2026)" (referencia al estudio de Vectara, NAACL 2025) — https://fast.io/resources/best-chunking-strategies-for-rag/

[4] Jina AI — "Late Chunking in Long-Context Embedding Models" — https://jina.ai/news/late-chunking-in-long-context-embedding-models/

[5] Günther et al. — "Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models" (arXiv:2409.04701) — https://arxiv.org/pdf/2409.04701

[6] BAAI — Ficha del modelo BGE-M3 en Hugging Face — https://huggingface.co/BAAI/bge-m3
