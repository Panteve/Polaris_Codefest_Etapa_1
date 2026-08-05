# Fase 1 — Limpieza y preparación unificada del corpus

Este documento es la guía operativa de la Fase 1. La información se
fundamenta en la documentación técnica disponible del proyecto y en el estado
actual de las salidas generadas.

## Producto final de esta fase

La salida oficial que debe consumir Fase 2 es:

```text
Fase_1_Limpieza/output final limpio/
```

Su manifiesto principal es:

```text
Fase_1_Limpieza/output final limpio/manifiesto_final_limpio.json
```

Actualmente contiene 1.726 documentos y todos los archivos de contenido están
nombrados con su identificador estable:

```text
DOC-000001.md
DOC-000002.md
DOC-000003.txt
```

La extensión indica el contenido disponible, no el formato original. El campo
`formato` del manifiesto conserva el formato original del documento.

## Tratamiento por formato

| Formato original | Tratamiento aplicado | Salida final |
|---|---|---|
| PDF con Markdown producido | `pdf-inspector` y limpieza Markdown determinista | `.md` |
| PDF sin Markdown | TXT limpio de respaldo de la limpieza anterior | `.txt` |
| JSON | Limpieza estructurada de Fase 1 | `.txt` |
| CSV/XLSX | Representación tabular de Fase 1 | `.txt` |
| Imagen | Texto disponible de Fase 1, si existe OCR | `.txt` |
| PBF | Texto disponible de Fase 1, si existe extracción | `.txt` |
| TXT original | Limpieza de Fase 1 | `.txt` |

La decisión para cada documento queda registrada en:

- `tipo_contenido_final`: `markdown` o `txt`;
- `metodo_extraccion_final`;
- `ruta_final`;
- `archivo_final`.

## Flujo completo

```text
input/                         originales entregados por ADL
   │
   ├── PDF ──► pdf-inspector ──► Markdown estructurado
   │                              │
   │                              └─ si no hay Markdown:
   │                                 TXT limpio anterior
   │
   └── JSON/CSV/XLSX/imagen/PBF/TXT
             └─ limpieza y extracción inicial

                 ▼
       consolidación de todos los formatos
                 ▼
       limpieza determinista de Markdown
                 ▼
       output final limpio/
                 ▼
       Fase 2 — chunking
```

## Carpetas y propósito

```text
Fase_1_Limpieza/
├── input/                         originales, nunca modificar
├── output final limpio/           PRODUCTO OFICIAL PARA FASE 2
│   ├── F1_.../                    contenido organizado por fenómeno/fuente
│   ├── F2_.../
│   ├── F3_.../
│   ├── manifiesto_final_limpio.json
│   └── reporte_limpieza_markdown.json
├── cambio de extractor pdf/       scripts del flujo PDF alternativo
│   └── output/                    Markdown intermedio de pdf-inspector
├── outputs_historicos/             copias y salidas anteriores, no usar para Fase 2
├── limpiar_documentos.py          limpieza inicial por formato
├── limpiar_con_subagente.py       pasada asistida opcional para la limpieza inicial
├── GUIA_PRIMER_PASO_LIMPIEZA_DOCUMENTOS.md
└── README_LIMPIEZA.md              documentación histórica/general
```

Los archivos `.rar` son respaldos comprimidos. No son la entrada directa de
Fase 2; debe usarse `output final limpio/`.

## Scripts del flujo final

Dentro de `cambio de extractor pdf/`:

1. `extraer_pdfs_pdf_inspector.py` procesa solo PDFs del manifiesto.
2. `consolidar_output_final.py` combina Markdown nuevo y TXT de respaldo.
3. `limpiar_markdown_pdf.py` elimina artefactos deterministas sin resumir ni
   reescribir el contenido.
4. `renombrar_output_final_por_id.py` garantiza nombres `DOC-xxxxxx.ext`.
5. `limpiar_manifest_final.py` elimina metadata heredada innecesaria.

## Regla para Fase 2

Fase 2 debe leer exclusivamente:

```text
output final limpio/
output final limpio/manifiesto_final_limpio.json
```

No debe mezclar archivos desde `input/`, `output/`, `outputs_historicos/` ni
desde el Markdown intermedio de `cambio de extractor pdf/output/`.

Los PDF que quedaron como `.txt` no deben descartarse: son documentos PDF para
los cuales el extractor nuevo no produjo Markdown, y su TXT anterior es el
respaldo autorizado dentro del producto final.

## Recuperacion de documentos vacios

Si el reporte de Fase 2 lista documentos en `documentos_vacios`, se pueden
reprocesar solo esos PDF con PDF Inspector y, cuando no haya Markdown, con
OCRmyPDF:

```powershell
python ".\Fase_1_Limpieza\cambio de extractor pdf\recuperar_documentos_vacios.py" `
  --reporte ".\Fase_2_Chunking\chunking-pdfs\pdfs_standard_objetivo-200palabras_max-250_solapamiento-0_bge_m3\reporte_chunking_pdf.json"
```

El script actualiza el Markdown en `output_final_limpio`, el manifiesto final
y vuelve a generar `metadata.json`, `metadata.jsonl` y el reporte de chunks en
la carpeta del reporte de entrada. Los PDF originales no se modifican. El
detalle de cada recuperación queda en
`output_final_limpio/reporte_recuperacion_documentos_vacios.json`.
