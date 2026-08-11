# Recuperación — BGE-M3 semantic PDF

Ejecuta la recuperación sobre `Fase_3_Encoder\06_bge_m3_semantic_pdf`.

```powershell
python .\Fase_4_Recuperacion\06_bge_m3_semantic_pdf\recuperar.py --query "..."
```

Por defecto recupera 20 chunks candidatos, puntúa cada documento con el
promedio de sus 3 mejores chunks y guarda solo 10 fragmentos en
`resultados.json`. Se puede usar `--doc-score sum` para sumar los candidatos.
