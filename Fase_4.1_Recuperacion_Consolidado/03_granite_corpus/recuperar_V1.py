"""Recuperacion densa basica para el indice Granite del corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import faiss
from sentence_transformers import SentenceTransformer


MODEL_NAME = "ibm-granite/granite-embedding-311m-multilingual-r2"
FOLDER = Path(__file__).resolve().parent
DATA = FOLDER


def read_metadata(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"La metadata debe contener objetos JSON: {path}:{line_number}")
            records.append(value)
    return records


def retrieve(question: str, model: SentenceTransformer, index: faiss.Index, records: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    if not question.strip():
        raise ValueError("La pregunta no puede estar vacia.")
    vector = model.encode([question], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False).astype("float32")
    scores, positions = index.search(vector, min(args.top_k, index.ntotal))
    fragments = []
    seen_documents = set()
    documents = []
    for rank, (score, position) in enumerate(zip(scores[0], positions[0]), 1):
        if position < 0 or position >= len(records):
            continue
        record = records[int(position)]
        if float(score) < args.threshold:
            continue
        if args.fenomeno is not None and str(record.get("fenomeno")) != str(args.fenomeno):
            continue
        if args.idioma and str(record.get("idioma", "")).lower() != args.idioma.lower():
            continue
        if args.formato and str(record.get("formato", "")).lower() != args.formato.lower():
            continue
        fragments.append({
            "rank": rank,
            "chunk_id": record.get("chunk_id"),
            "doc_id": record.get("doc_id"),
            "text": record.get("texto", ""),
            "score": float(score),
            "fuente": record.get("fuente"),
            "fenomeno": record.get("fenomeno"),
            "idioma": record.get("idioma"),
        })
        doc_id = record.get("doc_id")
        if doc_id not in seen_documents and len(documents) < 3:
            seen_documents.add(doc_id)
            documents.append({"rank": len(documents) + 1, "doc_id": doc_id, "score": float(score)})
    return {"query_id": "q001", "query": question, "documents": documents, "fragments": fragments}


def main() -> None:
    parser = argparse.ArgumentParser(description="Recuperacion basica con Granite.")
    parser.add_argument("--query", help="Ejecuta una sola pregunta y termina.")
    parser.add_argument("--top-k", type=int, default=20, help="Cantidad mÃ¡xima de vecinos directos.")
    parser.add_argument("--model", default=MODEL_NAME, help="Encoder para codificar la consulta.")
    parser.add_argument("--device", default=None)
    parser.add_argument("--index", type=Path, default=DATA / "index.faiss")
    parser.add_argument("--metadata", type=Path, default=DATA / "metadata.jsonl")
    parser.add_argument("--output-json", type=Path, default=FOLDER / "resultado.json")
    parser.add_argument("--output", type=Path, help="Guarda cada respuesta como una lÃ­nea JSONL.")
    parser.add_argument("--threshold", type=float, default=-1.0)
    parser.add_argument("--fenomeno", type=int, choices=(1, 2, 3))
    parser.add_argument("--idioma", help="Filtro opcional: es, en o pt.")
    parser.add_argument("--formato", help="Filtro opcional: pdf, json, csv, txt, etc.")
    args = parser.parse_args()
    if args.top_k < 1:
        raise ValueError("--top-k debe ser mayor que cero.")
    if not args.index.exists() or not args.metadata.exists():
        raise FileNotFoundError("No existe el indice o la metadata de esta configuracion.")
    index = faiss.read_index(str(args.index))
    records = read_metadata(args.metadata)
    if index.ntotal != len(records):
        raise ValueError("El indice y la metadata no tienen la misma cantidad de registros.")
    model = SentenceTransformer(args.model, device=args.device)
    questions = [args.query] if args.query else iter(lambda: input("Pregunta> "), "salir")
    output_handle = args.output.open("w", encoding="utf-8") if args.output else None
    results = []
    try:
        for number, question in enumerate(questions, 1):
            result = retrieve(question, model, index, records, args)
            result["query_id"] = f"q{number:03d}"
            results.append(result)
            print(json.dumps(result, ensure_ascii=False))
            if output_handle:
                output_handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                output_handle.flush()
    except EOFError:
        pass
    if output_handle:
        output_handle.close()
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, ImportError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
