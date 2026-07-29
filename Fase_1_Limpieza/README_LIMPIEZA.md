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
3. Calcula un checksum SHA-256.
4. Asigna o reutiliza un `doc_id` estable.
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
  --fenomeno 1 `
  --verbose
```

`--fenomeno` es opcional. Úsalo cuando todos los archivos de la entrada
pertenezcan al mismo fenómeno. Si todavía no conoces esa asignación, omítelo;
el manifiesto dejará `fenomeno` como `null` para completarlo después.

Para consultar la ayuda:

```powershell
python .\limpiar_documentos.py --help
```

## Estructura de salida

```text
procesados/
├── extraidos/
│   └── DOC-000001.txt       # extracción bruta
├── limpios/
│   └── DOC-000001.txt       # texto listo para chunking
├── manifiesto.jsonl         # un objeto JSON por documento
└── reporte_calidad.json     # resumen de estados del lote
```

Los originales permanecen en el directorio de entrada y nunca se sobrescriben.

## Cómo se conserva la trazabilidad

El campo `fuente` es la ruta relativa del archivo respecto al directorio de
entrada. Esa fuente es la clave que permite reutilizar el mismo `doc_id` en
ejecuciones posteriores. El checksum permite saber si el archivo original
cambió.

Ejemplo de registro del manifiesto:

```json
{
  "doc_id": "DOC-000001",
  "fuente": "fenomeno_1/informe.pdf",
  "formato": "pdf",
  "fenomeno": 1,
  "checksum": "...",
  "estado": "procesado",
  "idioma": "es",
  "metodo_extraccion": "pypdf",
  "advertencias": [],
  "archivo_extraido": "extraidos/DOC-000001.txt",
  "archivo_limpio": "limpios/DOC-000001.txt",
  "version_pipeline": "1.0.0"
}
```

El `doc_id` no depende de la posición del archivo en un listado. No debe
renombrarse después de iniciar la indexación.

## Flujo interno

```text
archivo original
      │
      ├── checksum + fuente + doc_id
      │
      ▼
extract(path)
      │  selecciona extract_pdf, extract_html, extract_json, etc.
      ▼
texto bruto ───────────────► extraidos/DOC-xxxxxx.txt
      │
      ▼
clean_text(text)
      │  Unicode, saltos, controles, espacios y ruido repetido
      ▼
texto limpio ──────────────► limpios/DOC-xxxxxx.txt
      │
      ▼
detect_language + métricas + advertencias
      │
      ▼
manifiesto.jsonl + reporte_calidad.json
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

## Revisión recomendada antes del chunking

1. Abrir una muestra de cada formato e idioma.
2. Comparar el original, `extraidos/` y `limpios/`.
3. Revisar todos los documentos con advertencias.
4. Revisar PDFs de una y varias columnas.
5. Confirmar que tablas, cifras, nombres y fechas no cambiaron.
6. Confirmar que no se perdió el orden del contenido.
7. Confirmar que todos los archivos aparecen en el manifiesto.
8. Resolver o aceptar explícitamente los casos anómalos.

Solo después de esa revisión debe comenzar el chunking con cortes en límites de
oraciones completas, según las especificaciones de la Etapa 1.
