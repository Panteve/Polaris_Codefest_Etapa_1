# Fase 4.1 — Recuperación consolidada

## Requisito de versiones de recuperación

Cada configuración de recuperación puede contener varias versiones de su script:

```text
recuperar_V1.py
recuperar_V2.py
recuperar_V3.py
```

La aplicación Node.js debe detectar automáticamente las versiones disponibles en cada carpeta y permitir seleccionar cuál ejecutar.

Reglas:

- El patrón válido es `recuperar_VN.py`, donde `N` es el número de versión.
- Si no se selecciona una versión, se utiliza la versión numérica más reciente.
- En una comparación, cada configuración puede utilizar una versión diferente.
- La versión ejecutada debe mostrarse en el resultado.

## Estructura esperada

```text
Fase_4.1_Recuperacion_Consolidado/
├── README.md
├── server.js
├── package.json
├── public/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── 01_bge_m3_corpus/
│   ├── recuperar_V1.py
│   ├── recuperar_V2.py
│   ├── index.faiss
│   ├── metadata.jsonl
│   ├── resultados.json
│   └── README.md
├── 03_granite_corpus/
│   ├── recuperar_V1.py
│   ├── index.faiss
│   ├── metadata.jsonl
│   └── README.md
├── 04_bge_m3_overlap_1/
│   ├── recuperar_V1.py
│   ├── index.faiss
│   ├── metadata.jsonl
│   └── README.md
└── 05_granite_overlap_1/
    ├── recuperar_V1.py
    ├── index.faiss
    ├── metadata.jsonl
    └── README.md
```
