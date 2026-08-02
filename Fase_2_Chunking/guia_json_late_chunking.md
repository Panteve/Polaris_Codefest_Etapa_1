# Guia de chunking para JSON estructurado de F1

Este documento fija como se deben tratar en Fase 2 los archivos JSON
estructurados del Fenomeno 1 (F1), Inteligencia artificial e innovacion en
entornos militares. Las reglas descritas aqui aplican a los JSON de F1 que
contienen paginas web o articulos estructurados; no sustituyen las reglas
especificas de PDF, CSV, XLSX, imagenes o PBF, ni las de F2 y F3.

## Entrada esperada

Para los JSON de F1, Fase 1 entrega un archivo `.txt` en texto plano. No
conserva la sintaxis JSON,
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
