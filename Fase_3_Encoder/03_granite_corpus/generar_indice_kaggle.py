# Instalar antes: %pip install -q -U sentence-transformers faiss-cpu transformers accelerate

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

import faiss
import numpy as np
import torch
from sentence_transformers import SentenceTransformer

MODEL_NAME = "ibm-granite/granite-embedding-311m-multilingual-r2"
LABEL = "Granite corpus"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", default=None)
    parser.add_argument("--output-index", default="/kaggle/working/index.faiss")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--gpus", type=int, default=0)
    parser.add_argument("--checkpoint-dir", default="/kaggle/working/.checkpoint")
    parser.add_argument("--checkpoint-every", type=int, default=10)
    parser.add_argument("--fresh", action="store_true")
    args, _ = parser.parse_known_args()
    files = [Path(args.metadata)] if args.metadata else sorted(Path("/kaggle/input").rglob("metadata.jsonl"))
    if len(files) != 1:
        raise RuntimeError(f"Se esperaba una metadata.jsonl; encontradas: {files}")
    records = [json.loads(line) for line in files[0].open(encoding="utf-8") if line.strip()]
    texts = [str(r["texto"]).strip() for r in records]
    digest = hashlib.sha256("".join(json.dumps(r, sort_keys=True) for r in records).encode()).hexdigest()
    gpu_count = torch.cuda.device_count()
    used = gpu_count if args.gpus <= 0 else min(args.gpus, gpu_count)
    print(f"[{LABEL}] Registros: {len(records):,} | GPU: {used}", flush=True)
    model = SentenceTransformer(MODEL_NAME, device="cuda:0" if used else "cpu")
    checkpoint = Path(args.checkpoint_dir); state_file = checkpoint / "state.json"; vectors_file = checkpoint / "vectors.npy"
    vectors, start = [], 0
    if not args.fresh and state_file.exists() and vectors_file.exists() and json.loads(state_file.read_text()).get("digest") == digest:
        start = int(json.loads(state_file.read_text())["next"]); vectors = [np.load(vectors_file)]; print(f"Reanudando desde {start:,}.", flush=True)
    pool = model.start_multi_process_pool(target_devices=[f"cuda:{i}" for i in range(used)]) if used > 1 else None
    step = args.batch_size * max(used, 1); started = time.perf_counter()
    try:
        for position in range(start, len(texts), step):
            batch = texts[position:position + step]
            encoded = model.encode(batch, pool=pool, batch_size=args.batch_size, chunk_size=args.batch_size, show_progress_bar=False, convert_to_numpy=True) if pool else model.encode(batch, batch_size=args.batch_size, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True)
            encoded = np.asarray(encoded, dtype="float32"); encoded /= np.maximum(np.linalg.norm(encoded, axis=1, keepdims=True), 1e-12); vectors.append(encoded)
            done = position + len(batch); print(f"[{LABEL}] {done:,}/{len(texts):,} ({done * 100 / len(texts):.2f}%)", flush=True)
            if args.checkpoint_every and ((position // step) + 1) % args.checkpoint_every == 0:
                checkpoint.mkdir(parents=True, exist_ok=True); np.save(vectors_file, np.concatenate(vectors)); state_file.write_text(json.dumps({"next": done, "digest": digest}))
    finally:
        if pool: model.stop_multi_process_pool(pool)
    matrix = np.concatenate(vectors); index = faiss.IndexFlatIP(matrix.shape[1]); index.add(matrix); faiss.write_index(index, args.output_index)
    if checkpoint.exists(): shutil.rmtree(checkpoint)
    print(f"[{LABEL}] Listo: {index.ntotal:,} vectores -> {args.output_index}", flush=True)


if __name__ == "__main__": main()
