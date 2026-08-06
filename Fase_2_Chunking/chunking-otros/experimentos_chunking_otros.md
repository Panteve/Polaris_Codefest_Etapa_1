# Chunking para CSV, imágenes y TXT derivados de PBF

## Alcance

En la limpieza final, los 18 CSV, las 3 imágenes y el PBF quedaron
representados como TXT. El manifiesto conserva el formato original, por lo que
el script usa ese campo para aplicar reglas diferentes sin depender de la
extensión final.

## Estrategia recomendada

La configuración inicial debe ser una unidad autocontenida por registro:

- CSV: una fila por chunk, conservando Columna: valor y la relación entre
  columnas.
- PBF: una entidad geográfica por chunk, conservando sus atributos y valores.
- Imagen: cada bloque textual extraído por OCR; el título de la imagen se
  antepone como contexto cuando existe.
- Sin solapamiento.
- Sin cortes semánticos.
- Máximo de 250 palabras por chunk.
- Se conserva doc_id, chunk_id, fuente, fenómeno, idioma y posición.

Esta estrategia es preferible porque una fila de CSV, una entidad geográfica o
un registro de tabla ya constituye una unidad semántica más natural que un
bloque arbitrario de 200 palabras.

## Experimentos que sí valen la pena

### Experimento 1 — Registro individual

Es la línea base obligatoria y la configuración recomendada. Cada fila o
registro se indexa como una unidad. Deben revisarse:

- que no se pierdan nombres de columnas;
- que cada entidad conserve sus atributos;
- que los chunks no superen 250 palabras;
- que no haya duplicados de registros;
- que el texto de OCR conserve títulos, fechas y valores.

### Experimento 2 — Agrupación de registros

Es opcional. Se pueden agrupar varias filas del mismo archivo hasta
aproximadamente 150–200 palabras, siempre que no se mezclen documentos ni se
rompa la relación entre registros.

Solo se justifica si la recuperación de consultas que comparan varias filas
resulta débil. Tiene como costo que una consulta sobre una entidad puede
recuperar un chunk con muchas entidades irrelevantes.

### Experimento 3 — Imagen con contexto ampliado

Es opcional y aplica únicamente a imágenes con filas o categorías breves.
Puede compararse el registro individual contra un chunk que incluya el título
de la imagen y dos o tres registros cercanos.

No se recomienda aplicarlo a todas las imágenes automáticamente, porque una
imagen puede ser una tabla, un indicador o un listado con estructuras
diferentes.

## Experimentos que no se recomiendan

- Solapamiento entre filas: produce duplicados y no aporta contexto útil.
- Cortes por caracteres o tokens dentro de una fila: destruyen la relación
  columna–valor.
- Chunking semántico con embeddings de cada fila: el corpus es pequeño y las
  unidades ya vienen estructuradas; el costo no se justifica inicialmente.
- Late chunking: no aporta una ventaja clara cuando cada registro es corto y
  autocontenido.

## Salida

El script genera los archivos metadata.json, metadata.jsonl y
reporte_chunking_otros.json dentro de salida_otros.

El conteo num_tokens se mantiene como estimación temporal y no se añade un
campo num_tokens_metodo al registro. Cuando se defina el encoder de la base,
el conteo exacto debe validarse con su tokenizer.
