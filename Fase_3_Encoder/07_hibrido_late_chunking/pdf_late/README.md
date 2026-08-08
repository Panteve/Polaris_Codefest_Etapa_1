# PDF late

Contiene únicamente la metadata late de los PDF y copias de los documentos
fuente limpios en formato `.md` o `.txt`. No se copian los PDF originales.

Preparar primero desde la raíz:

```powershell
python .\Fase_3_Encoder\07_hibrido_late_chunking\preparar_metadata.py
```

Ejecutar localmente:

```powershell
python .\Fase_3_Encoder\07_hibrido_late_chunking\pdf_late\generar_indice_local.py
```

El script usa `manifiesto_late_local.json`, genera vectores con
`ibm-granite/granite-embedding-311m-multilingual-r2` y escribe `index.faiss`.
Si un documento supera la ventana máxima del modelo, lo procesa mediante
ventanas solapadas que intentan terminar en límites de oración. Conserva los
offsets de los chunks y combina las representaciones de las ventanas antes de
normalizar cada vector. Una oración individual que exceda el límite se divide
por tokens como último recurso.

En Kaggle, copia esta carpeta al entorno de trabajo y ejecuta el script
autónomo:

```python
!python generar_indice_kaggle.py --metadata metadata.jsonl \
    --manifest manifiesto_late_local.json --output-index index.faiss
```

Este script no importa `index_utils.py`.
