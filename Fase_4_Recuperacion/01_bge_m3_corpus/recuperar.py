"""Consulta interactiva del índice FAISS BGE-M3 de la Fase 3."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import faiss
from sentence_transformers import SentenceTransformer


MODEL_NAME = "BAAI/bge-m3"
MAX_WORDS_PER_FRAGMENT = 250
DISPLAY_FRAGMENTS = 10
MEAN_TOP_CHUNKS = 3


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON inválido en {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Se esperaba un objeto JSON en {path}:{line_number}.")
            records.append(value)
    return records


def shorten_text(text: str, limit: int = MAX_WORDS_PER_FRAGMENT) -> str:
    """Limita la salida a 250 palabras sin alterar la metadata en disco."""
    words = str(text).split()
    if len(words) <= limit:
        return " ".join(words)
    return " ".join(words[:limit]).rstrip(" ,;:") + "…"


def matching(record: dict[str, Any], args: argparse.Namespace) -> bool:
    if args.fenomeno is not None and str(record.get("fenomeno")) != str(args.fenomeno):
        return False
    if args.idioma and str(record.get("idioma", "")).lower() != args.idioma.lower():
        return False
    if args.formato and str(record.get("formato", "")).lower() != args.formato.lower():
        return False
    return True


def retrieve(
    question: str,
    model: SentenceTransformer,
    index: faiss.Index,
    records: list[dict[str, Any]],
    args: argparse.Namespace,
    query_id: str,
) -> dict[str, Any]:
    if not question.strip():
        raise ValueError("La pregunta no puede estar vacía.")

    vector = model.encode(
        [question],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).astype("float32")

    candidate_count = min(index.ntotal, max(args.candidate_chunks, DISPLAY_FRAGMENTS))
    scores, positions = index.search(vector, candidate_count)
    chunks: list[dict[str, Any]] = []
    for score, position in zip(scores[0], positions[0]):
        if position < 0 or position >= len(records):
            continue
        record = records[int(position)]
        if not matching(record, args) or float(score) < args.threshold:
            continue
        chunks.append({
            "score": float(score),
            "position": int(position),
            "record": record,
        })
        if len(chunks) == args.candidate_chunks:
            break

    scores_by_document: dict[str, list[float]] = defaultdict(list)
    for item in chunks:
        doc_id = str(item["record"].get("doc_id", ""))
        scores_by_document[doc_id].append(item["score"])

    if args.doc_score == "sum":
        document_scores = {
            doc_id: sum(scores)
            for doc_id, scores in scores_by_document.items()
        }
    else:
        document_scores = {
            doc_id: sum(sorted(scores, reverse=True)[:MEAN_TOP_CHUNKS])
            / min(len(scores), MEAN_TOP_CHUNKS)
            for doc_id, scores in scores_by_document.items()
        }

    documents = [
        {"rank": rank, "doc_id": doc_id, "score": score}
        for rank, (doc_id, score) in enumerate(
            sorted(document_scores.items(), key=lambda item: item[1], reverse=True)[:3],
            1,
        )
    ]
    fragments = [
        {
            "rank": rank,
            "chunk_id": item["record"].get("chunk_id"),
            "doc_id": item["record"].get("doc_id"),
            "text": shorten_text(item["record"].get("texto", "")),
            "score": item["score"],
            "fuente": item["record"].get("fuente"),
            "fenomeno": item["record"].get("fenomeno"),
            "idioma": item["record"].get("idioma"),
        }
        for rank, item in enumerate(chunks[:DISPLAY_FRAGMENTS], 1)
    ]
    return {"query_id": query_id, "query": question, "documents": documents, "fragments": fragments}


def print_result(result: dict[str, Any]) -> None:
    print(f"\n{result['query_id']}: {result['query']}")
    print("\nDocumentos más relevantes:")
    if not result["documents"]:
        print("  No se encontraron documentos con los filtros indicados.")
    for item in result["documents"]:
        print(f"  {item['rank']}. {item['doc_id']}  (similitud: {item['score']:.4f})")
    print("\nFragmentos:")
    if not result["fragments"]:
        print("  No se encontraron fragmentos con los filtros indicados.")
    for item in result["fragments"]:
        print(f"\n  [{item['rank']}] {item['chunk_id']} | {item['fuente']} | {item['score']:.4f}")
        print(f"  {item['text']}")


def result_for_jsonl(result: dict[str, Any]) -> dict[str, Any]:
    """Devuelve el esquema de entrega, sin campos auxiliares de depuración."""
    return {
        "query_id": result["query_id"],
        "documents": [
            {"rank": item["rank"], "doc_id": item["doc_id"]}
            for item in result["documents"]
        ],
        "fragments": [
            {
                "rank": item["rank"],
                "chunk_id": item["chunk_id"],
                "doc_id": item["doc_id"],
                "text": item["text"],
            }
            for item in result["fragments"]
        ],
    }


def parse_args(
    default_doc_score: str | None = None,
    default_index: Path | None = None,
    default_metadata: Path | None = None,
    default_output: Path | None = None,
    default_model: str | None = None,
) -> argparse.Namespace:
    folder = Path(__file__).resolve().parent
    phase3 = folder.parents[1] / "Fase_3_Encoder" / "01_bge_m3_corpus"
    parser = argparse.ArgumentParser(description="Recuperación semántica con FAISS y BGE-M3.")
    parser.add_argument("--index", type=Path, default=default_index or phase3 / "index.faiss")
    parser.add_argument("--metadata", type=Path, default=default_metadata or phase3 / "metadata.jsonl")
    parser.add_argument("--model", default=default_model or MODEL_NAME)
    parser.add_argument("--device", default=None, help="Por ejemplo: cpu o cuda.")
    parser.add_argument("--query", help="Ejecuta una sola pregunta y termina.")
    parser.add_argument("--output", type=Path, help="Guarda cada respuesta como una línea JSONL.")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=default_output or folder / "resultados.json",
        help="Ruta del JSON normal; por defecto: resultados.json.",
    )
    parser.add_argument(
        "--candidate-chunks",
        type=int,
        default=20,
        help="Chunks candidatos para agrupar y puntuar documentos (por defecto: 20).",
    )
    parser.add_argument(
        "--doc-score",
        choices=("mean", "sum"),
        default=default_doc_score or "mean",
        help="Agregación de puntuaciones por documento (por defecto: mean).",
    )
    parser.add_argument("--threshold", type=float, default=-1.0)
    parser.add_argument("--fenomeno", type=int, choices=(1, 2, 3))
    parser.add_argument("--idioma", help="Filtro opcional: es, en o pt.")
    parser.add_argument("--formato", help="Filtro opcional: pdf, json, csv, txt, etc.")
    return parser.parse_args()


def main(
    default_doc_score: str | None = None,
    default_index: Path | None = None,
    default_metadata: Path | None = None,
    default_output: Path | None = None,
    default_model: str | None = None,
) -> None:
    args = parse_args(default_doc_score, default_index, default_metadata, default_output, default_model)
    if args.candidate_chunks < DISPLAY_FRAGMENTS:
        raise ValueError(
            f"--candidate-chunks debe ser como mínimo {DISPLAY_FRAGMENTS}, "
            "porque la salida siempre muestra 10 fragmentos."
        )
    if not args.index.exists():
        raise FileNotFoundError(f"No existe el índice FAISS: {args.index}")
    if not args.metadata.exists():
        raise FileNotFoundError(f"No existe la metadata: {args.metadata}")

    print(f"Cargando índice: {args.index}", flush=True)
    index = faiss.read_index(str(args.index))
    records = read_jsonl(args.metadata)
    if index.ntotal != len(records):
        raise ValueError(
            f"Desalineación: FAISS contiene {index.ntotal:,} vectores y "
            f"la metadata contiene {len(records):,} registros."
        )
    print(f"Cargando encoder: {args.model}", flush=True)
    model = SentenceTransformer(args.model, device=args.device)
    print(f"Listo: {index.ntotal:,} vectores. Escribe 'salir' para terminar.\n", flush=True)

    output_handle = args.output.open("w", encoding="utf-8") if args.output else None
    json_results: list[dict[str, Any]] = []
    try:
        questions = [args.query] if args.query else iter(lambda: input("Pregunta> "), "salir")
        for number, question in enumerate(questions, 1):
            result = retrieve(question, model, index, records, args, f"q{number:03d}")
            print_result(result)
            clean_result = result_for_jsonl(result)
            json_results.append(clean_result)
            if output_handle:
                output_handle.write(json.dumps(clean_result, ensure_ascii=False) + "\n")
                output_handle.flush()
    except EOFError:
        pass
    finally:
        if output_handle:
            output_handle.close()
        if args.output_json:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(
                json.dumps(json_results, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
