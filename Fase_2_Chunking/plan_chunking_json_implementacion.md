# Plan de implementación: chunking de todos los JSON mediante script Python

**Proyecto:** CODEFEST AD ASTRA 2026 — Etapa 1  
**Alcance:** exclusivamente los documentos JSON estructurados entregados por
Fase 1 como archivos `.txt`  
**Responsables:** una persona define/valida el algoritmo; una IA apoya la
generación del script Python  
**Decisión fija:** los JSON se procesarán con late chunking

## 1. Propósito del plan

El objetivo no es leer manualmente todos los documentos. El objetivo es darle a
una IA una especificación suficientemente precisa para que genere un script
Python que:

1. recorra automáticamente todos los `.txt` provenientes de JSON;
2. reconozca las etiquetas estructurales;
3. construya bloques semánticos de forma determinista;
4. prepare los offsets de caracteres y tokens para el late chunking posterior;
5. produzca chunks, metadata y un informe de calidad;
6. registre los casos que requieran revisión humana, sin detener todo el lote.

La IA no debe resumir, traducir, reescribir ni decidir manualmente el contenido
de cada documento. Su función es generar y mejorar el programa.

## 2. Patrones estructurales que el script debe reconocer

La revisión preliminar de algunos TXT permitió identificar que los archivos
estructurados no conservan la sintaxis JSON original, pero sí conservan
etiquetas que permiten reconstruirla. El script debe detectar estos patrones en
**todos los archivos del corpus**, sin asumir que todos aparecen en cada
documento:

```text
title: ...
excerpt: ...
body_paragraphs[0]: ...
body_paragraphs[1]: ...
sections[0].heading: ...
sections[0].paragraphs[0]: ...
lists[0]: ...
images[0].alt: ...
[fila n] ...
```

También hay archivos muy pequeños que contienen solamente títulos, fechas o
texto alternativo de imágenes. El script debe conservarlos para trazabilidad,
pero marcarlos como `contenido_insuficiente` si no aportan texto recuperable.

Por lo tanto, el chunking debe operar por bloques etiquetados cuando existan,
con una ruta de respaldo para archivos sin estructura suficiente. No debe
depender de una lista fija de documentos ni de una revisión manual completa.

## 3. Resultado esperado del script

El programa debe recibir una carpeta raíz y producir, como mínimo:

```text
salida_json/
├── metadata_chunks.json
├── metadata_chunks.jsonl
└── reporte_chunking.json
```

`metadata_chunks.jsonl` contendrá una línea JSON válida por cada chunk. En esta
fase cada línea contiene el texto y la metadata del chunk; todavía no contiene
vectores ni requiere un archivo `.npy`.

`metadata_chunks.json` contendrá esos mismos registros dentro de un arreglo
JSON. Las dos versiones deben representar exactamente los mismos chunks,
metadata, orden y valores; solo cambia el formato de almacenamiento.

`reporte_chunking.json` contendrá el resumen global del procesamiento,
incluyendo documentos procesados, chunks generados, documentos vacíos,
advertencias y errores. No se generará un archivo de errores separado.

Su estructura puede seguir este esquema:

```json
{
  "resumen": {
    "documentos_leidos": 0,
    "documentos_procesados": 0,
    "chunks_generados": 0,
    "documentos_con_error": 0
  },
  "advertencias": [],
  "errores": [],
  "documentos": []
}
```

Metadata mínima por chunk:

```json
{
  "doc_id": "DOC-000001",
  "chunk_id": "DOC-000001-CH-0000",
  "fuente": "archivo_original.json",
  "formato": "json",
  "fenomeno": 1,
  "posicion": 0,
  "texto": "...",
  "num_tokens": 180,
  "num_palabras": 132,
  "idioma": "es",
  "char_start": 0,
  "char_end": 950,
  "token_start": 0,
  "token_end": 180,
  "advertencias": []
}
```

`posicion` comienza en `0`. `chunk_id` debe ser estable si se vuelve a
procesar el mismo documento con la misma configuración.

## 4. Flujo automático que debe implementar el script

### Paso 1: descubrir archivos

- Recorrer recursivamente la carpeta de entrada.
- Procesar solo `.txt` que provengan de la ruta JSON de Fase 1.
- No procesar PDF, CSV, XLSX, imágenes ni PBF en este script.
- Obtener el `doc_id` desde el nombre o metadata existente y conservar la ruta
  original completa como `ruta_origen`.
- Si falta el `doc_id`, generar uno determinista a partir de la ruta y dejar
  una advertencia.

### Paso 2: leer sin destruir estructura

El lector debe conservar:

- el orden de aparición;
- la etiqueta completa;
- el índice de listas, secciones y párrafos;
- el texto asociado;
- offsets de caracteres y, posteriormente, offsets de tokens.

No se debe convertir todo el archivo a un párrafo único antes de analizarlo.

### Paso 3: clasificar etiquetas

El script debe reconocer, como mínimo:

| Etiqueta | Tratamiento |
|---|---|
| `title` | Encabezado principal; asociarlo con el primer bloque |
| `excerpt`, `summary`, `abstract` | Contexto inicial del documento |
| `sections[i].heading` | Inicio de sección |
| `sections[i].paragraphs[j]` | Párrafo de la sección correspondiente |
| `body_paragraphs[i]` | Párrafo narrativo en orden |
| `body_text` | Cuerpo alternativo; usarlo solo si no duplica párrafos |
| `lists[i]` | Lista; conservar relación entre elementos |
| `codigo`, `tipo`, `fecha`, `tema_clave` | Contexto de alertas |
| `municipios`, `poblaciones_afectadas` | Contexto territorial de alertas |
| `images[i].alt` | Usarlo solo si contiene información semántica real |
| `url`, `detail_url`, `pdf_url`, `src`, `href`, DOI | Excluir del texto vectorizado |

El parser debe ser extensible mediante un archivo de configuración, no mediante
decisiones codificadas para un solo proveedor.

### Paso 4: eliminar duplicados y ruido

- Si existen `body_paragraphs` y `body_text` con el mismo contenido, conservar
  una sola versión.
- Normalizar espacios, saltos de línea y caracteres de control.
- No eliminar cifras, fechas, códigos, nombres propios ni unidades.
- Excluir enlaces técnicos, navegación, SVG, imágenes embebidas y registros
  marcados como `excluido_no_contenido`.
- Conservar el valor excluido en metadata de trazabilidad si estaba presente.

### Paso 5: diseñar y construir bloques lógicos

Este paso no queda fijado por una receta única. La persona responsable, con
apoyo de la IA, debe diseñar reglas generales que funcionen para todos los
JSON. El script debe descubrir la estructura disponible en cada archivo y
seleccionar la regla correspondiente de forma determinista.

La decisión debe considerar, como mínimo:

- si el título y el resumen deben acompañar al primer bloque o conservarse
  únicamente como contexto separado;
- cuándo un encabezado debe permanecer unido al primer párrafo;
- cómo mantener relacionadas las listas y sus encabezados;
- cómo unir los campos contextuales de una alerta con el texto que describen;
- cuándo `body_text` es una alternativa a `body_paragraphs` y cuándo es un
  duplicado;
- cómo tratar bloques demasiado pequeños o documentos que solo contienen
  metadata;
- cómo evitar mezclar secciones temáticamente distintas.

La IA debe ayudar a comparar y documentar estas alternativas, pero no debe
introducir una decisión semántica arbitraria ni consultar un modelo generativo
para clasificar cada documento. La decisión final debe quedar escrita en la
configuración y en el informe técnico del responsable de JSON.

El resultado del análisis debe ser una estrategia determinista: dado el mismo
TXT y la misma configuración, el script debe producir los mismos bloques y los
mismos `chunk_id`.

## 5. Segmentación multilingüe

El corpus puede contener español, inglés, portugués, chino, japonés y otros
idiomas. El script debe:

- detectar idioma por bloque, no solo por documento completo;
- registrar idioma y script;
- conservar el texto original;
- reconocer `。`, `！`, `？`, `｡`, `！`, `？`, `.`, `!` y `?` como posibles
  terminadores según el idioma;
- no depender de espacios para separar oraciones en chino o japonés;
- conservar abreviaturas, decimales, URLs excluidas y siglas sin crear cortes
  incorrectos;
- marcar bloques demasiado cortos para una detección confiable;
- permitir una revisión manual únicamente de las advertencias, no de todo el
  corpus.

La segmentación debe ocurrir antes de calcular los offsets de tokens. Si una
oración no puede segmentarse con seguridad, se conserva completa y se registra
`segmentacion_incierta`.

## 6. Preparación para late chunking

El responsable de JSON llega únicamente hasta preparar los chunks y alinear
caracteres con tokens. El encoder se aplicará en una fase posterior.

El flujo de esta fase es:

```text
Documento completo
        ↓
Tokenizer + offsets
```

El script debe conservar el documento completo, calcular los límites de cada
chunk y obtener la correspondencia entre caracteres y tokens. No debe generar
embeddings todavía.

### 6.1 Tokenizador definido para la fase posterior

Usar inicialmente el tokenizador compatible con `BAAI/bge-m3`, porque el
encoder definido para la fase posterior declara licencia MIT, soporte para más
de 100 idiomas, vectores de 1024 dimensiones y hasta 8192 tokens de contexto.

Fuente: [BAAI/bge-m3 en Hugging Face](https://huggingface.co/BAAI/bge-m3).

Para cada documento que quepa en la ventana, esta fase debe:

1. tokenizar el documento estructurado completo;
2. obtener los offsets de caracteres de cada token;
3. guardar el mapeo de cada chunk a sus tokens;
4. guardar la metadata y los offsets en `.json` y `.jsonl`.

No corresponde en esta fase:

- pasar el documento por el encoder;
- obtener embeddings contextualizados;
- aplicar mean pooling;
- normalizar vectores;
- crear índices FAISS.

### 6.2 Documentos que exceden la ventana

Los TXT de JSON que superen 8192 tokens no deben truncarse silenciosamente.
Tampoco deben dividirse automáticamente en ventanas consecutivas por cantidad
de caracteres o tokens. Antes de tokenizar para la fase posterior, el script
debe aplicar una estrategia de partición basada en la estructura del documento
o en quiebres semánticos. La persona responsable, con apoyo de la IA, debe
decidir cuál de las dos funciona mejor para cada tipo de JSON y dejar esa
decisión documentada.

La partición debe:

1. conservar secciones, párrafos, listas y registros completos cuando sea
   posible;
2. evitar separar un encabezado de su contenido inmediato;
3. evitar separar elementos que dependan del mismo contexto;
4. usar límites de oración como frontera de seguridad;
5. producir segmentos que puedan procesarse dentro del contexto del encoder;
6. registrar en el reporte qué documentos requirieron esta partición;
7. guardar los offsets de cada chunk dentro de su segmento;
8. registrar `documento_supera_contexto`.

La partición por estructura o semántica debe ocurrir antes de la fase de
aplicación del encoder. En esta fase solo se preparan los segmentos, chunks,
tokens y offsets; el encoder se aplicará posteriormente sobre cada segmento
válido.

### 6.3 Tamaño de los chunks

Para la primera configuración usar:

- objetivo: 160–200 palabras;
- máximo de salida: 230 palabras;
- límite operativo: 384 tokens;
- solapamiento: 0;
- corte: únicamente al final de una oración o unidad de lista completa.

El máximo de 230 palabras deja margen frente al límite de 250 palabras exigido
en la salida del reto. El límite de tokens tiene prioridad sobre el de palabras.

## 7. Casos especiales

### Artículos y páginas web

Conservar `title`, `excerpt`, secciones y párrafos. No repetir el título en cada
chunk: solo incluirlo en el contexto inicial o como metadata de sección.

### Alertas territoriales

Mantener en el mismo bloque, cuando quepa, el código, tipo de alerta, fecha,
tema, municipios, población afectada y el párrafo que describe el riesgo.

### Listas

No dividir una lista si sus elementos dependen de un encabezado o si perderían
su relación. Si la lista excede el límite, dividir entre elementos completos y
repetir únicamente el encabezado asociado como contexto, sin duplicar el cuerpo.

### Archivos mínimos o sin contenido

No inventar texto. Crear un registro dentro de la lista `errores` de
`reporte_chunking.json` con estados como:

- `contenido_insuficiente`;
- `solo_metadata`;
- `solo_imagen_alt`;
- `sin_bloques_narrativos`;
- `segmentacion_incierta`.

## 8. Qué debe pedirle la persona a la IA programadora

La solicitud a la IA debe exigir que genere:

1. un script Python configurable por argumentos de línea de comandos;
2. funciones separadas para descubrimiento, parsing, deduplicación,
   segmentación, tokenización, alineación de offsets, metadata y reporte;
3. procesamiento por lotes, sin cargar todo el corpus en memoria;
4. reanudación o salida determinista por documento;
5. logs y errores por archivo;
6. validaciones automáticas de límites y correspondencia entre texto, offsets y metadata;
7. una opción `--dry-run` que solo genere el reporte de documentos y bloques;
8. un modo de muestra para procesar primero 20 documentos;
9. configuración externa para patrones de etiquetas y campos excluidos;
10. documentación de instalación, uso y formato de salida.

La IA no debe generar un algoritmo que llame a un LLM para resumir, clasificar,
traducir o decidir dónde cortar. Todas las decisiones deben depender de
etiquetas, reglas, tokenizer, límites y metadata.

## 9. Entregables del responsable de JSON

1. `chunk_json.py` o nombre equivalente.
2. Archivo de configuración de campos y etiquetas.
3. `metadata_chunks.json` con la metadata completa en un arreglo JSON.
4. `metadata_chunks.jsonl` con la misma metadata, una línea por chunk.
5. `reporte_chunking.json` con documentos procesados, chunks, advertencias y
   errores.
5. Documento breve con encoder, versión, parámetros y comando de reproducción.
6. Registro del lote piloto de 20 documentos y de los ajustes realizados antes
   del procesamiento total.
