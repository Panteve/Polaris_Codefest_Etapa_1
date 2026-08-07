"""Utilidades compartidas para generar indices FAISS en la Fase 3."""

from __future__ import annotations

import json
import hashlib
import shutil
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable

import faiss
import numpy as np


def read_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: se esperaba un objeto JSON.")
            records.append(value)
    return records


def select_records(records: list[dict], selector: Callable[[dict], bool] | None) -> list[dict]:
    if selector is None:
        return records
    return [record for record in records if selector(record)]


REQUIRED_METADATA_FIELDS = {
    "doc_id",
    "chunk_id",
    "fuente",
    "formato",
    "fenomeno",
    "posicion",
    "num_tokens",
    "texto",
}


def validate_records(records: list[dict]) -> None:
    for number, record in enumerate(records, 1):
        missing = sorted(field for field in REQUIRED_METADATA_FIELDS if field not in record)
        if missing:
            raise ValueError(
                f"El registro {number} ({record.get('chunk_id', '?')}) no tiene: "
                + ", ".join(missing)
            )
        text = str(record.get("texto", "")).strip()
        if not text:
            raise ValueError(f"El registro {number} no tiene texto.")


def records_fingerprint(records: list[dict]) -> str:
    digest = hashlib.sha256()
    for record in records:
        encoded = json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
        digest.update(encoded)
        digest.update(b"\n")
    return digest.hexdigest()


def atomic_json_write(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def save_checkpoint(
    checkpoint_dir: Path,
    vectors: np.ndarray,
    next_position: int,
    records_hash: str,
    model_name: str,
    label: str,
) -> None:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    vectors_path = checkpoint_dir / "vectors.npy"
    temporary_vectors = checkpoint_dir / "vectors.npy.tmp"
    with temporary_vectors.open("wb") as handle:
        np.save(handle, vectors)
    temporary_vectors.replace(vectors_path)
    atomic_json_write(
        checkpoint_dir / "state.json",
        {
            "next_position": next_position,
            "records": int(vectors.shape[0]),
            "records_hash": records_hash,
            "model": model_name,
            "label": label,
        },
    )
    print(f"[{label}] Checkpoint guardado: {next_position:,} registros", flush=True)


def load_checkpoint(
    checkpoint_dir: Path,
    records_hash: str,
    model_name: str,
    label: str,
) -> tuple[np.ndarray, int] | None:
    state_path = checkpoint_dir / "state.json"
    vectors_path = checkpoint_dir / "vectors.npy"
    if not state_path.exists() or not vectors_path.exists():
        return None
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("records_hash") != records_hash or state.get("model") != model_name:
        print(f"[{label}] Checkpoint incompatible; se inicia desde cero.", flush=True)
        return None
    vectors = np.load(vectors_path, allow_pickle=False).astype("float32")
    expected_vectors = int(state.get("records", vectors.shape[0]))
    if vectors.shape[0] != expected_vectors:
        print(f"[{label}] Checkpoint incompleto; se inicia desde cero.", flush=True)
        return None
    next_position = int(state.get("next_position", 0))
    print(f"[{label}] Reanudando desde el registro {next_position:,}.", flush=True)
    return vectors, next_position


def discard_checkpoint(checkpoint_dir: Path) -> None:
    if checkpoint_dir.exists():
        shutil.rmtree(checkpoint_dir)


def progress(done: int, total: int, started: float, prefix: str = "Procesados") -> None:
    elapsed = max(time.perf_counter() - started, 1e-9)
    rate = done / elapsed
    percent = done * 100 / total if total else 100.0
    print(
        f"[{prefix}] {done:,}/{total:,} ({percent:6.2f}%) | "
        f"{rate:,.1f} registros/s | transcurrido {elapsed:,.1f}s",
        flush=True,
    )


def build_standard_index(
    *,
    metadata_path: Path,
    output_index: Path,
    model_name: str,
    batch_size: int,
    device: str | None,
    selector: Callable[[dict], bool] | None = None,
    label: str,
    checkpoint_dir: Path,
    checkpoint_every: int,
    fresh: bool,
) -> None:
    from sentence_transformers import SentenceTransformer

    print(f"[{label}] Leyendo metadata: {metadata_path}", flush=True)
    records = select_records(read_jsonl(metadata_path), selector)
    if not records:
        raise ValueError("No hay registros para indexar después de aplicar el filtro.")
    validate_records(records)
    records_hash = records_fingerprint(records)
    texts = [str(record.get("texto", "")).strip() for record in records]
    if any(not text for text in texts):
        missing = sum(not text for text in texts)
        raise ValueError(f"Hay {missing} registros sin el campo 'texto'.")

    print(f"[{label}] Registros seleccionados: {len(records):,}", flush=True)
    print(f"[{label}] Cargando encoder: {model_name}", flush=True)
    model = SentenceTransformer(model_name, device=device)
    started = time.perf_counter()
    checkpoint = None if fresh else load_checkpoint(checkpoint_dir, records_hash, model_name, label)
    completed_vectors = checkpoint[0] if checkpoint else np.empty((0, 0), dtype="float32")
    start_position = checkpoint[1] if checkpoint else 0
    vectors = [completed_vectors] if start_position else []
    total = len(texts)
    for start in range(start_position, total, batch_size):
        batch = texts[start : start + batch_size]
        tokenized = model.tokenizer(batch, padding=False, truncation=False, add_special_tokens=True)
        max_length = model.get_max_seq_length()
        if max_length and max(len(item) for item in tokenized["input_ids"]) > max_length:
            raise ValueError(f"Hay un chunk que supera la ventana de {max_length} tokens de {model_name}.")
        encoded = model.encode(
            batch,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        vectors.append(np.asarray(encoded, dtype="float32"))
        progress(min(start + len(batch), total), total, started, label)
        completed = start + len(batch)
        batch_number = (start // batch_size) + 1
        if checkpoint_every > 0 and batch_number % checkpoint_every == 0:
            save_checkpoint(
                checkpoint_dir,
                np.concatenate(vectors, axis=0),
                completed,
                records_hash,
                model_name,
                label,
            )

    matrix = np.concatenate(vectors, axis=0)
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    output_index.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(output_index))
    discard_checkpoint(checkpoint_dir)
    elapsed = time.perf_counter() - started
    print(
        f"[{label}] Listo: {index.ntotal:,} vectores, dimensión {matrix.shape[1]}, "
        f"tiempo {elapsed:,.1f}s",
        flush=True,
    )
    print(f"[{label}] Índice: {output_index}", flush=True)


def normalise_text(text: str) -> str:
    return " ".join(text.replace("\r\n", "\n").replace("\r", "\n").split())


def load_document_texts(manifest_path: Path) -> dict[str, str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = {}
    for item in manifest:
        doc_id = str(item.get("doc_id", ""))
        final_path = item.get("archivo_final")
        if not final_path:
            final_path = item.get("ruta_final")
        if not doc_id or not final_path:
            continue
        path = Path(final_path)
        if not path.is_absolute():
            path = manifest_path.parent / path
        if path.exists():
            result[doc_id] = normalise_text(path.read_text(encoding="utf-8", errors="replace"))
    return result


def build_late_index(
    *,
    metadata_path: Path,
    manifest_path: Path,
    output_index: Path,
    model_name: str,
    device: str | None,
    selector: Callable[[dict], bool] | None = None,
    label: str,
    checkpoint_dir: Path,
    checkpoint_every: int,
    fresh: bool,
) -> None:
    import torch
    from transformers import AutoModel, AutoTokenizer

    print(f"[{label}] Leyendo metadata: {metadata_path}", flush=True)
    records = select_records(read_jsonl(metadata_path), selector)
    if not records:
        raise ValueError("No hay registros PDF para indexar.")
    validate_records(records)
    records_hash = records_fingerprint(records)
    texts_by_doc = load_document_texts(manifest_path)
    print(f"[{label}] Documentos con texto fuente: {len(texts_by_doc):,}", flush=True)
    print(f"[{label}] Cargando tokenizer y encoder: {model_name}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    if device:
        model.to(device)
    model.eval()

    grouped = defaultdict(list)
    for position, record in enumerate(records):
        grouped[str(record.get("doc_id"))].append((position, record))
    checkpoint = None if fresh else load_checkpoint(checkpoint_dir, records_hash, model_name, label)
    saved_vectors = checkpoint[0] if checkpoint else np.empty((0, 0), dtype="float32")
    start_document = checkpoint[1] if checkpoint else 0
    vectors = [None] * len(records)
    if start_document:
        saved_records = sum(len(items) for items in list(grouped.values())[:start_document])
        for position in range(saved_records):
            vectors[position] = saved_vectors[position]
    started = time.perf_counter()
    documents_done = 0
    grouped_items = list(grouped.items())
    for document_number, (doc_id, items) in enumerate(grouped_items):
        if document_number < start_document:
            continue
        document = texts_by_doc.get(doc_id)
        if document is None:
            raise FileNotFoundError(f"No se encontró el texto fuente para {doc_id}.")
        encoded = tokenizer(
            document,
            return_tensors="pt",
            return_offsets_mapping=True,
            truncation=False,
        )
        offsets = encoded.pop("offset_mapping")[0].tolist()
        model_device = next(model.parameters()).device
        max_length = getattr(model.config, "max_position_embeddings", None)
        if max_length and encoded["input_ids"].shape[1] > max_length:
            raise ValueError(f"{doc_id} supera la ventana de {max_length} tokens de {model_name}.")
        model_inputs = {key: value.to(model_device) for key, value in encoded.items()}
        with torch.no_grad():
            hidden = model(**model_inputs).last_hidden_state[0]
        for position, record in items:
            start = int(record.get("char_start", 0))
            end = int(record.get("char_end", 0))
            selected = [
                index
                for index, (token_start, token_end) in enumerate(offsets)
                if token_end > start and token_start < end and token_end > token_start
            ]
            if not selected:
                raise ValueError(f"No se encontraron tokens para {record.get('chunk_id')}.")
            vector = hidden[selected].mean(dim=0).cpu().numpy().astype("float32")
            vector /= max(float(np.linalg.norm(vector)), 1e-12)
            vectors[position] = vector
        documents_done = document_number + 1
        progress(documents_done, len(grouped), started, label)
        if checkpoint_every > 0 and documents_done % checkpoint_every == 0:
            complete_vectors = np.vstack([vector for vector in vectors if vector is not None])
            save_checkpoint(
                checkpoint_dir,
                complete_vectors,
                documents_done,
                records_hash,
                model_name,
                label,
            )

    matrix = np.vstack(vectors).astype("float32")
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    output_index.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(output_index))
    discard_checkpoint(checkpoint_dir)
    print(
        f"[{label}] Listo: {index.ntotal:,} vectores, dimensión {matrix.shape[1]}",
        flush=True,
    )
    print(f"[{label}] Índice: {output_index}", flush=True)
