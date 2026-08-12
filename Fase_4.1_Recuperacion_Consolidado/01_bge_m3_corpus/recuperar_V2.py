"""Recuperacion BGE-M3 con pool de recall ampliado y salida top-10."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import faiss
from sentence_transformers import CrossEncoder, SentenceTransformer


MODEL_NAME = "BAAI/bge-m3"
RERANKER_MODEL_NAME = "BAAI/bge-reranker-v2-m3"
FOLDER = Path(__file__).resolve().parent
DATA = FOLDER
DEFAULT_RECALL_TOP_K = 50
DEFAULT_OUTPUT_TOP_K = 10
DEFAULT_MMR_LAMBDA = 0.7


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


def matches_filters(record: dict[str, Any], args: argparse.Namespace, score: float) -> bool:
    if score < args.threshold:
        return False
    if args.fenomeno is not None and str(record.get("fenomeno")) != str(args.fenomeno):
        return False
    if args.idioma and str(record.get("idioma", "")).lower() != args.idioma.lower():
        return False
    if args.formato and str(record.get("formato", "")).lower() != args.formato.lower():
        return False
    return True


def min_max_normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    minimum = min(values)
    maximum = max(values)
    if maximum == minimum:
        return [1.0] * len(values)
    return [(value - minimum) / (maximum - minimum) for value in values]


def rerank_and_diversify(
    question: str,
    candidates: list[tuple[int, float, dict[str, Any]]],
    model: SentenceTransformer,
    reranker: CrossEncoder,
    args: argparse.Namespace,
) -> tuple[list[tuple[float, dict[str, Any]]], list[tuple[float, dict[str, Any]]]]:
    """Reordena el pool con cross-encoder y selecciona por MMR."""
    if not candidates:
        return [], []

    texts = [record.get("texto", "") for _, _, record in candidates]
    reranker_scores = [
        float(score)
        for score in reranker.predict(
            [(question, text) for text in texts],
            show_progress_bar=False,
        )
    ]
    relevance = min_max_normalize(reranker_scores)
    embeddings = model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    # Primero se ordena por relevancia del cross-encoder; los empates mantienen
    # el orden original de FAISS mediante el indice de candidato.
    ranked = sorted(
        range(len(candidates)),
        key=lambda index: (-reranker_scores[index], candidates[index][0]),
    )
    selected: list[int] = []
    remaining = set(ranked)
    while remaining and len(selected) < args.output_top_k:
        best_index = max(
            remaining,
            key=lambda index: (
                args.mmr_lambda * relevance[index]
                - (1.0 - args.mmr_lambda)
                * (
                    max(float(embeddings[index] @ embeddings[chosen]) for chosen in selected)
                    if selected
                    else 0.0
                ),
                -ranked.index(index),
            ),
        )
        selected.append(best_index)
        remaining.remove(best_index)

    all_scored = [(score, candidates[index][2]) for index, score in enumerate(reranker_scores)]
    selected_scored = [(reranker_scores[index], candidates[index][2]) for index in selected]
    return selected_scored, all_scored


def retrieve(
    question: str,
    model: SentenceTransformer,
    reranker: CrossEncoder,
    index: faiss.Index,
    records: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    if not question.strip():
        raise ValueError("La pregunta no puede estar vacia.")

    vector = model.encode(
        [question],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).astype("float32")

    # El recall consulta un pool amplio. La salida se limita despues de filtrar.
    recall_size = min(args.recall_top_k, index.ntotal)
    scores, positions = index.search(vector, recall_size)

    candidates = []
    for recall_rank, (score, position) in enumerate(zip(scores[0], positions[0]), 1):
        if position < 0 or position >= len(records):
            continue
        record = records[int(position)]
        score = float(score)
        if not matches_filters(record, args, score):
            continue
        candidates.append((recall_rank, score, record))

    reranked, _ = rerank_and_diversify(question, candidates, model, reranker, args)

    # Mean pooling documental sobre los fragmentos finales seleccionados por
    # MMR: cada documento se representa por el promedio de sus scores.
    document_scores: dict[Any, list[float]] = {}
    document_first_rank: dict[Any, int] = {}
    for candidate_rank, (score, record) in enumerate(reranked):
        doc_id = record.get("doc_id")
        document_scores.setdefault(doc_id, []).append(score)
        document_first_rank.setdefault(doc_id, candidate_rank)

    ranked_documents = sorted(
        document_scores.items(),
        key=lambda item: (
            -sum(item[1]) / len(item[1]),
            document_first_rank[item[0]],
        ),
    )
    documents = []
    for doc_id, scores in ranked_documents[:3]:
        documents.append(
            {
                "rank": len(documents) + 1,
                "doc_id": doc_id,
                "score": sum(scores) / len(scores),
            }
        )

    fragments = []
    for rank, (score, record) in enumerate(reranked, 1):
        fragments.append(
            {
                "rank": rank,
                "chunk_id": record.get("chunk_id"),
                "doc_id": record.get("doc_id"),
                "text": record.get("texto", ""),
                "score": score,
                "fuente": record.get("fuente"),
                "fenomeno": record.get("fenomeno"),
                "idioma": record.get("idioma"),
            }
        )

    return {"query_id": "q001", "query": question, "documents": documents, "fragments": fragments}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recuperacion BGE-M3 con recall top-50, reranking y MMR top-10."
    )
    parser.add_argument("--query", help="Ejecuta una sola pregunta y termina.")
    parser.add_argument(
        "--recall-top-k",
        type=int,
        default=DEFAULT_RECALL_TOP_K,
        help="Cantidad de candidatos solicitados a FAISS antes de aplicar filtros (por defecto: 50).",
    )
    parser.add_argument(
        "--output-top-k",
        type=int,
        default=DEFAULT_OUTPUT_TOP_K,
        help="Cantidad maxima de fragmentos expuestos en la respuesta (por defecto: 10).",
    )
    parser.add_argument("--model", default=MODEL_NAME, help="Encoder para codificar la consulta.")
    parser.add_argument(
        "--reranker-model",
        default=RERANKER_MODEL_NAME,
        help="Cross-encoder para reordenar el pool filtrado.",
    )
    parser.add_argument(
        "--mmr-lambda",
        type=float,
        default=DEFAULT_MMR_LAMBDA,
        help="Balance MMR entre relevancia y diversidad (0 a 1; por defecto: 0.7).",
    )
    parser.add_argument("--device", default=None)
    parser.add_argument("--index", type=Path, default=DATA / "index.faiss")
    parser.add_argument("--metadata", type=Path, default=DATA / "metadata.jsonl")
    parser.add_argument("--output-json", type=Path, default=FOLDER / "resultado_v2.json")
    parser.add_argument("--output", type=Path, help="Guarda cada respuesta como una linea JSONL.")
    parser.add_argument("--threshold", type=float, default=-1.0)
    parser.add_argument("--fenomeno", type=int, choices=(1, 2, 3))
    parser.add_argument("--idioma", help="Filtro opcional: es, en o pt.")
    parser.add_argument("--formato", help="Filtro opcional: pdf, json, csv, txt, etc.")
    args = parser.parse_args()

    if args.recall_top_k < 1:
        raise ValueError("--recall-top-k debe ser mayor que cero.")
    if args.output_top_k < 1:
        raise ValueError("--output-top-k debe ser mayor que cero.")
    if not 0.0 <= args.mmr_lambda <= 1.0:
        raise ValueError("--mmr-lambda debe estar entre 0 y 1.")
    if not args.index.exists() or not args.metadata.exists():
        raise FileNotFoundError("No existe el indice o la metadata de esta configuracion.")

    index = faiss.read_index(str(args.index))
    records = read_metadata(args.metadata)
    if index.ntotal != len(records):
        raise ValueError("El indice y la metadata no tienen la misma cantidad de registros.")

    model = SentenceTransformer(args.model, device=args.device)
    reranker = CrossEncoder(args.reranker_model, device=args.device)
    questions = [args.query] if args.query else iter(lambda: input("Pregunta> "), "salir")
    output_handle = args.output.open("w", encoding="utf-8") if args.output else None
    results = []
    try:
        for number, question in enumerate(questions, 1):
            result = retrieve(question, model, reranker, index, records, args)
            result["query_id"] = f"q{number:03d}"
            results.append(result)
            print(json.dumps(result, ensure_ascii=False))
            if output_handle:
                output_handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                output_handle.flush()
    except EOFError:
        pass
    finally:
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
