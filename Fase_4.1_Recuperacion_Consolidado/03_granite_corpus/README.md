# Recuperación con Granite y FAISS

Este módulo consulta el índice disponible en la carpeta actual usando el mismo encoder
`ibm-granite/granite-embedding-311m-multilingual-r2`. La metadata se lee en el orden original y se valida contra el
número de vectores del índice para evitar recuperar un texto equivocado.

## Estrategia de recuperación

Para cada pregunta, el script realiza este flujo:

1. Codifica la pregunta con el encoder configurado.
2. Normaliza el embedding de la pregunta, igual que durante la indexación.
3. Ejecuta una búsqueda directa de los vecinos más cercanos en FAISS.
4. Conserva el orden y el score entregados por FAISS.
5. Devuelve hasta 3 documentos distintos y hasta `top-k` fragmentos.

No se aplica reranking, agrupación de chunks, promedio de scores, suma de
scores, expansión de contexto ni generación de texto. Los filtros opcionales
solo descartan resultados después de la búsqueda y no cambian el ranking.

Por defecto se utilizan:

```text
model = ibm-granite/granite-embedding-311m-multilingual-r2
top_k = 20
threshold = -1.0
fragments_in_output = hasta 10
```

## Uso

Desde la raíz del proyecto:

```powershell
python .\Fase_4.1_Recuperacion_Consolidado\03_granite_corpus\recuperar_V1.py
```

El programa abre una consola interactiva. Para una sola pregunta:

```powershell
python .\Fase_4.1_Recuperacion_Consolidado\03_granite_corpus\recuperar_V1.py `
    --query "¿Qué capacidades de inteligencia artificial se destacan?"
```

Para guardar las respuestas como JSON Lines y JSON normal:

```powershell
python .\Fase_4.1_Recuperacion_Consolidado\03_granite_corpus\recuperar_V1.py `
    --output .\Fase_4.1_Recuperacion_Consolidado\03_granite_corpus\resultado.jsonl `
    --output-json .\Fase_4.1_Recuperacion_Consolidado\03_granite_corpus\resultado.json
```

## Parámetros

| Parámetro | Por defecto | Descripción |
|---|---|---|
| `--query` | interactivo | Ejecuta una sola pregunta y termina. |
| `--top-k` | `20` | Cantidad máxima de vecinos directos solicitados a FAISS. |
| `--model` | `ibm-granite/granite-embedding-311m-multilingual-r2` | Encoder para codificar la consulta. Debe coincidir con el índice. |
| `--device` | automático | Dispositivo de ejecución, por ejemplo `cpu` o `cuda`. |
| `--index` | `Fase_4.1_Recuperacion_Consolidado\03_granite_corpus\index.faiss` | Ruta del índice FAISS. |
| `--metadata` | `Fase_4.1_Recuperacion_Consolidado\03_granite_corpus\metadata.jsonl` | Ruta de la metadata JSONL. |
| `--output-json` | `resultado.json` | Ruta del arreglo JSON de salida. |
| `--output` | sin archivo | Ruta opcional para salida JSON Lines. |
| `--threshold` | `-1.0` | Score mínimo para conservar un vecino. |
| `--fenomeno` | sin filtro | Filtra por fenómeno `1`, `2` o `3`. |
| `--idioma` | sin filtro | Filtra por idioma, por ejemplo `es`, `en` o `pt`. |
| `--formato` | sin filtro | Filtra por formato, por ejemplo `pdf`, `json` o `txt`. |

Ejemplo con parámetros configurables:

```powershell
python .\Fase_4.1_Recuperacion_Consolidado\03_granite_corpus\recuperar_V1.py `
    --top-k 20 `
    --threshold 0.35 `
    --device cpu `
    --idioma es `
    --formato pdf
```

Los artefactos usados por defecto son los de
`Fase_4.1_Recuperacion_Consolidado\03_granite_corpus`: `index.faiss` y `metadata.jsonl`.
