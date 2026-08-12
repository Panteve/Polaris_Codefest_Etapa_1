"""Celda completa de Kaggle para ejecutar la recuperacion V3 del corpus 04.

Copiar y pegar todo este archivo en una celda de Kaggle. Los datasets deben
estar adjuntos y montados bajo /kaggle/input.
"""

# Instalar dependencias en Kaggle si hacen falta:
# #pip install -q faiss-cpu sentence-transformers
#
# Si Kaggle solicita reiniciar el kernel después de instalar, reinícialo y
# vuelve a ejecutar esta misma celda.

from __future__ import annotations

import json
from pathlib import Path

import faiss
from sentence_transformers import CrossEncoder, SentenceTransformer


# Configuracion editable desde la celda.
KAGGLE_INPUT = Path("/kaggle/input")
KAGGLE_OUTPUT = Path("/kaggle/working")
DATASET_HINT = "04_bge_m3_overlap_1"
RECALL_TOP_K = 100
OUTPUT_TOP_K = 10
RERANK_BATCH_SIZE = 8
MMR_LAMBDA = 0.7
NEAR_DUPLICATE_THRESHOLD = 0.90
MODEL_NAME = "BAAI/bge-m3"
RERANKER_NAME = "BAAI/bge-reranker-v2-m3"
QUESTIONS_FILENAME = "ground_truth_15_preguntas.json"


def find_files(filename: str) -> list[Path]:
    return sorted(path for path in KAGGLE_INPUT.rglob(filename) if path.is_file())


def select_index_metadata() -> tuple[Path, Path]:
    indexes = find_files("index.faiss")
    metadatas = find_files("metadata.jsonl")
    pairs = [
        (index_path, metadata_path)
        for index_path in indexes
        for metadata_path in metadatas
        if index_path.parent == metadata_path.parent
    ]
    print(f"Parejas index/metadata encontradas: {len(pairs)}")
    for number, (index_path, metadata_path) in enumerate(pairs, 1):
        print(f"[{number}] index={index_path}")
        print(f"    metadata={metadata_path}")
    if not pairs:
        raise FileNotFoundError("No se encontró index.faiss junto a metadata.jsonl.")
    preferred = [
        pair for pair in pairs if DATASET_HINT.casefold() in str(pair[0].parent).casefold()
    ]
    if preferred:
        print(f"Seleccionando la pareja que coincide con: {DATASET_HINT}")
        return preferred[0]
    print("No se encontró coincidencia por nombre; se seleccionará la primera pareja.")
    return pairs[0]


def select_questions() -> Path:
    questions = find_files(QUESTIONS_FILENAME)
    if not questions:
        questions = find_files("ground_truth_15_preguntas.json")
    if not questions:
        raise FileNotFoundError(f"No se encontró {QUESTIONS_FILENAME} en /kaggle/input.")
    print(f"Preguntas: {questions[0]}")
    return questions[0]


def read_metadata(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"Metadata invalida en la linea {line_number}.")
                records.append(value)
    return records


def read_questions(path: Path) -> list[tuple[str, str]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("El archivo de preguntas debe ser un arreglo JSON.")
    result = []
    for number, item in enumerate(value, 1):
        if isinstance(item, str):
            result.append((f"q{number:03d}", item))
        elif isinstance(item, dict) and isinstance(item.get("query"), str):
            result.append((str(item.get("query_id", f"q{number:03d}")), item["query"]))
        else:
            raise ValueError(f"La pregunta {number} no tiene un campo query valido.")
    return result


def normalize(values: list[float]) -> list[float]:
    low, high = min(values), max(values)
    return [1.0] * len(values) if low == high else [(value - low) / (high - low) for value in values]


def text_key(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def rerank_chunks(question, texts, reranker, question_number, total_questions):
    scores = []
    total = len(texts)
    for start in range(0, total, RERANK_BATCH_SIZE):
        batch = texts[start:start + RERANK_BATCH_SIZE]
        scores.extend(
            float(value)
            for value in reranker.predict(
                [(question, text) for text in batch], show_progress_bar=False
            )
        )
        processed = min(start + len(batch), total)
        print(
            f"Pregunta {question_number}/{total_questions} - reranking chunks: "
            f"{int(processed * 100 / total)}% ({processed}/{total})",
            flush=True,
        )
    return scores


def encode_chunks(texts, encoder, question_number, total_questions):
    vectors = []
    total = len(texts)
    for start in range(0, total, RERANK_BATCH_SIZE):
        batch = texts[start:start + RERANK_BATCH_SIZE]
        vectors.extend(
            encoder.encode(
                batch,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        )
        processed = min(start + len(batch), total)
        print(
            f"Pregunta {question_number}/{total_questions} - embeddings MMR: "
            f"{int(processed * 100 / total)}% ({processed}/{total})",
            flush=True,
        )
    return vectors


def retrieve(question, question_number, total_questions, encoder, reranker, index, records):
    print(f"Pregunta {question_number}/{total_questions} - inicio: 0%", flush=True)
    query_vector = encoder.encode(
        [question], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False
    ).astype("float32")
    scores, positions = index.search(query_vector, min(RECALL_TOP_K, index.ntotal))
    print(f"Pregunta {question_number}/{total_questions} - recall FAISS: 25%", flush=True)

    candidates = [
        (rank, float(score), records[int(position)])
        for rank, (score, position) in enumerate(zip(scores[0], positions[0]), 1)
        if 0 <= position < len(records)
    ]
    print(f"Pregunta {question_number}/{total_questions} - filtros: 40%", flush=True)

    if not candidates:
        return {"query_id": "q001", "query": question, "documents": [], "fragments": []}

    texts = [record.get("texto", "") for _, _, record in candidates]
    rerank_scores = rerank_chunks(question, texts, reranker, question_number, total_questions)
    vectors = encode_chunks(texts, encoder, question_number, total_questions)
    scored = [
        (rerank_scores[index], (candidates[index][0], candidates[index][2]), vectors[index])
        for index in range(len(candidates))
    ]
    print(f"Pregunta {question_number}/{total_questions} - reranking: 60%", flush=True)

    # Deduplicacion exacta y semantica. Se conserva el score mas alto.
    order = sorted(range(len(scored)), key=lambda i: (-scored[i][0], scored[i][1][0]))
    kept = []
    exact_keys = set()
    for index in order:
        score, (_, record), vector = scored[index]
        chunk_id = record.get("chunk_id")
        normalized_text = text_key(record.get("texto", ""))
        if chunk_id in exact_keys or (normalized_text and normalized_text in exact_keys):
            continue
        if any(float(vector @ scored[other][2]) >= NEAR_DUPLICATE_THRESHOLD for other in kept):
            continue
        kept.append(index)
        if chunk_id is not None:
            exact_keys.add(chunk_id)
        if normalized_text:
            exact_keys.add(normalized_text)
    print(f"Pregunta {question_number}/{total_questions} - deduplicacion: 75%", flush=True)

    unique = [scored[index] for index in kept]
    relevance = normalize([item[0] for item in unique]) if unique else []
    ranked = sorted(range(len(unique)), key=lambda i: (-unique[i][0], unique[i][1][0]))
    selected = []
    remaining = set(ranked)
    while remaining and len(selected) < OUTPUT_TOP_K:
        best = max(
            remaining,
            key=lambda i: (
                MMR_LAMBDA * relevance[i]
                - (1 - MMR_LAMBDA)
                * (
                    max(float(unique[i][2] @ unique[j][2]) for j in selected)
                    if selected
                    else 0.0
                ),
                -ranked.index(i),
            ),
        )
        selected.append(best)
        remaining.remove(best)
    print(f"Pregunta {question_number}/{total_questions} - MMR: 90%", flush=True)

    final = [(unique[index][0], unique[index][1][1]) for index in selected]
    grouped = {}
    for score, record in final:
        grouped.setdefault(record.get("doc_id"), []).append(score)
    document_ids = sorted(grouped, key=lambda doc: -sum(grouped[doc]) / len(grouped[doc]))[:3]
    documents = [
        {"rank": rank, "doc_id": doc_id, "score": sum(grouped[doc_id]) / len(grouped[doc_id])}
        for rank, doc_id in enumerate(document_ids, 1)
    ]
    fragments = [
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
        for rank, (score, record) in enumerate(final, 1)
    ]
    print(f"Pregunta {question_number}/{total_questions} - resultado listo: 100%", flush=True)
    return {"query_id": "q001", "query": question, "documents": documents, "fragments": fragments}


def main():
    index_path, metadata_path = select_index_metadata()
    questions_path = select_questions()
    records = read_metadata(metadata_path)
    questions = read_questions(questions_path)
    index = faiss.read_index(str(index_path))
    if index.ntotal != len(records):
        raise ValueError("El indice FAISS y metadata.jsonl no tienen la misma cantidad de registros.")

    print(f"Modelo encoder: {MODEL_NAME}")
    print(f"Modelo reranker: {RERANKER_NAME}")
    print(f"Recall: {RECALL_TOP_K}; salida: {OUTPUT_TOP_K}; preguntas: {len(questions)}")
    print("Cargando modelos...")
    encoder = SentenceTransformer(MODEL_NAME)
    reranker = CrossEncoder(RERANKER_NAME)
    print("Modelos cargados.")

    results = []
    for question_number, (query_id, question) in enumerate(questions, 1):
        result = retrieve(question, question_number, len(questions), encoder, reranker, index, records)
        result["query_id"] = query_id
        results.append(result)

    output_path = KAGGLE_OUTPUT / "resultado_v3_preguntas.json"
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Resultado guardado en: {output_path}")


main()
