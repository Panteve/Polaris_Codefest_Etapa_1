# Plan de preparación de textos JSON para metadata

**Proyecto:** CODEFEST AD ASTRA 2026 — Etapa 1  
**Alcance:** archivos `.txt` provenientes de JSON procesados en Fase 1  
**Objetivo:** limpiar y consolidar el texto en metadata  
**Fuera de alcance general:** chunking, embeddings, FAISS y generación de
vectores.  
**Excepción:** los documentos cuyo texto limpio supere 250 palabras deben
prepararse para late chunking.

## 1. Propósito

El script debe recorrer automáticamente todos los TXT provenientes de JSON y
generar registros de metadata con texto limpio y legible.

La IA será apoyo para diseñar y generar el script Python. No debe leer ni
procesar manualmente todos los documentos, ni resumir, traducir o reescribir su
contenido.

El resultado de esta fase será un corpus limpio y estructurado. Normalmente se
generará un registro por documento. La única excepción serán los documentos
que superen 250 palabras después de la limpieza: esos deberán quedar divididos
en unidades preparadas para late chunking antes de la fase de encoder.

## 2. Qué debe hacer el script

Para cada TXT debe:

1. leer el archivo completo;
2. identificar y eliminar las etiquetas estructurales del TXT;
3. conservar el texto semánticamente útil en su orden original;
4. eliminar campos técnicos y ruido de navegación;
5. evitar duplicar contenido repetido;
6. detectar idioma cuando sea posible;
7. calcular número de palabras y tokens;
8. guardar un registro de metadata por documento;
9. registrar advertencias y errores en un reporte global.

No debe dividir el texto en chunks ni crear `chunk_id` para documentos de hasta
250 palabras. Para documentos que superen ese límite se aplicará la excepción
descrita en la Sección 10.

## 3. Patrones que debe reconocer

Los TXT pueden contener etiquetas como:

```text
title: ...
excerpt: ...
body_text: ...
body_paragraphs[0]: ...
sections[0].heading: ...
sections[0].paragraphs[0]: ...
lists[0]: ...
images[0].alt: ...
[fila n] ...
```

Las etiquetas sirven para identificar el tipo de contenido, pero no deben
aparecer en el texto final de metadata.

Ejemplo:

Entrada:

```text
title: Example article
excerpt: Short summary.
body_paragraphs[0]: First paragraph.
body_paragraphs[1]: Second paragraph.
```

Texto limpio:

```text
Example article
Short summary.
First paragraph.
Second paragraph.
```

La persona responsable, apoyada por la IA, debe definir reglas generales para
reconocer etiquetas nuevas sin depender de nombres específicos de un único
proveedor.

## 4. Reglas de limpieza

### Conservar

- título y subtítulo cuando tengan contenido informativo;
- resumen, excerpt o abstract;
- encabezados y cuerpo textual, sin sus etiquetas técnicas;
- listas cuando sus elementos tengan significado;
- fechas, cifras, códigos, nombres propios, municipios y nombres de entidades;
- contexto de alertas: código, tipo, fecha, tema, municipios y población
  afectada, siempre que aporte significado;
- registros tabulares completos, manteniendo la relación columna–valor.

### Eliminar

- prefijos como `title:`, `excerpt:`, `body_paragraphs[0]:`,
  `sections[0].heading:` y equivalentes;
- URLs técnicas: `url`, `detail_url`, `pdf_url`, `src`, `href`;
- enlaces de navegación, menús y botones;
- DOI y referencias técnicas que no aporten contenido al texto;
- SVG, HTML embebido, imágenes embebidas y etiquetas de scraper;
- campos marcados como `excluido_no_contenido`;
- información repetida por aparecer simultáneamente en `body_text` y
  `body_paragraphs`;
- espacios redundantes, caracteres de control y saltos de línea artificiales.

La limpieza no debe corregir el contenido con una IA generativa. Si hay
caracteres dañados por la extracción, se registra una advertencia.

## 5. Regla para contenido duplicado

Cuando existan varias representaciones del mismo cuerpo:

- comparar `body_text` con la concatenación de `body_paragraphs`;
- conservar una sola versión;
- preferir la representación que conserve mejor el orden de párrafos;
- no duplicar título, resumen ni cuerpo;
- registrar en el reporte qué documentos tenían contenido repetido.

La comparación debe ser determinista mediante normalización y hash o similitud
textual controlada, no mediante un modelo generativo.

## 6. Metadata de salida

El script debe producir un registro por documento, no por chunk:

```json
{
  "doc_id": "DOC-000001",
  "fuente": "archivo_original.json",
  "formato": "json",
  "fenomeno": 1,
  "texto": "Texto limpio consolidado...",
  "num_tokens": 850,
  "num_palabras": 620,
  "idioma": "es",
  "advertencias": []
}
```

Campos obligatorios de esta fase:

- `doc_id`;
- `fuente`;
- `formato`;
- `fenomeno`;
- `texto`;
- `num_tokens`;
- `num_palabras`.

`idioma` y `advertencias` son campos recomendados para control de calidad.
No deben incluirse `chunk_id`, `posicion`, offsets de tokens, embeddings ni
atributos como `title`, `body_text` o `sections` dentro del registro final.

## 7. Idiomas

El texto debe conservarse en su idioma original. El script debe permitir, como
mínimo, español, inglés, portugués, chino y japonés.

La detección de idioma debe ser una ayuda de metadata, no una razón para
descartar un documento. Si el texto es demasiado corto o mixto, usar un valor
como `unknown` o `mixed` y registrar una advertencia.

No se debe traducir el contenido ni normalizarlo hacia español o inglés.

## 8. Conteo de palabras y tokens

### Palabras

El script debe usar una regla estable y documentada para contar palabras. Debe
conservar cifras y términos con guion cuando representen una unidad semántica.
En chino y japonés, donde los espacios no delimitan palabras de la misma forma,
la regla debe quedar documentada y aplicarse consistentemente.

### Tokens

El conteo de tokens debe realizarse con el tokenizer del encoder elegido para la
fase posterior. Si el encoder aún no está definitivamente seleccionado, el
script debe recibir el tokenizer como configuración y registrar su nombre y
versión en el reporte.

El conteo no implica generar embeddings ni hacer chunking.

## 9. Archivos de salida

El script debe producir únicamente:

```text
salida_json/
├── metadata_json.json
├── metadata_json.jsonl
└── reporte_limpieza_json.json
```

### `metadata_json.json`

Arreglo JSON con un objeto por documento.

### `metadata_json.jsonl`

Un objeto JSON válido por línea, con exactamente los mismos registros y el mismo
orden que `metadata_json.json`.

### `reporte_limpieza_json.json`

Debe incluir, como mínimo:

```json
{
  "resumen": {
    "documentos_leidos": 0,
    "documentos_procesados": 0,
    "documentos_vacios": 0,
    "documentos_con_error": 0,
    "documentos_con_duplicados": 0
  },
  "advertencias": [],
  "errores": [],
  "documentos": []
}
```

No se deben generar archivos de chunks, vectores, embeddings, índices FAISS ni
un archivo separado de errores.

## 10. Excepción: documentos que superan 250 palabras

El límite de 250 palabras se evalúa después de limpiar y consolidar el texto.

Si el texto limpio tiene 250 palabras o menos:

- se conserva como un único registro de metadata;
- no se hace chunking;
- no se crea `chunk_id` ni `posicion`.

Si el texto limpio supera 250 palabras:

1. el reporte debe marcar el documento como `requiere_late_chunking`;
2. el texto debe dividirse en unidades de máximo 250 palabras;
3. los cortes deben respetar oraciones completas y límites estructurales cuando
   existan;
4. cada unidad debe conservar el orden original;
5. cada unidad debe recibir `chunk_id` y `posicion` para que la fase posterior
   pueda aplicar el encoder mediante late chunking;
6. deben conservarse los offsets de caracteres y tokens de cada unidad;
7. el reporte debe indicar cuántas unidades se generaron y qué advertencias
   surgieron.

En esta excepción, el script prepara los fragmentos y sus offsets, pero no
genera embeddings ni ejecuta mean pooling. La aplicación del encoder ocurre en
la fase posterior.

Para estos registros excepcionales se pueden añadir los siguientes campos:

```json
{
  "chunk_id": "DOC-000001-CH-0000",
  "posicion": 0,
  "char_start": 0,
  "char_end": 950,
  "token_start": 0,
  "token_end": 180
}
```

## 11. Casos especiales

### Documentos muy cortos

No inventar contenido. Mantener el texto disponible y registrar estados como:

- `contenido_insuficiente`;
- `solo_metadata`;
- `solo_imagen_alt`;
- `sin_contenido_narrativo`.

### Alertas territoriales

Conservar los campos contextuales útiles junto con el texto de la alerta. No
separar ni eliminar municipios, fechas, tipos de riesgo o población afectada si
son parte del significado.

### Listas y registros

Conservar los elementos en orden. En registros tabulares, mantener los nombres
de columna junto a sus valores:

```text
Year: 2020 | Count: 6828
```

### Texto con idiomas no latinos

No descartar chino o japonés por ausencia de espacios. Conservar los caracteres
originales y calcular `num_palabras` mediante una regla específica y
documentada.

## 12. Requisitos para la IA que genere el script

La persona responsable puede pedirle a la IA que genere un script que incluya:

1. argumentos de entrada y salida configurables;
2. procesamiento recursivo de todos los TXT;
3. funciones separadas para lectura, extracción de texto, limpieza,
   deduplicación, conteo y escritura;
4. procesamiento por lotes sin cargar todo el corpus en memoria;
5. salida determinista;
6. `--dry-run` para revisar conteos sin escribir resultados finales;
7. logs integrados en `reporte_limpieza_json.json`;
8. configuración externa de campos excluidos y patrones de etiquetas;
9. validación de que JSON y JSONL contienen los mismos registros;
10. documentación del tokenizer utilizado para `num_tokens`;
11. una opción para ejecutar pruebas sobre una cantidad configurable de TXT
    seleccionados aleatoriamente, por ejemplo `--sample-size 20`;
12. una opción `--seed` para poder repetir la misma selección aleatoria cuando
    sea necesario comparar resultados.

La selección de prueba debe hacerse sin reemplazo y el reporte debe registrar
los archivos seleccionados. Si no se proporciona `--sample-size`, el script
procesará todos los documentos. Si se proporciona `--seed`, la muestra será
reproducible.

La IA no debe usar un LLM para resumir, traducir, clasificar semánticamente o
decidir qué contenido conservar documento por documento.

## 13. Validación inicial

Antes de procesar todo el corpus, se puede ejecutar el script sobre un lote
piloto de 20 documentos para verificar:

- eliminación correcta de etiquetas;
- ausencia de duplicación entre `body_text` y `body_paragraphs`;
- conservación de cifras, fechas y nombres propios;
- tratamiento de alertas, listas y filas;
- conservación de chino, japonés y otros idiomas;
- igualdad entre JSON y JSONL;
- coherencia de `num_tokens` y `num_palabras`.

Este lote solo sirve para validar el programa. Las reglas deben funcionar para
todo el corpus.
