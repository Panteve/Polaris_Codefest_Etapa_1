# Instalar antes: %pip install -q -U sentence-transformers faiss-cpu transformers accelerate

import argparse
import json
from pathlib import Path
import faiss
import numpy as np
import torch
from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-m3"
LABEL = "BGE-M3 semantic PDF"

parser = argparse.ArgumentParser()
parser.add_argument("--metadata", default=None)
parser.add_argument("--output-index", default="/kaggle/working/index.faiss")
parser.add_argument("--batch-size", type=int, default=64)
parser.add_argument("--gpus", type=int, default=0)
args, _ = parser.parse_known_args()
files = [Path(args.metadata)] if args.metadata else sorted(Path("/kaggle/input").rglob("metadata.jsonl"))
if len(files) != 1: raise RuntimeError(f"Se esperaba una metadata.jsonl; encontradas: {files}")
records = [json.loads(line) for line in files[0].open(encoding="utf-8") if line.strip()]
texts = [str(record["texto"]).strip() for record in records]
available = torch.cuda.device_count(); used = available if args.gpus <= 0 else min(args.gpus, available)
print(f"[{LABEL}] Registros: {len(texts):,} | GPU: {used}", flush=True)
model = SentenceTransformer(MODEL_NAME, device="cuda:0" if used else "cpu")
pool = model.start_multi_process_pool(target_devices=[f"cuda:{i}" for i in range(used)]) if used > 1 else None
vectors = []; step = args.batch_size * max(used, 1)
try:
    for start in range(0, len(texts), step):
        batch = texts[start:start + step]
        encoded = model.encode(batch, pool=pool, batch_size=args.batch_size, chunk_size=args.batch_size, show_progress_bar=False, convert_to_numpy=True) if pool else model.encode(batch, batch_size=args.batch_size, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True)
        encoded = np.asarray(encoded, dtype="float32"); encoded /= np.maximum(np.linalg.norm(encoded, axis=1, keepdims=True), 1e-12); vectors.append(encoded)
        print(f"[{LABEL}] {start + len(batch):,}/{len(texts):,}", flush=True)
finally:
    if pool: model.stop_multi_process_pool(pool)
matrix = np.concatenate(vectors); index = faiss.IndexFlatIP(matrix.shape[1]); index.add(matrix); faiss.write_index(index, args.output_index)
print(f"[{LABEL}] Listo: {index.ntotal:,} vectores -> {args.output_index}", flush=True)
