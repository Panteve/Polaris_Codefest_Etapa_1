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
    args, _ = parser.parse_known_args()
    path = metadata_path(args.metadata)
    records = read_records(path)
    texts = [record["texto"].strip() for record in records]
    gpu_count = torch.cuda.device_count()
    used_gpus = gpu_count if args.gpus <= 0 else min(args.gpus, gpu_count)
    print(f"[{LABEL}] Metadata: {path}\n[{LABEL}] Registros: {len(records):,}\nGPU: {used_gpus}", flush=True)
    model = SentenceTransformer(MODEL_NAME, device="cuda:0" if used_gpus else "cpu")
    pool = model.start_multi_process_pool(target_devices=[f"cuda:{i}" for i in range(used_gpus)]) if used_gpus > 1 else None
    vectors = []
    started = time.perf_counter()
    step = args.batch_size * max(used_gpus, 1)
    next_milestone = 5
    try:
        for position in range(0, len(texts), step):
            batch = texts[position:position + step]
            encoded = model.encode(batch, pool=pool, batch_size=args.batch_size, chunk_size=args.batch_size, show_progress_bar=False, convert_to_numpy=True) if pool else model.encode(batch, batch_size=args.batch_size, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True)
            encoded = np.asarray(encoded, dtype="float32")
            encoded /= np.maximum(np.linalg.norm(encoded, axis=1, keepdims=True), 1e-12)
            vectors.append(encoded)
            done = position + len(batch)
            percent = done * 100 / len(texts)
            while next_milestone <= 100 and percent >= next_milestone:
                elapsed = max(time.perf_counter() - started, 1e-9)
                print(f"[{LABEL}] {done:,}/{len(texts):,} ({next_milestone}%) | {done / elapsed:.1f} registros/s | {elapsed:.1f}s", flush=True)
                next_milestone += 5
    finally:
        if pool:
            model.stop_multi_process_pool(pool)
    matrix = np.concatenate(vectors)
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    faiss.write_index(index, args.output_index)
    print(f"[{LABEL}] Listo: {index.ntotal:,} vectores -> {args.output_index}", flush=True)


if __name__ == "__main__":
    main()
