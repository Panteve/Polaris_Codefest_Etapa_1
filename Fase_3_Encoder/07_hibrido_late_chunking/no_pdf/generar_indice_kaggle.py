# Instalar antes: %pip install -q -U sentence-transformers faiss-cpu transformers accelerate

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

KAGGLE_INPUT = Path("/kaggle/input")
KAGGLE_OUTPUT = Path("/kaggle/working")


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
    raise RuntimeError("Hay varias metadata.jsonl; indica una con --metadata:\n" + "\n".join(map(str, candidates)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Índice BGE-M3 para no-PDF en Kaggle.")
    parser.add_argument("--metadata", type=Path, default=None)
    parser.add_argument("--output-index", type=Path, default=KAGGLE_OUTPUT / "index.faiss")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--device", default="cuda")
    # Kaggle/Colab agrega argumentos internos como -f y --HistoryManager.
    args, _ = parser.parse_known_args()
    metadata_path = find_metadata(args.metadata)
    print(f"[BGE-M3 no-PDF Kaggle] Metadata: {metadata_path}", flush=True)
    records = []
    with metadata_path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                record = json.loads(line)
                if str(record.get("formato", "")).lower() != "pdf":
                    records.append(record)
    if not records:
        raise ValueError("No hay registros no-PDF en la metadata.")
    texts = [str(record.get("texto", "")).strip() for record in records]
    if any(not text for text in texts):
        raise ValueError("La metadata contiene registros no-PDF sin texto.")
    model = SentenceTransformer("BAAI/bge-m3", device=args.device)
    vectors_by_batch = []
    total = len(texts)
    started = time.perf_counter()
    next_milestone = 5
    for start in range(0, total, args.batch_size):
        batch = texts[start : start + args.batch_size]
        encoded = model.encode(
            batch,
            batch_size=args.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        vectors_by_batch.append(np.asarray(encoded, dtype="float32"))
        done = min(start + len(batch), total)
        percent = done * 100 / total
        while next_milestone <= 100 and percent >= next_milestone:
            elapsed = max(time.perf_counter() - started, 1e-9)
            print(f"Procesados: {done:,}/{total:,} ({next_milestone}%) | {done / elapsed:.1f} registros/s | {elapsed:.1f}s", flush=True)
            next_milestone += 5
    vectors = np.vstack(vectors_by_batch).astype("float32")
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    faiss.write_index(index, str(args.output_index))
    print(f"Índice listo: {args.output_index} | vectores: {index.ntotal:,}")


if __name__ == "__main__":
    main()
