# Pipeline de limpieza de documentos

Este script implementa el primer paso de la base de conocimiento de CODEFEST
AD ASTRA 2026. Su objetivo es convertir los archivos originales entregados por
ADL en texto limpio, normalizado y trazable para el chunking posterior.

La explicación y las decisiones de este documento se fundamentan en la
documentación técnica disponible del proyecto y en la guía local de limpieza.

## Qué hace y qué no hace

El pipeline hace lo siguiente:

1. Recorre un directorio de entrada de forma recursiva.
2. Trata cada archivo como un documento independiente.
3. Asigna un `doc_id` según la posición del documento en la entrada.
5. Extrae texto según el formato.
6. Guarda la extracción bruta sin modificarla.
7. Normaliza y limpia el texto.
8. Detecta el idioma predominante.
9. Registra advertencias, estadísticas y método de extracción.

No hace todavía:

- chunking;
- embeddings;
- indexación FAISS;
- recuperación;
- traducción, resumen o reescritura;
- construcción del grafo de conocimiento.

Separar estas fases permite revisar el texto antes de fragmentarlo y evita que
una transformación de limpieza se confunda con una decisión de chunking.

## Requisitos

Se necesita Python 3.10 o superior. Las dependencias recomendadas están en
`requirements-limpieza.txt`:

```powershell
python -m pip install -r .\requirements-limpieza.txt
```

Los lectores son opcionales. Si falta una dependencia, el documento no falla
silenciosamente: el manifiesto registra la advertencia y el estado resultante.

| Formato | Método | Dependencia |
|---|---|---|
| PDF | Extracción página por página | `pypdf` |
| HTML | Texto visible, quitando scripts, navegación y estilos | `beautifulsoup4` |
| MD/TXT | Lectura con detección de encoding común | Ninguna |
| JSON | Campos textuales conocidos, respetando el orden | Ninguna |
| CSV | Encabezado unido a cada valor de fila | Ninguna |
| XLSX | Hojas y filas estructuradas | `openpyxl` |
| PNG/JPG/TIFF | OCR | `pillow`, `pytesseract` y Tesseract instalado |
| PBF | Pendiente de lector geoespacial específico | No incluido todavía |

## Uso básico

```powershell
python .\limpiar_documentos.py `
  .\datos\originales `
  .\datos\procesados `
  --formatos pdf,json `
  --fenomeno 1 `
  --verbose
```

`--formatos` acepta una lista separada por comas, por ejemplo `pdf,json`.
El identificador de cada documento se calcula según su posición global en la
entrada, incluso cuando su formato no fue seleccionado. Así, en el orden
`pdf, json, pdf`, al procesar solo `pdf` se asignan `DOC-000001` y
`DOC-000003`.

Cuando la entrada es una carpeta `F1_...`, `F2_...` o `F3_...`, el script
calcula automáticamente el inicio global usando `--fenomeno` y contando todos
los formatos reconocidos de los fenómenos anteriores. Si el último documento
global anterior fue `DOC-000287`, la siguiente carpeta comenzará en `DOC-000288`.

`--id-inicial` queda disponible solo para sobrescribir manualmente ese cálculo:

```powershell
--id-inicial 288
```

`--fenomeno` es opcional. Úsalo cuando todos los archivos de la entrada
pertenezcan al mismo fenómeno. Si todavía no conoces esa asignación, omítelo;
el manifiesto dejará `fenomeno` como `null` para completarlo después.

Para consultar la ayuda:

```powershell
python .\limpiar_documentos.py --help
```

## Segunda pasada asistida

DespuÃ©s de generar los `.txt` iniciales en `output/`, se puede ejecutar una
segunda pasada de limpieza con `limpiar_con_subagente.py`. Esta pasada conserva
tÃ­tulos, encabezados y secciones estructurales para que la fase de chunking
pueda usarlos como seÃ±ales de segmentaciÃ³n, pero sigue eliminando boilerplate,
bibliografÃ­a, referencias, notas, DOI y URLs cuando funcionen como metadatos o
ruido editorial.

Muestra local sin consumir API:

```powershell
python .\limpiar_con_subagente.py --sample-size 6 --seed 20260801 --sin-api
```

Corpus completo con DeepSeek:

```powershell
$env:DEEPSEEK_API_KEY="tu_api_key"
python .\limpiar_con_subagente.py --formatos pdf
```

El filtro `--formatos` usa el formato original registrado en el manifiesto.
Por ejemplo, `--formatos pdf` limita la segunda pasada a los PDF aunque en
`output/` ya existan TXT provenientes de JSON. Se pueden indicar varios
formatos separados por coma, como `--formatos pdf,json`.

Por defecto la salida se guarda en `.\output_post_limpieza` y solo se crea el
manifiesto consolidado. Para generar tambien un JSON detallado por documento,
usa `--con-reportes-limpieza`.

Si la ejecucion se interrumpe, puedes volver a lanzar el mismo comando. Los
`.txt` que ya existan en la salida se omiten y se continua con los faltantes.
Para reprocesar todo desde cero, usa `--sobrescribir-salida`.

Para procesar en paralelo, abre tres consolas en `Fase_1_Limpieza` y ejecuta:

```powershell
python .\limpiar_con_subagente.py --formatos pdf --shard-count 3 --shard-index 0
python .\limpiar_con_subagente.py --formatos pdf --shard-count 3 --shard-index 1
python .\limpiar_con_subagente.py --formatos pdf --shard-count 3 --shard-index 2
```

Cada particion escribe un manifiesto propio para evitar choques entre procesos.
Cuando las tres terminen, une los manifiestos y agrega al consolidado los
documentos procesados por la limpieza inicial que no pasaron por el subagente
(por ejemplo, los JSON):

```powershell
python .\limpiar_con_subagente.py --unir-manifiestos-shards
```

El comando lee los manifiestos de `output/`, copia los TXT iniciales faltantes
a `output_post_limpieza/` y los marca como `procesado_inicial`. Los documentos
con estado `fallido` no se incorporan.

Si la segunda pasada se limito a PDF, puedes conservar ese filtro al unirlos:

```powershell
python .\limpiar_con_subagente.py --formatos pdf --unir-manifiestos-shards
```

## Estructura de salida

```text
procesados/
├── manifiesto_global.json   # todos los fenómenos
├── F1_.../
│   ├── DOC-000001.txt       # textos limpios del fenómeno
│   ├── manifiesto.json       # manifiesto granular de F1
│   └── reporte_calidad.json
└── F2_.../
    └── ...
```

Los originales permanecen en el directorio de entrada y nunca se sobrescriben.
La carpeta de salida replica las subcarpetas de la entrada y guarda cada
documento procesado como `DOC-xxxxxx.txt` en su carpeta relativa.

## Cómo se conserva la trazabilidad

El campo `fuente` es el nombre original sin extensión. La ruta relativa del
original queda en `ruta_original` y la salida limpia en `ruta_limpio`. El
`doc_id` conserva la
posición del documento dentro del inventario global, incluso al filtrar
formatos.

Ejemplo de registro del manifiesto:

```json
{
  "doc_id": "DOC-000001",
  "fuente": "informe",
  "ruta_original": "fenomeno_1/informe.pdf",
  "formato": "pdf",
  "fenomeno": 1,
  "estado": "procesado",
  "idioma": "es",
  "metodo_extraccion": "pypdf",
  "advertencias": [],
  "ruta_limpio": "fenomeno_1/DOC-000001.txt",
  "archivo_limpio": "fenomeno_1/DOC-000001.txt",
  "version_pipeline": "1.0.0"
}
```

El `doc_id` depende del orden global de la entrada y no cambia al filtrar
formatos durante esa ejecución.

## Flujo interno

```text
archivo original
      │
      ├── posición global + fuente + doc_id
      │
      ▼
extract(path)
      │  selecciona extract_pdf, extract_html, extract_json, etc.
      ▼
texto extraído
      │
      ▼
clean_text(text)
      │  Unicode, saltos, controles, espacios y ruido repetido
      ▼
texto limpio ──────────────► misma/ruta/relativa/documento.txt
      │
      ▼
detect_language + métricas + advertencias
      │
      ▼
manifiesto.json de fenómeno + manifiesto_global.json
```

## Reglas de limpieza

La limpieza es deliberadamente conservadora:

- normaliza Unicode a NFC;
- convierte saltos de línea a `\n`;
- reemplaza espacios no separables;
- elimina caracteres de control no semánticos;
- reduce espacios horizontales repetidos;
- conserva títulos, párrafos y listas como texto;
- elimina números de página aislados;
- elimina líneas repetidas solo cuando aparecen en varias páginas;
- no resume, traduce ni corrige el contenido del autor.

En PDF, las páginas se separan temporalmente con un carácter de página. Esto
permite detectar cabeceras y pies repetidos. La heurística considera repetida
una línea no vacía que aparece al menos en la mitad de las páginas y mide como
máximo 180 caracteres. Los documentos con diseños poco usuales deben pasar por
revisión manual.

## Tratamiento por formato

### PDF

Se extrae página por página. Las páginas sin texto generan una advertencia,
porque probablemente necesiten OCR. El script no aplica OCR automáticamente al
PDF completo para evitar introducir texto inventado o errores no visibles.

### HTML

Se conserva el texto visible y se eliminan scripts, estilos, navegación, pies,
formularios, barras laterales y SVG. El título HTML se conserva como metadata.

### JSON

No se vuelca el objeto completo. Se buscan claves textuales como `title`,
`body_text`, `body_paragraphs`, `content`, `text`, `abstract` y `summary`.
También se conservan estructuras narrativas anidadas, como `sections.heading`,
`sections.paragraphs` y `lists`, respetando su orden. Se omiten metadata y
ramas auxiliares de páginas web como `links` y `pdf_links`, además de URLs
técnicas en `src` y `href`, para evitar contaminar el texto con navegación y
recursos gráficos. Si una imagen contiene texto alternativo (`alt`), este se
conserva porque puede aportar una descripción semántica. El manifiesto registra
los campos de metadata detectados.
Campos como URL, fecha, autores, etiquetas e IDs se tratan como metadata cuando
están en el nivel principal.

### CSV/XLSX

Cada fila se convierte en una unidad estructural. El nombre de la columna se
mantiene junto al valor para que una futura búsqueda semántica no pierda el
contexto. En XLSX también se conserva el nombre de la hoja.

### Imágenes

El OCR es opcional. Las cifras, porcentajes, nombres propios y etiquetas de
gráficos deben revisarse manualmente, tal como exige la guía del proyecto.

### PBF

Se registra como pendiente porque requiere una librería geoespacial capaz de
recorrer capas y atributos. No se debe tratar como texto plano.

## Estados y advertencias

Cada documento termina con uno de estos estados:

- `procesado`: texto limpio y sin advertencias;
- `procesado_con_advertencias`: hay texto, pero requiere revisión;
- `fallido`: no se obtuvo texto utilizable.

Las advertencias no se ocultan. Ejemplos: dependencia ausente, JSON inválido,
PDF sin texto, OCR vacío o formato pendiente.

Los reportes y catálogos técnicos del scraper que no aportan contenido de
conocimiento se conservan en los originales y el manifiesto, pero se marcan
como `excluido_no_contenido` con `apto_para_indice: false`. No generan TXT,
chunks ni embeddings.

## Revisión recomendada antes del chunking

1. Abrir una muestra de cada formato e idioma.
2. Comparar el original con el archivo `.txt` limpio en la ruta espejo.
3. Revisar todos los documentos con advertencias.
4. Revisar PDFs de una y varias columnas.
5. Confirmar que tablas, cifras, nombres y fechas no cambiaron.
6. Confirmar que no se perdió el orden del contenido.
7. Confirmar que todos los archivos aparecen en el manifiesto.
8. Resolver o aceptar explícitamente los casos anómalos.

Solo después de esa revisión debe comenzar el chunking con cortes en límites de
oraciones completas, según las especificaciones de la Etapa 1.
