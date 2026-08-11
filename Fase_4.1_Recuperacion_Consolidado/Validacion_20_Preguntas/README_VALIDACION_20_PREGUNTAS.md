# Validación de recuperación - 20 preguntas

## Preguntas

`preguntas_validacion_20.jsonl` es un conjunto interno de prueba. No sustituye
las 50 consultas oficiales. Antes de usar métricas, el equipo debe añadir a
cada registro la evidencia exacta que encontró: `doc_id`, `chunk_id` y, si es
posible, una copia breve del texto fuente en un archivo separado de anotaciones.

Validación:

```powershell
python .\Fase_4.1_Recuperacion_Consolidado\Validacion_20_Preguntas\validar_preguntas.py `
  .\Fase_4.1_Recuperacion_Consolidado\Validacion_20_Preguntas\preguntas_validacion_20.jsonl
```

Las respuestas incluidas son hipótesis de validación, no respuestas generadas
por el sistema. Deben confirmarse manualmente contra el corpus.

El grafo está organizado en `Fase_3.5_Grafo_Conocimiento`, siguiendo el orden
del flujo técnico del reto.
