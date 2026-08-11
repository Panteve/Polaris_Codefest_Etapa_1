# Instalar antes: %pip install -q -U sentence-transformers faiss-cpu transformers accelerate

import argparse
import json
import time
from pathlib import Path
import faiss
import numpy as np
import torch
from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-m3"
LABEL = "BGE-M3 semantic PDF"
KAGGLE_INPUT = Path("/kaggle/input")
DEFAULT_OUTPUT_INDEX = Path("/kaggle/working/index_semantic_bge_m3.faiss")


def find_input_metadata() -> Path:
    candidates = sorted(
        path for path in KAGGLE_INPUT.rglob("metadata.jsonl")
        if path.is_file()
    )
    semantic = [
        path for path in candidates
        if any(term in str(path).casefold() for term in ("semantic", "bge_m3_semantic", "chunks_semantic"))
    ]
    if len(semantic) == 1:
        return semantic[0]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError("No se encontró metadata.jsonl dentro de /kaggle/input.")
    raise RuntimeError(
        "Se encontraron varias metadata.jsonl en /kaggle/input. "
        "Usa --metadata para indicar la del dataset semántico:\n"
        + "\n".join(str(path) for path in candidates)
    )

parser = argparse.ArgumentParser()
parser.add_argument("--metadata", default=None)
parser.add_argument("--output-index", default=str(DEFAULT_OUTPUT_INDEX))
parser.add_argument("--batch-size", type=int, default=8)
parser.add_argument("--gpus", type=int, default=0)
args, _ = parser.parse_known_args()
metadata_path = Path(args.metadata) if args.metadata else find_input_metadata()
if not metadata_path.is_file():
    raise FileNotFoundError(
        f"No se encontró la metadata generada por la celda anterior: {metadata_path}. "
        "Ejecuta primero el generador de chunks o usa --metadata con otra ruta."
    )
print(f"[{LABEL}] Metadata: {metadata_path}", flush=True)
if metadata_path.suffix.casefold() == ".json":
    records = json.loads(metadata_path.read_text(encoding="utf-8"))
else:
    records = [json.loads(line) for line in metadata_path.open(encoding="utf-8") if line.strip()]
if not isinstance(records, list):
    raise RuntimeError(f"La metadata debe ser una lista o JSON Lines: {metadata_path}")
if not records:
    raise RuntimeError(f"La metadata está vacía: {metadata_path}")
texts = [str(record["texto"]).strip() for record in records]
available = torch.cuda.device_count(); used = available if args.gpus <= 0 else min(args.gpus, available)
print(f"[{LABEL}] Registros: {len(texts):,} | GPU: {used}", flush=True)
model = SentenceTransformer(MODEL_NAME, device="cuda:0" if used else "cpu")
pool = model.start_multi_process_pool(target_devices=[f"cuda:{i}" for i in range(used)]) if used > 1 else None
vectors = []; step = args.batch_size * max(used, 1)
started = time.perf_counter()
next_milestone = 5
try:
    for start in range(0, len(texts), step):
        batch = texts[start:start + step]
        encoded = model.encode(batch, pool=pool, batch_size=args.batch_size, chunk_size=args.batch_size, show_progress_bar=False, convert_to_numpy=True) if pool else model.encode(batch, batch_size=args.batch_size, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True)
        encoded = np.asarray(encoded, dtype="float32"); encoded /= np.maximum(np.linalg.norm(encoded, axis=1, keepdims=True), 1e-12); vectors.append(encoded)
        done = start + len(batch); percent = done * 100 / len(texts)
        while next_milestone <= 100 and percent >= next_milestone:
            elapsed = max(time.perf_counter() - started, 1e-9); print(f"[{LABEL}] {done:,}/{len(texts):,} ({next_milestone}%) | {done / elapsed:.1f} registros/s | {elapsed:.1f}s", flush=True); next_milestone += 5
finally:
    if pool: model.stop_multi_process_pool(pool)
matrix = np.concatenate(vectors); index = faiss.IndexFlatIP(matrix.shape[1]); index.add(matrix); faiss.write_index(index, args.output_index)
print(f"[{LABEL}] Listo: {index.ntotal:,} vectores -> {args.output_index}", flush=True)
