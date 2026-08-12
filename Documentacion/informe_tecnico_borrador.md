# CODEFEST AD ASTRA 2026

## Informe técnico — Fases 1 y 2: preparación del corpus

**Equipo:** [Nombre del equipo]  
**Versión del documento:** 0.1 — borrador de trabajo  
**Fecha:** [Fecha de entrega]

> Este borrador se fundamenta en la documentación técnica disponible del
> proyecto y en el estado actual de las fases de limpieza y chunking. El
> documento se detiene antes de seleccionar encoder, índice o estrategia de
> recuperación, porque esa decisión aún está pendiente.

## 1. Resumen ejecutivo

Se documenta la preparación del corpus para la Etapa 1 del CODEFEST AD ASTRA
2026. El flujo transforma los documentos suministrados por ADL en texto limpio,
normalizado y trazable, y posteriormente los organiza en fragmentos aptos para
las etapas posteriores de codificación e indexación.

En esta versión no se fija una línea de encoder, índice FAISS ni estrategia de
recuperación. Esas decisiones se mantienen abiertas hasta terminar la
comparación experimental.

## 2. Objetivo y alcance

El objetivo de esta etapa es construir una base de conocimiento vectorial que
permita recuperar los fragmentos y documentos más relevantes ante consultas en
español, inglés y portugués. La evaluación se concentra en la calidad del
ranking recuperado, no en la generación de respuestas ni en el resumen del
contenido.

Este documento cubre únicamente las siguientes etapas:

1. extracción y limpieza de fuentes;
2. identificación estable de documentos;
3. fragmentación del texto;
4. preparación de metadata para las etapas posteriores.

La generación de embeddings, la indexación FAISS, la recuperación, la
evaluación y el grafo de conocimiento quedan fuera de esta versión del informe.

## 3. Corpus y trazabilidad

El corpus está organizado en tres fenómenos temáticos:

1. inteligencia artificial e innovación en entornos militares;
2. seguridad espacial y órbita baja terrestre;
3. dinámicas territoriales en América Latina y el Caribe.

Las fuentes pueden presentarse como PDF, HTML, Markdown/TXT, JSON, CSV, XLSX,
imágenes y PBF. En el estado actual del proyecto, la salida consolidada de la
limpieza contiene aproximadamente 1.726 documentos, con predominio de PDF y
JSON, además de CSV, imágenes, TXT y un PBF representado mediante texto.

Cada documento recibe un identificador estable con la forma `DOC-xxxxxx`. Este
identificador se conserva a través de las fases y permite relacionar el archivo
original, el texto limpio, los fragmentos, los vectores y los resultados.

La metadata conserva, entre otros datos, la fuente original, la ruta, el
formato, el fenómeno, el idioma y el método de extracción. Los documentos
originales no se modifican; las transformaciones se escriben en una salida
separada para preservar la trazabilidad.

## 4. Preprocesamiento de las fuentes

### 4.1 Extracción

El tratamiento depende del formato original:

- **PDF:** extracción página por página, procurando conservar el orden de
  lectura. Cuando existe contenido textual estructurado se conserva como
  Markdown; en los demás casos se usa texto limpio de respaldo.
- **HTML:** conservación del texto visible y eliminación de scripts, estilos,
  navegación y elementos no semánticos.
- **Markdown/TXT:** lectura del contenido y conservación de encabezados,
  párrafos y listas como señales estructurales.
- **JSON:** selección de campos narrativos como `title`, `body_text`,
  `body_paragraphs`, `content`, `abstract` y `summary`, respetando su orden.
  URLs, identificadores y otros campos descriptivos se conservan como metadata
  cuando corresponde.
- **CSV/XLSX:** representación de cada fila como pares `columna: valor`, para
  que los valores no pierdan su contexto.
- **Imágenes:** uso del texto OCR disponible, sujeto a revisión de cifras,
  nombres propios y etiquetas.
- **PBF:** la extracción geoespacial específica queda identificada como una
  limitación; los registros que ya poseen representación textual se conservan
  con su formato original en la metadata.

### 4.2 Limpieza y normalización

La limpieza es conservadora y determinista. Incluye normalización Unicode,
codificación UTF-8, eliminación de caracteres de control, reducción de
espacios redundantes y eliminación de cabeceras, pies de página y números de
página repetidos. También se eliminan artefactos de navegación, etiquetas
técnicas y duplicaciones evidentes.

No se traduce, resume ni reescribe el contenido del autor. El idioma se detecta
y se almacena como metadata, pero no se usa para descartar documentos.

## 5. Estrategia de chunking

### 5.1 Configuración estándar

La configuración estándar usa un objetivo aproximado de 200 palabras por
fragmento y un máximo absoluto de 250 palabras, límite exigido por el formato de
salida. Se descartan fragmentos residuales de 15 palabras o menos cuando no
aportan contenido suficiente.

Los cortes se realizan únicamente después de oraciones completas. Cuando un
bloque supera el objetivo, se retrocede al final de la última oración que cabe
en el límite. De esta forma, una oración no se extiende entre dos fragmentos.

Para PDF se conservan, cuando aportan contexto, los encabezados y las señales
estructurales. Se filtran índices, tablas de contenido y bloques numéricos sin
significado independiente. Las tablas informativas no se eliminan únicamente
por su formato.

### 5.2 Tratamiento por tipo de dato

- En **PDF**, los párrafos y oraciones se agrupan hasta alcanzar el objetivo,
  manteniendo continuidad temática. Esta familia de documentos queda separada
  para comparar posteriormente distintas estrategias de fragmentación.
- En **JSON**, el texto se conserva en su orden original y se prepara para
  late chunking, sin mezclar campos de navegación con el contenido narrativo.
- En **CSV/XLSX**, cada fila conserva los nombres de sus columnas y se procesa
  con late chunking para mantener la relación entre cada registro y su contexto.
- En **PBF**, cada entidad geográfica y sus atributos se conserva como unidad
  textual para el procesamiento posterior con late chunking.
- En **imágenes**, cada bloque OCR se conserva con el título o contexto
  disponible y se prepara bajo la misma estrategia de late chunking.
- En **TXT y otros formatos textuales**, se conserva el orden del contenido y
  se utiliza late chunking como estrategia de preparación.

En consecuencia, la decisión tomada para la Fase 2 es trabajar los archivos que
no son PDF —principalmente JSON, CSV, XLSX, TXT, imágenes y PBF— mediante late
chunking. La estrategia concreta de codificación y pooling se definirá en la
fase de encoder, que todavía no forma parte de este informe.

### 5.3 Variantes experimentales para PDF

Se prepararon tres familias de comparación:

1. estándar sin solapamiento;
2. estándar con solapamiento de una oración;
3. chunking semántico para PDF, usando similitud entre oraciones consecutivas
   y un umbral configurado en `0.80`.

La variante semántica mantiene el máximo de 250 palabras y conserva la regla de
corte en oraciones completas. El solapamiento se limita a una oración para
evitar redundancia excesiva en el top-10.

Estas variantes se dejan registradas como alternativas para una fase posterior.
En este documento no se selecciona ninguna de ellas como configuración final.

## 6. Metadata de los fragmentos

Cada registro de `metadata.jsonl` contiene como mínimo:

| Campo | Descripción |
|---|---|
| `doc_id` | Identificador estable del documento de origen. |
| `chunk_id` | Identificador único del fragmento. |
| `fuente` | Nombre o archivo original suministrado por ADL. |
| `formato` | Formato original del documento. |
| `fenomeno` | Fenómeno temático, con valor 1, 2 o 3. |
| `posicion` | Posición ordinal del fragmento dentro del documento. |
| `num_tokens` | Cantidad de tokens registrada para el fragmento. |
| `texto` | Texto original del fragmento, sin resumen ni traducción. |

También se conservan campos adicionales como `ruta_original`, `seccion`,
`idioma`, `num_palabras` y `chunking_mode` cuando están disponibles.

El orden de los registros en `metadata.jsonl` coincide con el orden de los
vectores insertados en FAISS. Esta correspondencia es necesaria para recuperar
el texto correcto a partir del identificador entero devuelto por el índice.

## 7. Limitaciones y trabajo pendiente

1. Seleccionar la línea de encoder e índice después de comparar las alternativas.
2. Confirmar el tratamiento definitivo de los documentos PBF y de imágenes con
   OCR.
3. Validar el late chunking con el tokenizer exacto del encoder elegido.
4. Verificar que todos los fragmentos finales tengan como máximo 250 palabras.
5. Documentar la recuperación, la evaluación y los entregables en una versión
   posterior del informe.

## 8. Conclusión

La solución implementada establece un pipeline modular y trazable para preparar
el corpus de ADL. La decisión documentada en esta versión es separar la limpieza
de la fragmentación y aplicar late chunking a los formatos que no son PDF,
manteniendo abierta la selección del encoder y de la arquitectura de
recuperación para una fase posterior.
