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


MODEL_NAME = "BAAI/bge-m3"
LABEL = "BGE-M3 híbrido sin PDF"


def metadata_path(explicit):
    if explicit:
        return Path(explicit)
    files = sorted(Path("/kaggle/input").rglob("metadata.jsonl"))
    if len(files) != 1:
        raise RuntimeError(f"Se esperaba una metadata.jsonl en /kaggle/input; encontradas: {files}")
    return files[0]


def read_records(path):
    records = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            record = json.loads(line)
            if str(record.get("formato", "")).lower() != "pdf" and str(record.get("texto", "")).strip():
                records.append(record)
    if not records:
        raise ValueError("No hay registros no-PDF para indexar.")
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", default=None)
    parser.add_argument("--output-index", default="/kaggle/working/index.faiss")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--gpus", type=int, default=0)
    parser.add_argument("--checkpoint-dir", default="/kaggle/working/.checkpoint")
    parser.add_argument("--checkpoint-every", type=int, default=10)
    parser.add_argument("--fresh", action="store_true")
    args, _ = parser.parse_known_args()
    path = metadata_path(args.metadata)
    records = read_records(path)
    texts = [record["texto"].strip() for record in records]
    digest = hashlib.sha256("".join(json.dumps(r, sort_keys=True) for r in records).encode()).hexdigest()
    gpu_count = torch.cuda.device_count()
    used_gpus = gpu_count if args.gpus <= 0 else min(args.gpus, gpu_count)
    print(f"[{LABEL}] Metadata: {path}\n[{LABEL}] Registros: {len(records):,}\nGPU: {used_gpus}", flush=True)
    model = SentenceTransformer(MODEL_NAME, device="cuda:0" if used_gpus else "cpu")
    checkpoint = Path(args.checkpoint_dir)
    state_file, vectors_file = checkpoint / "state.json", checkpoint / "vectors.npy"
    saved, start = [], 0
    if not args.fresh and state_file.exists() and vectors_file.exists():
        state = json.loads(state_file.read_text())
        if state.get("digest") == digest:
            start = int(state["next"])
            saved = [np.load(vectors_file)]
            print(f"[{LABEL}] Reanudando desde {start:,}.", flush=True)
    pool = model.start_multi_process_pool(target_devices=[f"cuda:{i}" for i in range(used_gpus)]) if used_gpus > 1 else None
    vectors = saved
    started = time.perf_counter()
    step = args.batch_size * max(used_gpus, 1)
    try:
        for position in range(start, len(texts), step):
            batch = texts[position:position + step]
            encoded = model.encode(batch, pool=pool, batch_size=args.batch_size, chunk_size=args.batch_size, show_progress_bar=False, convert_to_numpy=True) if pool else model.encode(batch, batch_size=args.batch_size, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True)
            encoded = np.asarray(encoded, dtype="float32")
            encoded /= np.maximum(np.linalg.norm(encoded, axis=1, keepdims=True), 1e-12)
            vectors.append(encoded)
            done = position + len(batch)
            print(f"[{LABEL}] {done:,}/{len(texts):,} ({done * 100 / len(texts):.2f}%) | {done / max(time.perf_counter() - started, 1e-9):.1f} registros/s", flush=True)
            if args.checkpoint_every and ((position // step) + 1) % args.checkpoint_every == 0:
                checkpoint.mkdir(parents=True, exist_ok=True)
                np.save(vectors_file, np.concatenate(vectors))
                state_file.write_text(json.dumps({"next": done, "digest": digest}))
    finally:
        if pool:
            model.stop_multi_process_pool(pool)
    matrix = np.concatenate(vectors)
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    faiss.write_index(index, args.output_index)
    if checkpoint.exists():
        shutil.rmtree(checkpoint)
    print(f"[{LABEL}] Listo: {index.ntotal:,} vectores -> {args.output_index}", flush=True)


if __name__ == "__main__":
    main()
