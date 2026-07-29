# Contraplan recomendado para el chunking

**Proyecto:** CODEFEST AD ASTRA 2026 — Etapa 1, Base de Conocimiento  
**Alcance:** estrategia de fragmentación y preparación de textos para recuperación vectorial  
**Estado:** propuesta técnica para validar con el corpus del proyecto

## 1. Propósito

Este documento propone una estrategia operativa para el chunking del corpus del proyecto. Se formula a partir de las restricciones de la especificación técnica disponible y de la revisión de evidencia externa sobre recuperación semántica.

La propuesta no asume que exista una configuración universalmente óptima. La configuración definitiva debe seleccionarse mediante una comparación controlada sobre consultas de validación propias.

## 2. Decisión recomendada

Se recomienda utilizar como estrategia principal un **chunking estructural-oracional adaptativo, sin solapamiento por defecto**.

La estrategia debe:

- respetar encabezados, secciones y párrafos cuando estén disponibles;
- dividir únicamente en límites de oraciones completas;
- agrupar oraciones de una misma sección hasta aproximarse a 200 palabras;
- mantener un límite máximo de 250 palabras por fragmento reportable;
- aplicar también un límite de seguridad medido en tokens;
- evitar mezclar secciones temáticamente diferentes;
- conservar la trazabilidad completa hacia el documento original;
- generar fragmentos suficientemente autónomos para responder consultas puntuales.

### Configuración inicial propuesta

| Parámetro | Valor recomendado |
|---|---:|
| Estrategia | Estructural + oracional |
| Tamaño objetivo | 200 palabras |
| Rango de prueba | 150, 200 y 230 palabras |
| Límite duro de salida | 250 palabras |
| Límite de seguridad | 300–350 tokens, según el encoder |
| Solapamiento inicial | 0 |
| Corte permitido | Solo después de una oración completa |
| Cruce de encabezados | No |
| Encoder candidato | BGE-M3 u otro encoder multilingüe validado |

La unidad principal de control debe ser el token del encoder, no únicamente el número de palabras. El límite de 250 palabras pertenece al formato de salida del reto y no garantiza, por sí mismo, una longitud equivalente en tokens entre español, inglés y portugués.

## 3. Algoritmo propuesto

### 3.1 Preparación del documento

Para cada documento limpio:

1. Conservar el `doc_id`, la fuente, el formato y el fenómeno.
2. Mantener el orden original del contenido.
3. Identificar encabezados, títulos, páginas, párrafos y listas cuando sea posible.
4. Detectar el idioma predominante sin traducir el texto.
5. Separar el documento en bloques estructurales.

En PDF, si no es posible recuperar encabezados de forma fiable, los párrafos y los saltos de página deben usarse como señales auxiliares, no como cortes obligatorios.

### 3.2 Segmentación en oraciones

Cada bloque debe segmentarse mediante un separador de oraciones compatible con el idioma del documento.

La segmentación debe:

- conservar la puntuación;
- reconocer abreviaturas, siglas, decimales y referencias;
- no separar una oración por un salto de línea producido por el PDF;
- conservar una oración completa aunque sea larga;
- registrar advertencias cuando una oración no pueda segmentarse con seguridad.

### 3.3 Agrupación de oraciones

Las oraciones se agregan secuencialmente mientras el siguiente elemento no provoque que el fragmento exceda el tamaño objetivo o el límite duro.

Reglas:

1. No combinar oraciones de secciones diferentes.
2. No cerrar un fragmento a mitad de oración.
3. Preferir el último límite de oración disponible antes de exceder el objetivo.
4. Si una sola oración supera el objetivo, conservarla completa y registrar una advertencia.
5. No dividir tablas, registros o listas estructuradas de forma que se pierda la relación entre campo y valor.
6. En documentos tabulares, tratar cada fila o registro autocontenido como unidad estructural antes de aplicar agrupaciones adicionales.

### 3.4 Solapamiento

El primer experimento debe utilizar cero solapamiento. Esto reduce duplicados en el top-10, evita que varios resultados representen esencialmente el mismo texto y disminuye el tamaño del índice.

Se debe probar una segunda variante con una oración de solapamiento únicamente como comparación. No debe adoptarse por defecto salvo que mejore de forma clara la recuperación del pasaje correcto.

## 4. Metadata obligatoria y recomendada

Cada fragmento debe conservar como mínimo:

```json
{
  "doc_id": "DOC-000001",
  "chunk_id": "DOC-000001-CH-0001",
  "fuente": "nombre_original.pdf",
  "formato": "pdf",
  "fenomeno": 1,
  "posicion": 1,
  "num_tokens": 287,
  "num_palabras": 194,
  "texto": "..."
}
```

Se recomienda añadir también:

- sección o encabezado asociado;
- página inicial y final;
- posición de caracteres en el texto limpio;
- idioma;
- versión del pipeline;
- indicador de si el fragmento contiene una tabla, lista o registro;
- advertencias de segmentación.

La metadata debe permitir recuperar tanto el fragmento como el documento completo relacionado.

## 5. Variantes que deben compararse

La estrategia estructural-oracional será la línea base. Se deben comparar, como mínimo, estas configuraciones:

| Variante | Objetivo | Solapamiento | Propósito |
|---|---:|---:|---|
| A1 | 150 palabras | 0 oraciones | Favorecer precisión en consultas puntuales |
| A2 | 200 palabras | 0 oraciones | Configuración base recomendada |
| A3 | 230 palabras | 0 oraciones | Aumentar contexto por fragmento |
| A4 | 200 palabras | 1 oración | Medir beneficio de continuidad local |
| B1 | Punto de quiebre semántico | 0 | Comparar segmentación temática |

El Candidato B debe considerarse experimental. Para implementarlo, se calculan embeddings de oraciones o ventanas pequeñas de oraciones, se detectan cambios bruscos de similitud y se impone siempre el límite máximo de palabras y tokens.

## 6. Qué no se recomienda como primera opción

### 6.1 Fragmentación puramente fija

No se recomienda cortar cada cantidad fija de caracteres o tokens ignorando las oraciones, porque puede producir frases incompletas y separar una idea entre dos fragmentos.

### 6.2 Solapamiento amplio

No se recomienda utilizar solapamientos grandes de forma predeterminada. Pueden mejorar cobertura en algunos casos, pero también aumentan la redundancia, el costo de indexación y la probabilidad de recuperar duplicados.

### 6.3 Chunking guiado por modelos generativos

No se incluye en esta propuesta porque la especificación del reto disponible prohíbe utilizar modelos generativos durante la construcción del índice y la recuperación.

### 6.4 Late chunking como configuración inicial

`Late chunking` es una técnica válida, pero debe tratarse como una optimización posterior. Requiere un encoder de contexto largo, acceso a embeddings a nivel de token y tratamiento especial para documentos que excedan la ventana del modelo.

Solo debe probarse si la evaluación revela errores concretos de pérdida de contexto entre fragmentos, por ejemplo referencias como “este país”, “la ciudad” o “dicha estrategia” cuyo antecedente aparece en un fragmento anterior.

## 7. Evaluación experimental

El conjunto de validación debe contener entre 10 y 15 consultas redactadas manualmente y cubrir:

- los tres fenómenos del reto;
- español, inglés y portugués cuando el corpus lo permita;
- documentos cortos y largos;
- consultas literales y consultas que requieran relacionar conceptos;
- artículos académicos, informes institucionales y documentos con listas o tablas.

Para cada consulta se debe registrar manualmente:

- documento correcto;
- fragmento o pasaje correcto;
- relevancia esperada de los primeros resultados;
- si la respuesta requiere contexto de más de un fragmento.

### Métricas recomendadas

1. `Hit@3` de documento: el documento correcto aparece entre los tres primeros.
2. `Hit@10` de fragmento: el pasaje correcto aparece entre los diez primeros.
3. `NDCG@10`: mide si los fragmentos más relevantes aparecen mejor posicionados.
4. Tasa de fragmentos incompletos o inválidos.
5. Porcentaje de resultados duplicados o casi duplicados.
6. Número total de fragmentos y costo aproximado de indexación.

La decisión no debe basarse en una sola métrica. Una variante que mejora recall pero llena el top-10 de duplicados puede ser peor para este reto que una variante ligeramente menos amplia pero más precisa.

## 8. Criterio de selección

La configuración final debe cumplir simultáneamente:

- 100 % de los fragmentos con oraciones completas, salvo excepciones documentadas;
- ningún fragmento por encima del límite exigido para la salida;
- metadata completa y trazable;
- mejor o comparable `NDCG@10` frente a las demás configuraciones;
- baja proporción de resultados duplicados;
- costo de indexación razonable;
- comportamiento estable en los tres fenómenos y en los idiomas disponibles.

Si ninguna configuración semántica supera claramente a la línea base, debe conservarse la estrategia estructural-oracional por ser más simple, reproducible y auditable.

## 9. Decisión esperada

La configuración de partida recomendada es:

> Fragmentos estructurales y oracionales de aproximadamente 200 palabras, sin solapamiento, con límite máximo de 250 palabras y control adicional por tokens.

El punto de quiebre semántico y `late chunking` deben evaluarse como alternativas experimentales, no incorporarse por complejidad o novedad tecnológica.

## 10. Fundamentación externa

La recomendación se apoya en los siguientes resultados y referencias:

- Chroma reporta que una estrategia heurística de aproximadamente 200 tokens y sin solapamiento ofrece un buen equilibrio entre recuperación y eficiencia, y advierte que el solapamiento puede introducir redundancia: [Evaluating Chunking Strategies for Retrieval](https://www.trychroma.com/research/evaluating-chunking).
- El trabajo original de `late chunking` propone contextualizar primero los tokens del documento y calcular posteriormente los embeddings de los fragmentos: [Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models](https://arxiv.org/abs/2409.04701).
- BGE-M3 documenta soporte multilingüe y una longitud máxima de 8192 tokens: [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3).
- Investigación posterior señala que la estrategia óptima depende de la tarea y que la contextualización puede mejorar algunos escenarios y empeorar otros: [Beyond Chunk-Then-Embed](https://arxiv.org/abs/2602.16974).

Estas fuentes respaldan la necesidad de experimentar, pero no sustituyen la validación sobre el corpus específico del CODEFEST.
