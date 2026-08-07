# Configuración híbrida: BGE-M3 sin PDF

## Propósito

Construir el índice BGE-M3 para la parte no-PDF del corpus. Este índice se
combina posteriormente con el índice Granite late de la carpeta hermana
`02_hibrido_granite_late_pdf`.

## Entrada

Colocar la metadata combinada de referencia como:

```text
metadata.jsonl
```

El script filtra automáticamente todos los registros cuyo campo `formato` sea
`pdf`. Los formatos restantes se procesan sin cambiar sus chunks. Como el
script ya no escribe metadata, el archivo que acompañe al índice debe quedar
preparado con esos mismos registros no-PDF y en el mismo orden.

## Ejecución

```powershell
python .\Fase_3_Encoder\02_hibrido_bge_m3_no_pdf\generar_indice.py
```

Acepta `--metadata`, `--output-index`, `--batch-size`, `--device`,
`--checkpoint-every` y `--fresh`.

## Salida

```text
index.faiss
```

El índice contiene únicamente los registros no-PDF. La metadata asociada debe
contener exactamente esos registros y conservar el mismo orden de los vectores;
una metadata completa del corpus no puede acompañar directamente este índice.

## Progreso y reanudación

Informa el avance por lotes y guarda checkpoints temporales cada 10 lotes. No
escribe metadata ni rechaza chunks por cantidad de palabras.
