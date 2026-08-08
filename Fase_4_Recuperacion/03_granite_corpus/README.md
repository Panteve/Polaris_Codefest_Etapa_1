# Recuperación — Granite corpus

Ejecuta la recuperación sobre `Fase_3_Encoder\03_granite_corpus`.

```powershell
python .\Fase_4_Recuperacion\03_granite_corpus\recuperar.py --query "..."
```

Por defecto recupera 20 chunks candidatos, puntúa cada documento con el
promedio de sus 3 mejores chunks y guarda solo 10 fragmentos en
`resultados.json`. Se puede usar `--doc-score sum` para sumar los candidatos.
