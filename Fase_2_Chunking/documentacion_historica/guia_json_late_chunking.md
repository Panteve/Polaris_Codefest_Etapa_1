# Guia de chunking para JSON estructurado de F1

Este documento fija como se deben tratar en Fase 2 los archivos JSON
estructurados de F1, F2 y F3. Las reglas aplican a JSON que contienen paginas
web, articulos, alertas o reportes estructurados; no sustituyen las reglas
especificas de PDF, CSV, XLSX, imagenes o PBF.

## Entrada esperada

Para los JSON de los tres fenomenos, Fase 1 entrega un archivo `.txt` en texto
plano. No conserva la sintaxis JSON,
pero mantiene etiquetas que representan la estructura original, por ejemplo:

```text
title: Capacitacion Cuprum - CENIA

sections[0].heading: Capacitacion Grupo Principal

sections[0].paragraphs[0]: Durante el segundo semestre se realizo...

lists[0]: Inteligencia Artificial. Un breve viaje...
```

Las etiquetas forman parte del texto y deben utilizarse como señales de
estructura. No deben aparecer separadas de la información que describen.

## Señales estructurales

El chunker debe interpretar, cuando existan:

- `title` como titulo del documento;
- `sections[i].heading` como encabezado de una seccion;
- `sections[i].paragraphs[j]` como parrafos asociados a esa seccion;
- `lists[i]` como elementos de una lista o unidades breves de contenido.

No se deben mezclar en un mismo chunk secciones tematicamente diferentes si
existe un limite estructural natural. Un encabezado debe permanecer junto al
primer contenido de su seccion, siempre que el limite de tokens y palabras lo
permita.

## Late chunking

Para estos documentos se evaluara late chunking como metodo de vectorizacion:

1. Se conserva el documento completo y su orden estructural.
2. El encoder procesa el documento completo dentro de su ventana de contexto.
3. Despues se determinan los limites de los chunks usando secciones, parrafos,
   listas y oraciones completas.
4. Se calcula el embedding de cada chunk a partir de los embeddings de los
   tokens que pertenecen a su rango.

Late chunking no reemplaza la estrategia de decidir donde cortar. Puede
combinarse con chunking estructural y oracional. Su uso debe validarse contra
la estrategia convencional con las mismas consultas y metricas.

## Reglas por tipo de JSON

### Articulos y paginas web de F1 y F2

Se deben mantener el titulo, resumen o excerpt, cuerpo, parrafos, secciones,
topics y keywords. Cuando `body_paragraphs` y `body_text` repitan el mismo
contenido, se conserva una sola copia. Las fechas y autores pueden conservarse
como metadata del documento y no deben convertirse en ruido repetido dentro de
cada chunk.

### Alertas y reportes territoriales de F3

Los parrafos del cuerpo deben permanecer vinculados a su contexto. En una
alerta, campos como `codigo`, `tipo`, `fecha_emision`, `tema_clave`,
`municipios` y poblaciones afectadas son contexto semantico util y pueden
formar un bloque de contexto junto al cuerpo de la alerta. No se deben separar
municipio, tipo de riesgo o fecha del texto que describe la alerta si caben en
el mismo fragmento.

### Campos tecnicos excluidos

No deben formar parte del texto vectorizado las URLs tecnicas (`url`,
`detail_url`, `pdf_url`, `src`, `href`), enlaces de navegacion, DOI, SVG o
imagenes embebidas, ni catalogos o registros del scraper marcados como
`excluido_no_contenido`. Estos archivos se conservan solo para trazabilidad.

## Secuencia recomendada para late chunking

1. Leer el `.txt` completo y conservar el orden de sus etiquetas estructurales.
2. Agrupar titulo, etiquetas semanticas, metadata contextual y cuerpo en
   bloques logicos.
3. Pasar el documento completo al encoder de contexto largo, si cabe en su
   ventana.
4. Definir los limites despues de la contextualizacion, usando bloques,
   parrafos, listas y oraciones completas.
5. Calcular el vector de cada chunk con los embeddings de tokens de su rango.
6. Conservar en cada chunk la seccion o bloque de origen junto con la metadata
   obligatoria.

Si un documento excede la ventana del encoder, se debe registrar la situacion
y aplicar una particion previa por bloques estructurales completos. No se debe
cortar arbitrariamente un JSON largo por caracteres.

## Reglas de corte

- No cortar una oracion a la mitad.
- No separar un encabezado de su contenido inmediato cuando sea posible.
- No romper una lista de forma que se pierda la relacion entre sus elementos.
- Mantener cada fragmento por debajo de 250 palabras para la salida evaluable.
- Controlar tambien el limite de tokens del encoder.
- Evitar solapamiento por defecto, salvo que una comparacion empirica lo
  justifique.
- Para documentos cortos, conservar un solo fragmento si no se supera el
  limite.
- Para documentos largos, dividir primero por estructura y despues por
  oraciones completas.

## Metadata y trazabilidad

Cada fragmento debe conservar como minimo:

```json
{
  "doc_id": "DOC-000001",
  "chunk_id": "DOC-000001-CH-0001",
  "fuente": "nombre_original",
  "formato": "json",
  "fenomeno": 1,
  "posicion": 0,
  "num_tokens": 0,
  "texto": "..."
}
```

Cuando sea posible, se recomienda agregar el encabezado o seccion asociada,
el idioma, la posicion de caracteres en el texto limpio y la ruta al archivo
original. El `doc_id` debe permanecer estable y el `chunk_id` debe ser unico
dentro del indice.

## Nota de validacion

Late chunking requiere un encoder de contexto largo y acceso a embeddings a
nivel de token. Debe compararse con una linea base de chunking estructural y
oracional sobre un conjunto de consultas representativo. La seleccion final
debe basarse en NDCG@10, calidad de recuperacion, costo y reproducibilidad.
