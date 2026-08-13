# Recuperación V2 con BGE-M3 y FAISS

Esta versión amplía el recall antes de aplicar los filtros de metadata o de
similitud. Para cada consulta, FAISS trae un pool inicial de hasta **50
candidatos**. Luego aplica el cross-encoder `BAAI/bge-reranker-v2-m3` para
reordenar ese pool y MMR para reducir fragmentos redundantes. La respuesta
final expone como máximo **10 fragmentos**.

El tamaño del pool y el límite de salida son parámetros independientes:

```text
recall_top_k = 50
output_top_k = 10
```

El flujo es:

1. Codificar y normalizar la consulta con `BAAI/bge-m3`.
2. Recuperar hasta 50 vecinos desde FAISS.
3. Aplicar los filtros opcionales al pool recuperado.
4. Reordenar los candidatos filtrados con `BAAI/bge-reranker-v2-m3`.
5. Aplicar MMR para penalizar redundancia y seleccionar los mejores 10.
6. Aplicar mean pooling sobre los 10 fragmentos finales: calcular el score
   promedio del reranker por documento y devolver los 3 documentos con mayor
   promedio.

## Uso

```powershell
python .\Fase_4.1_Recuperacion_Consolidado\01_bge_m3_corpus\recuperar_V2.py `
    --query "¿Qué capacidades de inteligencia artificial se destacan?"
```

Para guardar JSON Lines:

```powershell
python .\Fase_4.1_Recuperacion_Consolidado\01_bge_m3_corpus\recuperar_V2.py `
    --output .\Fase_4.1_Recuperacion_Consolidado\01_bge_m3_corpus\resultado_v2.jsonl
```


```powershell
python .\Fase_4.1_Recuperacion_Consolidado\01_bge_m3_corpus\recuperar_V2.py `
  --query "¿Qué relación existe entre la adopción de inteligencia artificial y el desarrollo de talento humano en América Latina?" `
  --recall-top-k 100 `
  --output-top-k 10 `
  --device cpu
```


## Parámetros principales

| Parámetro | Por defecto | Descripción |
|---|---:|---|
| `--recall-top-k` | `50` | Candidatos que se solicitan a FAISS antes de filtrar. |
| `--output-top-k` | `10` | Fragmentos máximos que se exponen en la respuesta. |
| `--reranker-model` | `BAAI/bge-reranker-v2-m3` | Cross-encoder aplicado al pool filtrado. |
| `--mmr-lambda` | `0.7` | Balance entre relevancia y diversidad en MMR. |
| `--threshold` | `-1.0` | Score mínimo para conservar un candidato. |
| `--fenomeno` | sin filtro | Filtra por fenómeno `1`, `2` o `3`. |
| `--idioma` | sin filtro | Filtra por idioma, por ejemplo `es`, `en` o `pt`. |
| `--formato` | sin filtro | Filtra por formato, por ejemplo `pdf`, `json` o `txt`. |

Los artefactos usados por defecto son `index.faiss` y `metadata.jsonl` de esta
misma carpeta.
