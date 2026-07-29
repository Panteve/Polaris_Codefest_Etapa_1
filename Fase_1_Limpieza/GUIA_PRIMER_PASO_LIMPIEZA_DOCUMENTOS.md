# Guía del primer paso: extracción, limpieza y normalización de documentos

> Esta guía se fundamenta en el contexto y las especificaciones técnicas disponibles del proyecto CODEFEST AD ASTRA 2026, Etapa 1. Incluye además decisiones operativas recomendadas para convertir esos requisitos en un proceso reproducible.

## 1. Propósito

El primer paso consiste en transformar cada archivo original entregado por ADL en una representación textual limpia, normalizada, trazable y lista para fragmentarse posteriormente.

El objetivo de esta fase **no** es crear embeddings, construir el índice FAISS ni producir los chunks definitivos. Tampoco es resumir, traducir o reinterpretar el contenido. El resultado debe conservar el significado y el orden lógico del documento original, eliminando únicamente ruido técnico o repetitivo.

Un buen resultado de esta fase permite:

- recuperar el texto relevante de todos los formatos;
- conservar la relación con el archivo original;
- evitar que cabeceras, menús, pies de página o duplicados contaminen la búsqueda;
- identificar el idioma predominante;
- preservar estructuras útiles para el chunking;
- repetir el procesamiento y auditar sus decisiones.

## 2. Requisitos obligatorios del reto

Durante la extracción y limpieza se debe cumplir, como mínimo, con lo siguiente:

1. Normalizar la codificación a **UTF-8**.
2. Eliminar caracteres de control y espacios redundantes.
3. Detectar y marcar el idioma predominante del documento.
4. Eliminar elementos repetitivos sin valor informativo:
   - cabeceras de página;
   - pies de página;
   - numeración de páginas;
   - boilerplate de sitios web.
5. Preservar el orden de lectura y de aparición del contenido.
6. Asignar a cada archivo un `doc_id` único e inmutable.
7. Mantener la referencia al archivo o fuente original.
8. Tratar cada archivo entregado por ADL como un documento independiente.

El corpus puede contener español, inglés y portugués. La limpieza no debe traducir ni homogeneizar los idiomas.

## 3. Principios que deben guiar la limpieza

### 3.1 Conservar significado antes que reducir texto

Solo se debe eliminar contenido cuando exista evidencia suficiente de que es ruido. Si un elemento puede aportar contexto semántico, debe conservarse.

### 3.2 No modificar el contenido sustantivo

No se debe:

- resumir;
- parafrasear;
- traducir;
- corregir afirmaciones del autor;
- cambiar nombres propios, cifras, fechas o unidades;
- eliminar texto por parecer irrelevante para una consulta concreta;
- usar un modelo generativo para reescribir el corpus.

Sí se pueden realizar normalizaciones mecánicas y documentadas, como corregir espacios repetidos, unificar saltos de línea o retirar caracteres de control.

### 3.3 Mantener la estructura útil

Deben conservarse, cuando existan:

- títulos y subtítulos;
- párrafos;
- listas;
- nombres de columnas;
- etiquetas o nombres de campos;
- secciones;
- orden de páginas;
- referencias comprensibles;
- límites entre registros o elementos de un mapa.

Estas señales serán útiles en la etapa posterior de chunking jerárquico, estructural o por párrafos.

### 3.4 Garantizar trazabilidad

Todo texto limpio debe poder relacionarse con:

- su `doc_id`;
- el nombre o URL de la fuente;
- el formato original;
- su ubicación dentro del archivo, cuando sea posible;
- el archivo original sin modificar.

La evaluación a nivel de documento relaciona los resultados con el campo `fuente`, no únicamente con el `doc_id` arbitrario del equipo. Por eso, la fuente original no debe perderse ni cambiar de forma ambigua.

### 3.5 Separar extracción, limpieza y chunking

Estas fases deben mantenerse separadas:

1. **Extracción:** obtener el contenido desde el formato original.
2. **Limpieza y normalización:** retirar ruido y normalizar el texto.
3. **Chunking:** dividir posteriormente el texto limpio en fragmentos completos.

No conviene imponer cortes definitivos durante la limpieza. En particular, todavía no se deben cortar oraciones para satisfacer un tamaño fijo.

## 4. Inventario previo al procesamiento

Antes de limpiar, se recomienda crear un inventario con una fila por archivo:

| Campo | Descripción |
|---|---|
| `doc_id` | Identificador único, estable e inmutable |
| `fuente` | Nombre exacto, ruta relativa o URL original provista por ADL |
| `formato` | Extensión o tipo real del archivo |
| `fenomeno` | Fenómeno 1, 2 o 3 |
| `tamano_bytes` | Tamaño del archivo |
| `checksum` | Huella para detectar cambios o duplicados exactos |
| `estado` | Pendiente, procesado, con advertencias o fallido |
| `idioma` | Idioma predominante detectado |
| `metodo_extraccion` | Parser, OCR, lector tabular, lector PBF, etc. |
| `advertencias` | Problemas encontrados |

Reglas recomendadas para `doc_id`:

- no derivarlo de una posición que pueda cambiar;
- no reutilizarlo;
- no cambiarlo después de indexar;
- mantener un mapeo permanente entre `doc_id` y `fuente`;
- usar un formato consistente, por ejemplo `DOC-000001`.

## 5. Tratamiento según el formato

### 5.1 PDF

1. Extraer el texto página por página.
2. Preservar el orden de lectura de párrafos y secciones.
3. Detectar si el PDF tiene texto digital, es escaneado o es híbrido.
4. Aplicar OCR únicamente a páginas o regiones que lo necesiten.
5. Eliminar cabeceras, pies y números de página repetitivos.
6. Conservar títulos, subtítulos, listas y texto de tablas cuando sea legible.
7. Se pueden omitir imágenes, elementos decorativos y tablas no textuales cuando no aporten significado semántico legible.
8. Registrar las páginas sin texto o con extracción deficiente.

Controles específicos:

- comparar visualmente una muestra de páginas con el texto extraído;
- revisar documentos con varias columnas;
- detectar palabras pegadas, orden de lectura incorrecto y guiones de final de línea;
- no unir automáticamente palabras separadas por guion si no existe certeza;
- verificar fórmulas, símbolos, tildes y caracteres no latinos.

### 5.2 HTML

1. Conservar solo el texto visible y semánticamente útil.
2. Eliminar:
   - etiquetas y atributos;
   - scripts y estilos;
   - menús globales repetitivos;
   - avisos de cookies;
   - navegación;
   - formularios irrelevantes;
   - publicidad;
   - contenido duplicado del encabezado o pie del sitio.
3. Preservar encabezados, párrafos, listas, tablas y su orden.
4. Conservar como metadata, si existe, la URL, fecha, autor, título y etiquetas.
5. Evitar mezclar esos campos descriptivos con el cuerpo salvo que aporten contexto necesario.

### 5.3 Markdown y TXT

1. Preservar el texto y su orden.
2. Mantener encabezados, listas y separadores que representen estructura.
3. Eliminar caracteres de control, espacios redundantes y ruido técnico.
4. No retirar el marcado ligero si ayuda a reconocer secciones.
5. Detectar problemas de codificación antes de reemplazar caracteres.

### 5.4 JSON

1. Interpretar el JSON; no tratarlo como una cadena plana.
2. Identificar explícitamente los campos que contienen el cuerpo textual, por ejemplo:
   - `title`;
   - `body_text`;
   - `body_paragraphs`.
3. Concatenar los campos seleccionados respetando su orden lógico.
4. Si el cuerpo es una lista de párrafos, conservar el orden de la lista.
5. Mantener como metadata los campos descriptivos, como:
   - URL;
   - fecha;
   - autores;
   - etiquetas;
   - identificadores de origen.
6. Registrar qué campos fueron usados, ignorados o conservados como metadata.

No se debe volcar indiscriminadamente todo el objeto, porque claves técnicas, estructuras internas o metadata repetida pueden contaminar el contenido.

### 5.5 CSV y XLSX

1. Leer correctamente la fila de cabecera.
2. Recorrer los registros fila por fila.
3. Representar cada dato como `nombre_de_columna: valor`.
4. Conservar el orden de las columnas cuando tenga significado.
5. Omitir o normalizar celdas vacías.
6. Preservar números, fechas, unidades y coordenadas sin cambios de interpretación.
7. Registrar la hoja de origen en XLSX.
8. Tratar cada fila como una unidad estructural independiente que podrá usarse en el chunking.

Ejemplo:

```text
país: Colombia | año: 2025 | indicador: inversión en IA | valor: 18.4
```

Controles específicos:

- no perder ceros iniciales de identificadores;
- no convertir códigos en fechas;
- no redondear valores;
- distinguir una celda realmente vacía de valores como `0`, `false` o `N/A`;
- conservar el nombre de la hoja y el número de fila para trazabilidad.

### 5.6 Imágenes

1. Determinar si contienen texto relevante, como infografías, diagramas o gráficos.
2. Aplicar OCR cuando el texto aporte información semántica.
3. Verificar el OCR, especialmente en:
   - cifras;
   - porcentajes;
   - siglas;
   - nombres propios;
   - etiquetas de ejes;
   - leyendas.
4. Conservar una referencia a la imagen y, si aplica, a su página o documento contenedor.
5. No inventar texto ilegible ni completar datos por inferencia.

### 5.7 PBF

1. Usar una herramienta capaz de abrir y decodificar el formato.
2. Recorrer las capas.
3. Recorrer los elementos de cada capa, como municipios o zonas.
4. Convertir sus atributos en pares `atributo: valor`.
5. Conservar el nombre de la capa y un identificador del elemento.
6. Detectar elementos repetidos entre niveles de zoom.
7. Mantener una sola versión cuando la repetición sea producto del nivel de zoom, para no duplicar datos.

Antes de deduplicar, se debe confirmar que los elementos representan realmente el mismo objeto y no observaciones distintas.

## 6. Normalizaciones permitidas

Se recomienda aplicar reglas determinísticas como:

- convertir la salida a UTF-8;
- normalizar saltos de línea;
- eliminar caracteres de control no semánticos;
- sustituir múltiples espacios horizontales por uno;
- reducir saltos de línea excesivos sin borrar los límites de párrafo;
- eliminar espacios antes de signos de puntuación cuando sean artefactos de extracción;
- corregir separaciones mecánicas causadas por maquetación solo cuando la regla sea segura;
- normalizar espacios no separables;
- eliminar cabeceras, pies o numeración cuando se confirme su repetición.

Todas las reglas deben aplicarse de forma reproducible. Conviene registrar la versión del proceso y las transformaciones realizadas.

## 7. Elementos que requieren especial cuidado

### 7.1 Cabeceras y pies de página

No se deben eliminar solo por aparecer al inicio o al final. Primero debe comprobarse que:

- se repiten en muchas páginas;
- son idénticos o casi idénticos;
- no forman parte del contenido;
- su eliminación no borra títulos de sección.

### 7.2 Numeración

Se puede eliminar el número aislado de página. No se deben eliminar:

- números de secciones;
- fechas;
- identificadores;
- cifras de tablas;
- referencias;
- numeración de listas con contenido.

### 7.3 Duplicados

Hay que distinguir entre:

- duplicado exacto de archivo;
- contenido repetido por plantilla;
- versión nueva de un mismo informe;
- fragmentos legítimamente repetidos;
- repetición por niveles de zoom en PBF.

No se deben fusionar versiones distintas de un documento sin una regla explícita.

### 7.4 Guiones y saltos de línea

En PDF, una palabra puede quedar partida al final de una línea. La unión automática solo es segura si se diferencia entre:

- guion tipográfico real: `aero-espacial`;
- palabra cortada por maquetación;
- raya o viñeta;
- signo menos;
- código o identificador.

### 7.5 Texto de tablas

El texto de una tabla debe conservar la relación entre encabezado y valor. Extraer únicamente los valores puede destruir el significado. Si la tabla no puede reconstruirse con suficiente calidad, se debe registrar una advertencia y conservar una representación verificable.

## 8. Idioma

Debe detectarse y registrarse el idioma predominante de cada documento.

Recomendaciones:

- usar códigos consistentes, por ejemplo `es`, `en`, `pt`;
- permitir un valor como `multilingual` o una lista de idiomas cuando sea necesario;
- no eliminar contenido por estar en un idioma distinto al predominante;
- no traducir;
- detectar el idioma sobre suficiente texto, excluyendo menús y boilerplate;
- marcar como `unknown` los documentos demasiado cortos o ambiguos, en vez de inventar una clasificación.

## 9. Estructura recomendada de salida

Conviene conservar tres niveles:

```text
datos/
├── originales/          # Archivos entregados por ADL, sin modificar
├── extraidos/           # Texto bruto obtenido por los parsers u OCR
├── limpios/             # Texto normalizado listo para chunking
├── metadata/            # Un registro por documento
├── reportes_calidad/    # Métricas, advertencias y muestras de revisión
└── manifiesto.jsonl     # Mapeo estable de documentos
```

Ejemplo de registro de documento:

```json
{
  "doc_id": "DOC-000001",
  "fuente": "nombre_original.pdf",
  "formato": "pdf",
  "fenomeno": 1,
  "idioma": "es",
  "metodo_extraccion": "parser_pdf",
  "checksum": "…",
  "estado": "procesado",
  "advertencias": [],
  "version_pipeline": "1.0.0"
}
```

Los campos adicionales son recomendaciones operativas. Los campos obligatorios de cada chunk se crearán en la etapa posterior e incluyen `doc_id`, `chunk_id`, `fuente`, `formato`, `fenomeno`, `posicion`, `num_tokens` y `texto`.

## 10. Flujo recomendado de ejecución

1. Congelar una copia de los archivos originales.
2. Crear el inventario y calcular checksums.
3. Asignar los `doc_id`.
4. Validar que el tipo real de cada archivo coincida con su extensión.
5. Extraer contenido con un método específico por formato.
6. Guardar la extracción bruta.
7. Detectar el idioma predominante.
8. Aplicar las reglas de limpieza y normalización.
9. Guardar el texto limpio sin sobrescribir el bruto.
10. Ejecutar validaciones automáticas.
11. Revisar visualmente muestras y todos los casos con advertencias.
12. Generar un reporte de calidad.
13. Aprobar el corpus limpio para iniciar el chunking.

## 11. Validaciones automáticas mínimas

Por documento:

- `doc_id` presente y único;
- `fuente` presente y resoluble;
- formato reconocido;
- salida válida en UTF-8;
- idioma marcado;
- texto no vacío, salvo excepción documentada;
- ausencia de caracteres de control no permitidos;
- conteo de caracteres, palabras y líneas antes y después;
- porcentaje de texto eliminado;
- número de advertencias;
- hash del archivo original;
- correspondencia uno a uno entre inventario y archivo original.

Para todo el corpus:

- no existen `doc_id` duplicados;
- no existen fuentes sin procesar;
- no existen salidas huérfanas;
- la distribución de formatos coincide con el inventario;
- los documentos fallidos están identificados;
- los casos con reducciones anormalmente altas fueron revisados;
- los idiomas esperados están representados;
- no se sobrescribieron los originales.

Umbrales como “porcentaje anormalmente alto” deben calibrarse observando el corpus. No conviene fijar un valor universal antes de conocer los archivos.

## 12. Revisión manual por muestreo

La revisión automática no es suficiente. Se recomienda:

- revisar al menos una muestra de cada formato;
- revisar ejemplos de cada idioma;
- revisar PDFs de una y varias columnas;
- revisar documentos muy largos y muy cortos;
- revisar todos los archivos procesados con OCR;
- revisar todos los archivos con advertencias;
- comparar el original, la extracción bruta y el texto limpio;
- comprobar que el inicio, una sección intermedia y el final mantienen el orden.

Preguntas para la revisión:

- ¿Se conserva el significado?
- ¿El texto está en el orden correcto?
- ¿Se eliminaron títulos o datos importantes?
- ¿Quedó boilerplate repetido?
- ¿Las tablas conservan el contexto de sus valores?
- ¿Las cifras y nombres coinciden con el original?
- ¿La fuente y el `doc_id` permiten volver al archivo?
- ¿La estructura servirá para dividir el texto sin cortar oraciones?

## 13. Criterios de aceptación

Un documento se considera listo para chunking cuando:

- tiene `doc_id` único e inmutable;
- conserva su `fuente` original;
- su formato y fenómeno están registrados;
- el texto fue extraído con el método correcto;
- está codificado en UTF-8;
- tiene idioma predominante marcado;
- no contiene ruido repetitivo evidente;
- conserva contenido, orden y estructura semántica;
- no fue resumido, traducido ni reescrito;
- las advertencias críticas fueron resueltas o documentadas;
- pasó las validaciones automáticas;
- pasó la revisión manual requerida.

El corpus completo está listo cuando todos los originales aparecen en el manifiesto y cada uno tiene estado `procesado`, `procesado_con_advertencias_aceptadas` o `excluido_con_justificacion`.

## 14. Relación con el paso siguiente

El texto aprobado será la entrada del chunking. En esa etapa se deberá:

- dividir el contenido en fragmentos temáticamente coherentes;
- respetar límites completos de oración;
- evitar frases u oraciones incompletas;
- asignar `chunk_id` y posición ordinal;
- contar tokens;
- conservar el texto sin reescritura;
- justificar la estrategia elegida;
- preparar la metadata obligatoria para FAISS.

Aunque la salida final limita cada fragmento reportado a 250 palabras, ese requisito no debe resolverse destruyendo oraciones durante la limpieza. Los límites se controlarán al diseñar el chunking y al construir la salida de recuperación.

## 15. Checklist breve

### Antes

- [ ] Los originales están protegidos.
- [ ] Existe un inventario completo.
- [ ] Cada archivo tiene `doc_id`, fuente, formato y fenómeno.
- [ ] Se definió un extractor por formato.

### Durante

- [ ] Se guarda la extracción bruta.
- [ ] Se conserva el orden del contenido.
- [ ] Se eliminan únicamente elementos identificados como ruido.
- [ ] Se registra el idioma.
- [ ] Se documentan errores y advertencias.

### Después

- [ ] Todo está en UTF-8.
- [ ] No hay documentos perdidos ni identificadores duplicados.
- [ ] Los originales no fueron modificados.
- [ ] Se compararon muestras contra los originales.
- [ ] OCR, tablas, PBF y casos anómalos fueron verificados.
- [ ] El texto limpio conserva estructura útil para el chunking.
- [ ] El corpus cumple los criterios de aceptación.

