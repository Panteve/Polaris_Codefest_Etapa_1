# Instalar antes: %pip install -q -U sentence-transformers faiss-cpu transformers accelerate

from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path
from pathlib import PurePosixPath

import faiss
import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

KAGGLE_INPUT = Path("/kaggle/input")
KAGGLE_OUTPUT = Path("/kaggle/working")
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_ROOT = KAGGLE_INPUT if KAGGLE_INPUT.exists() else SCRIPT_DIR
DEFAULT_OUTPUT_ROOT = KAGGLE_OUTPUT if KAGGLE_OUTPUT.exists() else SCRIPT_DIR / "output"


def find_input_file(name: str, explicit: Path | None, input_root: Path) -> Path:
    if explicit:
        if not explicit.exists():
            raise FileNotFoundError(f"No existe el archivo: {explicit}")
        return explicit
    candidates = sorted(input_root.rglob(name))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError(f"No se encontró {name} en /kaggle/input. Usa el parámetro correspondiente.")
    raise RuntimeError(f"Hay varios {name}; indica una ruta explícita.")


def find_document(source: Path, manifest_path: Path, input_root: Path) -> Path:
    """Encuentra el documento aunque esté en otro dataset de Kaggle."""
    source_text = str(source).replace("\\", "/")
    source_posix = PurePosixPath(source_text)
    source_name = source_posix.name
    possible_paths = [
        Path(source_text) if source_posix.is_absolute() else None,
        manifest_path.parent / source_name,
        manifest_path.parent / Path(source_text),
        input_root / Path(source_text),
    ]
    for candidate in possible_paths:
        if candidate is not None and candidate.exists() and candidate.is_file():
            return candidate
    candidates = sorted(
        candidate for candidate in input_root.rglob(source_name) if candidate.is_file()
    )
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError(f"No se encontró el documento fuente: {source.name}")
    raise RuntimeError(f"Hay varias copias de {source.name}; indica una estructura sin duplicados.")


def normalise_text(text: str) -> str:
    return " ".join(text.replace("\r\n", "\n").replace("\r", "\n").split())


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def prepare_window_inputs(tokenizer, content_ids):
    """Agrega tokens especiales compatible con tokenizers clÃ¡sicos y TokenizersBackend."""
    return None


def encode_document_windows(document, items, tokenizer, model, model_device, window_tokens):
    tokenized = tokenizer(document, add_special_tokens=False, return_offsets_mapping=True, truncation=False)
    full_ids = tokenized["input_ids"]
    content = [
        (position, int(start), int(end))
        for position, (start, end) in enumerate(tokenized["offset_mapping"])
        if int(end) > int(start)
    ]
    max_length = getattr(model.config, "max_position_embeddings", None)
    if not max_length or max_length > 100000:
        max_length = tokenizer.model_max_length
    if not max_length or max_length > 100000:
        max_length = 512
    requested_length = min(int(window_tokens), int(max_length))
    capacity = requested_length - int(tokenizer.num_special_tokens_to_add(pair=False)) - 2
    if capacity <= 0:
        raise ValueError("La ventana máxima no permite tokens de contenido.")
    chunk_ranges = {}
    for position, record in items:
        start, end = int(record["char_start"]), int(record["char_end"])
        selected = [index for index, (_, token_start, token_end) in enumerate(content)
                    if token_end > start and token_start < end]
        if not selected:
            raise ValueError(f"No se encontraron tokens para {record['chunk_id']}.")
        chunk_ranges[position] = (start, end)
    sentence_token_ranges = []
    for match in re.finditer(r"\S.*?(?:[.!?。！？]+(?=\s|$)|$)", document, flags=re.DOTALL):
        sentence_start, sentence_end = match.span()
        tokens = [index for index, (_, token_start, token_end) in enumerate(content)
                  if token_end > sentence_start and token_start < sentence_end]
        if tokens:
            start_token, end_token = min(tokens), max(tokens) + 1
            for piece_start in range(start_token, end_token, capacity):
                sentence_token_ranges.append((piece_start, min(piece_start + capacity, end_token)))
    windows = []
    sentence_index = 0
    while sentence_index < len(sentence_token_ranges):
        window_start = sentence_token_ranges[sentence_index][0]
        window_end = window_start
        next_index = sentence_index
        while next_index < len(sentence_token_ranges):
            candidate_end = sentence_token_ranges[next_index][1]
            if next_index > sentence_index and candidate_end - window_start > capacity:
                break
            window_end = candidate_end
            next_index += 1
            if window_end - window_start >= capacity:
                break
        windows.append((window_start, window_end))
        if next_index >= len(sentence_token_ranges):
            break
        sentence_index = max(sentence_index + 1, next_index - 2)
    if not windows:
        windows = [(0, len(content))]

    accumulators = {position: [] for position, _ in items}
    for window_start, window_end in windows:
        window_char_start = content[window_start][1]
        window_char_end = content[window_end - 1][2]
        window_text = document[window_char_start:window_char_end]
        window_encoding = tokenizer(
            window_text,
            add_special_tokens=True,
            return_offsets_mapping=True,
            return_tensors="pt",
            truncation=False,
        )
        input_ids = window_encoding["input_ids"].to(model_device)
        attention_mask = window_encoding["attention_mask"].to(model_device)
        window_offsets = window_encoding["offset_mapping"][0].tolist()
        inputs = {"input_ids": input_ids, "attention_mask": attention_mask}
        with torch.inference_mode():
            if str(model_device).startswith("cuda"):
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    hidden = model(**inputs).last_hidden_state[0]
            else:
                hidden = model(**inputs).last_hidden_state[0]
        for position, (chunk_start, chunk_end) in chunk_ranges.items():
            local = [
                index
                for index, (token_start, token_end) in enumerate(window_offsets)
                if token_end > token_start
                and token_end + window_char_start > chunk_start
                and token_start + window_char_start < chunk_end
            ]
            if local:
                accumulators[position].append(hidden[local].mean(dim=0).cpu().numpy().astype("float32"))
    vectors = {}
    for position, values in accumulators.items():
        if not values:
            raise ValueError(f"No se pudo asignar ninguna ventana al registro {position}.")
        vector = np.vstack(values).mean(axis=0).astype("float32")
        vector /= max(float(np.linalg.norm(vector)), 1e-12)
        vectors[position] = vector
    return vectors


def main() -> None:
    parser = argparse.ArgumentParser(description="Índice Granite late para PDF en Kaggle.")
    parser.add_argument("--metadata", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-index", type=Path, default=DEFAULT_OUTPUT_ROOT / "index.faiss")
    parser.add_argument("--device", default="auto", choices=("auto", "cuda", "cpu"))
    parser.add_argument("--window-tokens", type=int, default=2048)
    # Kaggle/Colab agrega argumentos internos como -f y --HistoryManager.
    args, _ = parser.parse_known_args()
    input_root = args.input_root.resolve()
    if not input_root.exists():
        raise FileNotFoundError(f"No existe la raÃ­z de entrada: {input_root}")
    if args.window_tokens < 128:
        raise ValueError("--window-tokens debe ser al menos 128.")
    metadata_path = find_input_file("metadata.jsonl", args.metadata, input_root)
    manifest_path = find_input_file("manifiesto_late_local.json", args.manifest, input_root)
    print(f"[Granite late Kaggle] Metadata: {metadata_path}", flush=True)
    print(f"[Granite late Kaggle] Manifiesto: {manifest_path}", flush=True)
    records = [r for r in read_jsonl(metadata_path) if str(r.get("formato", "")).lower() == "pdf"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_doc = {str(item["doc_id"]): item for item in manifest}
    grouped = defaultdict(list)
    for position, record in enumerate(records):
        grouped[str(record["doc_id"])].append((position, record))
    device = "cuda" if args.device == "auto" and torch.cuda.is_available() else args.device
    if device == "auto":
        device = "cpu"
    print(f"[Granite late] Dispositivo: {device} | Ventana: {args.window_tokens:,} tokens", flush=True)
    tokenizer = AutoTokenizer.from_pretrained("ibm-granite/granite-embedding-311m-multilingual-r2")
    model = AutoModel.from_pretrained("ibm-granite/granite-embedding-311m-multilingual-r2").to(device)
    model.eval()
    vectors = [None] * len(records)
    total_documents = len(grouped)
    started = time.perf_counter()
    next_milestone = 5
    for document_number, (doc_id, items) in enumerate(grouped.items(), 1):
        source_info = by_doc.get(doc_id)
        if not source_info:
            raise FileNotFoundError(f"No hay manifiesto para {doc_id}.")
        source = find_document(Path(source_info["archivo_final"]), manifest_path, input_root)
        document = normalise_text(source.read_text(encoding="utf-8", errors="replace"))
        encoded_vectors = encode_document_windows(document, items, tokenizer, model, device, args.window_tokens)
        for position, vector in encoded_vectors.items():
            vectors[position] = vector
        percent = document_number * 100 / total_documents
        while next_milestone <= 100 and percent >= next_milestone:
            elapsed = max(time.perf_counter() - started, 1e-9)
            print(f"Documentos procesados: {document_number:,}/{total_documents:,} ({next_milestone}%) | {doc_id} | {elapsed:.1f}s", flush=True)
            next_milestone += 5
    matrix = np.vstack(vectors).astype("float32")
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    args.output_index.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(args.output_index))
    print(f"Índice listo: {args.output_index} | vectores: {index.ntotal:,}")


if __name__ == "__main__":
    main()
