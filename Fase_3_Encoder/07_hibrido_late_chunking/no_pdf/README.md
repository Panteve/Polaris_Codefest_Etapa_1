# No-PDF

Contiene la metadata de los registros JSON y de otros formatos no-PDF. No
incluye archivos fuente copiados.

Ejecutar localmente:

```powershell
python .\Fase_3_Encoder\07_hibrido_late_chunking\no_pdf\generar_indice_local.py
```

El script usa `BAAI/bge-m3`, excluye cualquier registro PDF y genera
`index.faiss` manteniendo el orden de `metadata.jsonl`.

En Kaggle:

```python
!python generar_indice_kaggle.py --metadata metadata.jsonl \
    --output-index index.faiss
```

El script de Kaggle es autónomo y no importa `index_utils.py`.
