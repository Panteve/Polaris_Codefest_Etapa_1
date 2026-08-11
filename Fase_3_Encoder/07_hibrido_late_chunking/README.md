# Experimento híbrido late chunking

Esta carpeta prepara dos entradas separadas para el encoder y la recuperación:

```text
07_hibrido_late_chunking/
├── pdf_late/
│   ├── metadata.jsonl
│   ├── documentos/                 # copias .md/.txt, no PDF
│   ├── manifiesto_late_local.json
│   ├── generar_indice_local.py
│   └── generar_indice_kaggle.py
└── no_pdf/
    ├── metadata.jsonl
    ├── generar_indice_local.py
    └── generar_indice_kaggle.py
```

## Preparación

Desde la raíz del proyecto, ejecutar el preparador cuando se quiera regenerar
la metadata:

```powershell
python .\Fase_3_Encoder\07_hibrido_late_chunking\preparar_metadata.py
```

La rama `pdf_late` toma la metadata late de los PDF y copia las fuentes limpias
correspondientes como `.md` o `.txt`. La rama `no_pdf` combina las metadatas de
JSON y otros formatos, excluyendo cualquier registro PDF.

La metadata y los vectores deben conservar exactamente el mismo orden. Para
late chunking, los offsets se aplican sobre los archivos copiados y el
`manifiesto_late_local.json` apunta a esas copias.

Los documentos que superan la ventana máxima de Granite no se truncan ni se
descartan: los scripts late los procesan por ventanas solapadas, procurando
cerrar cada ventana en un límite de oración y combinando las representaciones
correspondientes a cada chunk. Solo una oración individual demasiado larga se
divide por tokens.

Después de preparar las entradas, cada rama tiene su propio script local y de
Kaggle. Los scripts de Kaggle son autónomos: no importan `index_utils.py` ni
dependen de la estructura interna del repositorio. Los índices generados quedan
en la carpeta de su respectiva rama.
