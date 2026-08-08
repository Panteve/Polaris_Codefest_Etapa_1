import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2] / "Fase_4_Recuperacion" / "01_bge_m3_corpus"
sys.path.insert(0, str(BASE))
from recuperar import main

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "Fase_3_Encoder" / "05_granite_overlap_1"

if __name__ == "__main__":
    main(
        default_index=DATA / "index.faiss",
        default_metadata=DATA / "metadata.jsonl",
        default_output=Path(__file__).resolve().parent / "resultados.json",
        default_model="ibm-granite/granite-embedding-311m-multilingual-r2",
    )
