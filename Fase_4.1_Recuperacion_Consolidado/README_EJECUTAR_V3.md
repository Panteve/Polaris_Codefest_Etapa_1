# Ejecutar todas las recuperaciones V3

El script `ejecutar_todas_v3.py` ejecuta en secuencia los cinco recuperadores
V3. Usa por defecto el archivo de 15 preguntas, recall de 100, salida de 10
fragmentos y CPU.

Desde la raíz del proyecto:

```powershell
python .\Fase_4.1_Recuperacion_Consolidado\ejecutar_todas_v3.py
```

Cada configuración genera su propio archivo:

```text
01_bge_m3_corpus\resultado_v3_preguntas.json
03_granite_corpus\resultado_v3_preguntas.json
04_bge_m3_overlap_1\resultado_v3_preguntas.json
05_granite_overlap_1\resultado_v3_preguntas.json
06_bge_m3_semantic_pdf\resultado_v3_preguntas.json
```

La ejecución queda registrada en:

```text
Fase_4.1_Recuperacion_Consolidado\ejecucion_v3.log
```

El proceso continúa con los demás scripts si uno falla. Para usar otra
cantidad de candidatos:

```powershell
python .\Fase_4.1_Recuperacion_Consolidado\ejecutar_todas_v3.py `
  --recall-top-k 100 `
  --output-top-k 10 `
  --device cpu
```

Para ejecutar una sola pregunta en los cinco scripts:

```powershell
python .\Fase_4.1_Recuperacion_Consolidado\ejecutar_todas_v3.py `
  --query "¿Qué relación existe entre la adopción de inteligencia artificial y el desarrollo de talento humano en América Latina?" `
  --recall-top-k 100 `
  --output-top-k 10 `
  --device cpu
```

Cuando se usa `--query`, el orquestador no procesa el archivo completo de
preguntas. El resultado de cada corpus se guarda en su respectiva carpeta.

Si existe el entorno `.venv` en la raíz del proyecto, el orquestador lo usa
automáticamente para encontrar `faiss` y las demás dependencias.
