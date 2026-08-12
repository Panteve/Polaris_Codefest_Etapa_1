"""Recuperacion V2 independiente para BGE-M3 de PDF semantico."""

from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any
import faiss
from sentence_transformers import CrossEncoder, SentenceTransformer

MODEL_NAME = "BAAI/bge-m3"
RERANKER_NAME = "BAAI/bge-reranker-v2-m3"
FOLDER = Path(__file__).resolve().parent

def read_metadata(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict): raise ValueError(f"Metadata invalida: {path}:{number}")
                records.append(value)
    return records

def allowed(record, score, args):
    return score >= args.threshold and (args.fenomeno is None or str(record.get("fenomeno")) == str(args.fenomeno)) and (not args.idioma or str(record.get("idioma", "")).lower() == args.idioma.lower()) and (not args.formato or str(record.get("formato", "")).lower() == args.formato.lower())

def mmr(question, candidates, encoder, reranker, args):
    texts = [record.get("texto", "") for _, _, record in candidates]
    scores = [float(value) for value in reranker.predict([(question, text) for text in texts], show_progress_bar=False)]
    low, high = min(scores), max(scores)
    relevance = [1.0] * len(scores) if low == high else [(value - low) / (high - low) for value in scores]
    vectors = encoder.encode(texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
    ranked = sorted(range(len(candidates)), key=lambda i: (-scores[i], candidates[i][0]))
    selected, remaining = [], set(ranked)
    while remaining and len(selected) < args.output_top_k:
        best = max(remaining, key=lambda i: (args.mmr_lambda * relevance[i] - (1 - args.mmr_lambda) * (max(float(vectors[i] @ vectors[j]) for j in selected) if selected else 0.0), -ranked.index(i)))
        selected.append(best); remaining.remove(best)
    return [(scores[i], candidates[i][2]) for i in selected]

def retrieve(question, encoder, reranker, index, records, args):
    if not question.strip(): raise ValueError("La pregunta no puede estar vacia.")
    vector = encoder.encode([question], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False).astype("float32")
    scores, positions = index.search(vector, min(args.recall_top_k, index.ntotal))
    candidates = [(rank, float(score), records[int(position)]) for rank, (score, position) in enumerate(zip(scores[0], positions[0]), 1) if 0 <= position < len(records) and allowed(records[int(position)], float(score), args)]
    final = mmr(question, candidates, encoder, reranker, args) if candidates else []
    grouped = {}
    for score, record in final: grouped.setdefault(record.get("doc_id"), []).append(score)
    docs = sorted(grouped, key=lambda doc: -sum(grouped[doc]) / len(grouped[doc]))[:3]
    documents = [{"rank": rank, "doc_id": doc, "score": sum(grouped[doc]) / len(grouped[doc])} for rank, doc in enumerate(docs, 1)]
    fragments = [{"rank": rank, "chunk_id": record.get("chunk_id"), "doc_id": record.get("doc_id"), "text": record.get("texto", ""), "score": score, "fuente": record.get("fuente"), "fenomeno": record.get("fenomeno"), "idioma": record.get("idioma")} for rank, (score, record) in enumerate(final, 1)]
    return {"query_id": "q001", "query": question, "documents": documents, "fragments": fragments}

def main():
    parser = argparse.ArgumentParser(description="Recuperacion BGE-M3 PDF semantico V2 independiente.")
    parser.add_argument("--query"); parser.add_argument("--recall-top-k", type=int, default=50); parser.add_argument("--output-top-k", type=int, default=10); parser.add_argument("--model", default=MODEL_NAME); parser.add_argument("--reranker-model", default=RERANKER_NAME); parser.add_argument("--mmr-lambda", type=float, default=0.7); parser.add_argument("--device", default=None); parser.add_argument("--index", type=Path, default=FOLDER / "index.faiss"); parser.add_argument("--metadata", type=Path, default=FOLDER / "metadata.jsonl"); parser.add_argument("--output-json", type=Path, default=FOLDER / "resultado_v2.json"); parser.add_argument("--output", type=Path); parser.add_argument("--threshold", type=float, default=-1.0); parser.add_argument("--fenomeno", type=int, choices=(1, 2, 3)); parser.add_argument("--idioma"); parser.add_argument("--formato")
    args = parser.parse_args()
    if args.recall_top_k < 1 or args.output_top_k < 1 or not 0 <= args.mmr_lambda <= 1: raise ValueError("Parametros invalidos.")
    if not args.index.exists() or not args.metadata.exists(): raise FileNotFoundError("No existe el indice o la metadata.")
    index, records = faiss.read_index(str(args.index)), read_metadata(args.metadata)
    if index.ntotal != len(records): raise ValueError("El indice y la metadata no coinciden.")
    encoder, reranker = SentenceTransformer(args.model, device=args.device), CrossEncoder(args.reranker_model, device=args.device)
    questions = [args.query] if args.query else iter(lambda: input("Pregunta> "), "salir"); output_handle = args.output.open("w", encoding="utf-8") if args.output else None; results = []
    try:
        for number, question in enumerate(questions, 1):
            result = retrieve(question, encoder, reranker, index, records, args); result["query_id"] = f"q{number:03d}"; results.append(result); print(json.dumps(result, ensure_ascii=False))
            if output_handle: output_handle.write(json.dumps(result, ensure_ascii=False) + "\n")
    except EOFError: pass
    finally:
        if output_handle: output_handle.close()
    args.output_json.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    try: main()
    except (FileNotFoundError, ValueError, ImportError, json.JSONDecodeError) as exc: print(f"Error: {exc}", file=sys.stderr); raise SystemExit(1)
