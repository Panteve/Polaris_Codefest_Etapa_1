from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import faiss
from sentence_transformers import SentenceTransformer

BASE = Path(__file__).resolve().parents[2] / "Fase_4_Recuperacion" / "01_bge_m3_corpus"
sys.path.insert(0, str(BASE))
from recuperar import print_result, read_jsonl, result_for_jsonl, retrieve  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BGE_DATA = ROOT / "Fase_3_Encoder" / "02_hibrido_bge_m3_no_pdf"
GRANITE_DATA = ROOT / "Fase_3_Encoder" / "02_hibrido_granite_late_pdf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recuperación híbrida BGE-M3 + Granite late.")
    parser.add_argument("--query", help="Ejecuta una pregunta y termina.")
    parser.add_argument("--bge-index", type=Path, default=BGE_DATA / "index.faiss")
    parser.add_argument("--bge-metadata", type=Path, default=BGE_DATA / "metadata.jsonl")
    parser.add_argument("--granite-index", type=Path, default=GRANITE_DATA / "index.faiss")
    parser.add_argument("--granite-metadata", type=Path, default=GRANITE_DATA / "metadata.jsonl")
    parser.add_argument("--bge-model", default="BAAI/bge-m3")
    parser.add_argument("--granite-model", default="ibm-granite/granite-embedding-311m-multilingual-r2")
    parser.add_argument("--device", default=None)
    parser.add_argument("--candidate-chunks", type=int, default=20)
    parser.add_argument("--doc-score", choices=("mean", "sum"), default="mean")
    parser.add_argument("--threshold", type=float, default=-1.0)
    parser.add_argument("--fenomeno", type=int, choices=(1, 2, 3), default=None)
    parser.add_argument("--idioma", default=None)
    parser.add_argument("--formato", default=None)
    parser.add_argument("--output-json", type=Path, default=Path(__file__).resolve().parent / "resultados.json")
    return parser.parse_args()


def load_component(index_path: Path, metadata_path: Path) -> tuple[faiss.Index, list[dict[str, Any]]]:
    if not index_path.exists():
        raise FileNotFoundError(f"No existe el índice FAISS: {index_path}")
    if not metadata_path.exists():
        raise FileNotFoundError(f"No existe la metadata: {metadata_path}")
    index = faiss.read_index(str(index_path))
    records = read_jsonl(metadata_path)
    if index.ntotal != len(records):
        raise ValueError(f"Desalineación en {index_path}: índice={index.ntotal}, metadata={len(records)}")
    return index, records


def hybrid_result(question: str, args: argparse.Namespace, models: tuple[Any, Any], components: tuple[Any, Any], query_id: str) -> dict[str, Any]:
    bge_result = retrieve(question, models[0], components[0][0], components[0][1], args, query_id)
    granite_result = retrieve(question, models[1], components[1][0], components[1][1], args, query_id)
    fused: dict[tuple[str, str], dict[str, Any]] = {}
    for result in (bge_result, granite_result):
        for rank, fragment in enumerate(result["fragments"], 1):
            key = (str(fragment["doc_id"]), str(fragment["chunk_id"]))
            item = fused.setdefault(key, {**fragment, "score": 0.0})
            item["score"] += 1.0 / (60 + rank)
    chunks = sorted(fused.values(), key=lambda item: item["score"], reverse=True)
    by_doc: dict[str, list[float]] = defaultdict(list)
    for item in chunks:
        by_doc[str(item["doc_id"])].append(float(item["score"]))
    if args.doc_score == "sum":
        doc_scores = {doc: sum(scores) for doc, scores in by_doc.items()}
    else:
        doc_scores = {
            doc: sum(sorted(scores, reverse=True)[:3]) / min(len(scores), 3)
            for doc, scores in by_doc.items()
        }
    documents = [
        {"rank": rank, "doc_id": doc, "score": score}
        for rank, (doc, score) in enumerate(sorted(doc_scores.items(), key=lambda item: item[1], reverse=True)[:3], 1)
    ]
    return {"query_id": query_id, "query": question, "documents": documents, "fragments": chunks[:10]}


def main() -> None:
    args = parse_args()
    if args.candidate_chunks < 10:
        raise ValueError("--candidate-chunks debe ser como mínimo 10.")
    components = (load_component(args.bge_index, args.bge_metadata), load_component(args.granite_index, args.granite_metadata))
    models = (
        SentenceTransformer(args.bge_model, device=args.device),
        SentenceTransformer(args.granite_model, device=args.device),
    )
    results = []
    questions = [args.query] if args.query else iter(lambda: input("Pregunta> "), "salir")
    try:
        for number, question in enumerate(questions, 1):
            result = hybrid_result(question, args, models, components, f"q{number:03d}")
            print_result(result)
            results.append(result_for_jsonl(result))
    except EOFError:
        pass
    finally:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
