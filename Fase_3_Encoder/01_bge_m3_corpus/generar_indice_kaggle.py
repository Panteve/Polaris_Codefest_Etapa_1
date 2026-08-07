"""Genera el índice BGE-M3 en Kaggle usando una o varias GPU CUDA."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import faiss
import numpy as np


MODEL_NAME = "BAAI/bge-m3"
KAGGLE_INPUT = Path("/kaggle/input")
KAGGLE_OUTPUT = Path("/kaggle/working")


def read_metadata(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: se esperaba un objeto JSON.")
            if not str(value.get("texto", "")).strip():
                raise ValueError(f"{path}:{line_number}: el registro no tiene texto.")
            records.append(value)
    if not records:
        raise ValueError(f"No se encontraron registros en {path}.")
    return records


def fingerprint(records: list[dict]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def find_metadata(explicit: Path | None) -> Path:
    if explicit:
        if not explicit.exists():
            raise FileNotFoundError(f"No existe la metadata: {explicit}")
        return explicit
    candidates = sorted(KAGGLE_INPUT.rglob("metadata.jsonl"))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError("No se encontró metadata.jsonl en /kaggle/input. Usa --metadata.")
    raise RuntimeError(
        "Hay varias metadata.jsonl; indica una con --metadata:\n"
        + "\n".join(str(path) for path in candidates)
    )


def progress(done: int, total: int, started: float) -> None:
    elapsed = max(time.perf_counter() - started, 1e-9)
    print(
        f"[BGE-M3 Kaggle] {done:,}/{total:,} ({done * 100 / total:6.2f}%) | "
        f"{done / elapsed:,.1f} registros/s | {elapsed:,.1f}s",
        flush=True,
    )


def save_checkpoint(path: Path, vectors: np.ndarray, next_position: int, metadata_hash: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    np.save(path / "vectors.npy", vectors)
    (path / "state.json").write_text(
        json.dumps({"next_position": next_position, "metadata_hash": metadata_hash, "model": MODEL_NAME}, indent=2),
        encoding="utf-8",
    )
    print(f"[BGE-M3 Kaggle] Checkpoint guardado: {next_position:,} registros.", flush=True)


def load_checkpoint(path: Path, metadata_hash: str, fresh: bool) -> tuple[np.ndarray, int] | None:
    if fresh or not (path / "state.json").exists() or not (path / "vectors.npy").exists():
        return None
    state = json.loads((path / "state.json").read_text(encoding="utf-8"))
    if state.get("metadata_hash") != metadata_hash or state.get("model") != MODEL_NAME:
        print("[BGE-M3 Kaggle] Checkpoint incompatible; se inicia desde cero.", flush=True)
        return None
    next_position = int(state.get("next_position", 0))
    print(f"[BGE-M3 Kaggle] Reanudando desde el registro {next_position:,}.", flush=True)
    return np.load(path / "vectors.npy"), next_position


def encode_records(model, texts, batch_size, gpu_count, checkpoint_dir, metadata_hash, checkpoint_every, fresh):
    from sentence_transformers import SentenceTransformer

    checkpoint = load_checkpoint(checkpoint_dir, metadata_hash, fresh)
    saved = checkpoint[0] if checkpoint else np.empty((0, 0), dtype="float32")
    start_position = checkpoint[1] if checkpoint else 0
    vectors = [saved] if start_position else []
    pool = None
    if gpu_count > 1:
        devices = [f"cuda:{index}" for index in range(gpu_count)]
        print(f"[BGE-M3 Kaggle] Usando: {', '.join(devices)}", flush=True)
        pool = model.start_multi_process_pool(target_devices=devices)
    started = time.perf_counter()
    try:
        total = len(texts)
        step = batch_size * max(gpu_count, 1)
        for start in range(start_position, total, step):
            batch = texts[start : start + step]
            if pool is not None:
                encoded = model.encode(
                    batch,
                    pool=pool,
                    batch_size=batch_size,
                    chunk_size=batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                )
            else:
                encoded = model.encode(
                    batch, batch_size=batch_size, show_progress_bar=False,
                    convert_to_numpy=True, normalize_embeddings=True,
                )
            encoded = np.asarray(encoded, dtype="float32")
            encoded /= np.maximum(np.linalg.norm(encoded, axis=1, keepdims=True), 1e-12)
            vectors.append(encoded)
            completed = start + len(batch)
            progress(completed, total)
            batch_number = (start // step) + 1
            if checkpoint_every > 0 and batch_number % checkpoint_every == 0:
                save_checkpoint(checkpoint_dir, np.concatenate(vectors, axis=0), completed, metadata_hash)
    finally:
        if pool is not None:
            model.stop_multi_process_pool(pool)
    return np.concatenate(vectors, axis=0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Índice BGE-M3 para Kaggle.")
    parser.add_argument("--metadata", type=Path, default=None)
    parser.add_argument("--output-index", type=Path, default=KAGGLE_OUTPUT / "index.faiss")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--gpus", type=int, default=0, help="0=usar todas las GPU CUDA disponibles")
    parser.add_argument("--checkpoint-dir", type=Path, default=KAGGLE_OUTPUT / ".checkpoint_bge_m3")
    parser.add_argument("--checkpoint-every", type=int, default=10)
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()

    import torch
    from sentence_transformers import SentenceTransformer

    metadata_path = find_metadata(args.metadata)
    records = read_metadata(metadata_path)
    texts = [str(record["texto"]).strip() for record in records]
    metadata_hash = fingerprint(records)
    available_gpus = torch.cuda.device_count()
    gpu_count = available_gpus if args.gpus <= 0 else min(args.gpus, available_gpus)
    device = "cuda:0" if gpu_count else "cpu"
    print(f"[BGE-M3 Kaggle] Metadata: {metadata_path}", flush=True)
    print(f"[BGE-M3 Kaggle] Registros: {len(records):,}", flush=True)
    print(f"[BGE-M3 Kaggle] GPU disponibles: {available_gpus}; GPU usadas: {gpu_count}", flush=True)
    print(f"[BGE-M3 Kaggle] Cargando modelo: {MODEL_NAME}", flush=True)
    model = SentenceTransformer(MODEL_NAME, device=device)
    vectors = encode_records(
        model, texts, args.batch_size, gpu_count, args.checkpoint_dir,
        metadata_hash, args.checkpoint_every, args.fresh,
    )
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    args.output_index.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(args.output_index))
    print(f"[BGE-M3 Kaggle] Listo: {index.ntotal:,} vectores, dimensión {vectors.shape[1]}.", flush=True)
    print(f"[BGE-M3 Kaggle] Índice: {args.output_index}", flush=True)


if __name__ == "__main__":
    main()
