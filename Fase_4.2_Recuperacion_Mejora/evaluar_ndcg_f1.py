"""Evalúa resultados V3 con NDCG@10 para fragmentos y F1@3 para documentos.

El matching sigue la documentación técnica del reto:

* Fragmentos: una cita de ground truth coincide si aparece como substring
  exacto dentro de ``fragments[].text``. ``chunk_id`` no participa.
* Documentos: una fuente coincide por ``fuente``. Si V3 solo entrega
  ``doc_id`` en ``documents``, se resuelve mediante ``fuente`` de los
  fragmentos recuperados o mediante un metadata.jsonl opcional.

No requiere dependencias externas.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


def load_json_or_jsonl(path: Path) -> list[dict[str, Any]]:
    """Carga un arreglo JSON, un objeto JSON único o JSON Lines."""
    raw = path.read_text(encoding="utf-8-sig")
    if not raw.strip():
        return []

    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(raw.splitlines(), 1):
            if not line.strip():
                continue
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError(f"{path}:{line_number} no contiene un objeto JSON.")
            records.append(item)
        return records

    if isinstance(value, dict):
        return [value]
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return value
    raise ValueError(f"El archivo {path} debe contener objetos JSON.")


def load_metadata_sources(path: Path | None) -> dict[str, set[str]]:
    """Construye doc_id -> conjunto de fuentes desde metadata JSON/JSONL."""
    if path is None:
        return {}

    records = load_json_or_jsonl(path)
    mapping: dict[str, set[str]] = defaultdict(set)
    for record in records:
        doc_id = record.get("doc_id")
        fuente = record.get("fuente")
        if doc_id is not None and fuente:
            mapping[str(doc_id)].add(str(fuente))
    return dict(mapping)


def ranked_items(value: Any) -> list[dict[str, Any]]:
    """Versión simplificada de as_ranked_items sin exponer índices internos."""
    if not isinstance(value, list):
        return []
    items = [item for item in value if isinstance(item, dict)]
    if any(isinstance(item.get("rank"), (int, float)) for item in items):
        items = sorted(
            items,
            key=lambda item: item.get("rank")
            if isinstance(item.get("rank"), (int, float))
            else float("inf"),
        )
    return items


def fragment_text(fragment: dict[str, Any]) -> str:
    """Obtiene text; acepta texto como fallback para variantes internas."""
    value = fragment.get("text")
    if value is None:
        value = fragment.get("texto")
    return str(value or "")


def relevance_gain(fragment: dict[str, Any]) -> float:
    """Soporta ground truths binarias y futuras etiquetas alta/media."""
    label = fragment.get("relevancia", fragment.get("relevance"))
    if isinstance(label, str):
        label = label.lower().strip()
        if label == "alta":
            return 2.0
        if label == "media":
            return 1.0
    return 1.0


def unique_ground_truth_fragments(query: dict[str, Any]) -> list[dict[str, Any]]:
    ground_truth = query.get("ground_truth")
    if not isinstance(ground_truth, dict):
        return []
    fragments = ground_truth.get("fragmentos_relevantes")
    if not isinstance(fragments, list):
        return []

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fragment in fragments:
        if not isinstance(fragment, dict):
            continue
        text = str(fragment.get("texto_verbatim") or "")
        if text and text not in seen:
            result.append(fragment)
            seen.add(text)
    return result


def ndcg_at_10(
    query: dict[str, Any], result: dict[str, Any] | None
) -> tuple[float, list[dict[str, Any]]]:
    """Calcula NDCG@10 con matching exacto GT-text dentro de result-text.

    Cada resultado recuperado puede cubrir como máximo una posición de gain.
    Si un texto recuperado contiene varias citas GT, se registra la mejor y se
    evita contar dos veces el mismo resultado. Las citas cubiertas por ese
    resultado tampoco vuelven a generar gain en posiciones posteriores.
    """
    ground_truth = unique_ground_truth_fragments(query)
    if not ground_truth:
        return 0.0, []

    gains_ideal = sorted(
        (relevance_gain(fragment) for fragment in ground_truth), reverse=True
    )[:10]
    idcg = sum(gain / math.log2(rank + 2) for rank, gain in enumerate(gains_ideal))
    if idcg == 0:
        return 0.0, []

    ranked_fragments = ranked_items((result or {}).get("fragments"))[:10]
    remaining = set(range(len(ground_truth)))
    dcg = 0.0
    matches: list[dict[str, Any]] = []

    for position, fragment in enumerate(ranked_fragments, 1):
        text = fragment_text(fragment)
        matched_indices = [
            index for index in remaining if ground_truth[index].get("texto_verbatim") in text
        ]
        gain = max(
            (relevance_gain(ground_truth[index]) for index in matched_indices),
            default=0.0,
        )
        if matched_indices:
            remaining.difference_update(matched_indices)

        dcg += gain / math.log2(position + 1)
        matches.append(
            {
                "rank": position,
                "gain": gain,
                "matched": bool(matched_indices),
                "matched_ground_truth_indices": matched_indices,
                "returned_text": text,
            }
        )

    return dcg / idcg, matches


def ground_truth_sources(query: dict[str, Any]) -> set[str]:
    ground_truth = query.get("ground_truth")
    if not isinstance(ground_truth, dict):
        return set()
    documents = ground_truth.get("documentos_relevantes")
    if not isinstance(documents, list):
        return set()
    return {
        str(item.get("fuente"))
        for item in documents
        if isinstance(item, dict) and item.get("fuente")
    }


def result_fragment_source_map(result: dict[str, Any] | None) -> dict[str, set[str]]:
    """Mapea doc_id a fuentes observadas en los fragments de V3."""
    mapping: dict[str, set[str]] = defaultdict(set)
    if not result:
        return {}
    for fragment in ranked_items(result.get("fragments")):
        doc_id = fragment.get("doc_id")
        fuente = fragment.get("fuente")
        if doc_id is not None and fuente:
            mapping[str(doc_id)].add(str(fuente))
    return dict(mapping)


def predicted_sources(
    result: dict[str, Any] | None, metadata_sources: dict[str, set[str]]
) -> tuple[list[str], list[str]]:
    """Obtiene top-3 fuentes; devuelve también doc_ids sin fuente resoluble."""
    if not result:
        return [], []

    from_fragments = result_fragment_source_map(result)
    sources: list[str] = []
    unresolved: list[str] = []
    documents = ranked_items(result.get("documents"))[:3]

    if not documents:
        documents = []
        seen_docs: set[str] = set()
        for fragment in ranked_items(result.get("fragments")):
            doc_id = fragment.get("doc_id")
            if doc_id is not None and str(doc_id) not in seen_docs:
                documents.append({"doc_id": doc_id})
                seen_docs.add(str(doc_id))
            if len(documents) == 3:
                break

    for document in documents:
        direct_source = document.get("fuente", document.get("source"))
        resolved: set[str] = set()
        if direct_source:
            resolved.add(str(direct_source))
        doc_id = document.get("doc_id")
        if doc_id is not None:
            key = str(doc_id)
            resolved.update(from_fragments.get(key, set()))
            resolved.update(metadata_sources.get(key, set()))
        if resolved:
            for source in sorted(resolved):
                if source not in sources:
                    sources.append(source)
        elif doc_id is not None:
            unresolved.append(str(doc_id))

    return sources, unresolved


def f1_at_3(
    query: dict[str, Any], result: dict[str, Any] | None, metadata_sources: dict[str, set[str]]
) -> tuple[float, dict[str, Any]]:
    relevant = ground_truth_sources(query)
    predicted, unresolved = predicted_sources(result, metadata_sources)
    predicted_set = set(predicted)
    overlap = sorted(predicted_set & relevant)

    # La especificación define P@3 con denominador 3, aunque el resultado
    # contenga menos de tres documentos.
    precision = len(overlap) / 3.0
    recall_denominator = min(len(relevant), 3)
    recall = len(overlap) / recall_denominator if recall_denominator else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return f1, {
        "predicted_sources": predicted,
        "relevant_sources": sorted(relevant),
        "overlap_sources": overlap,
        "unresolved_doc_ids": unresolved,
        "precision_at_3": precision,
        "recall_at_3": recall,
        "f1_at_3": f1,
    }


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def grouped_summary(records: list[dict[str, Any]], field: str) -> dict[str, dict[str, float]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record.get(field, "sin_dato"))].append(record)
    return {
        key: {
            "queries": len(values),
            "ndcg_at_10": mean(item["ndcg_at_10"] for item in values),
            "f1_at_3": mean(item["f1_at_3"] for item in values),
        }
        for key, values in sorted(groups.items())
    }


def evaluate(
    ground_truth: list[dict[str, Any]],
    results: list[dict[str, Any]],
    metadata_sources: dict[str, set[str]],
) -> dict[str, Any]:
    results_by_id = {
        str(item.get("query_id")): item
        for item in results
        if item.get("query_id") is not None
    }
    expected_ids = [
        str(query.get("query_id", f"qa{index:03d}"))
        for index, query in enumerate(ground_truth, 1)
    ]
    # V3 conserva query_id cuando recibe --questions. Este fallback permite
    # evaluar también salidas antiguas q001/q002/... si tienen la misma
    # cantidad y el mismo orden que el ground truth.
    if not set(expected_ids) & set(results_by_id) and len(results) == len(expected_ids):
        results_by_id = dict(zip(expected_ids, results))

    per_query: list[dict[str, Any]] = []
    for index, query in enumerate(ground_truth, 1):
        query_id = str(query.get("query_id", f"qa{index:03d}"))
        result = results_by_id.get(query_id)
        ndcg, fragment_matches = ndcg_at_10(query, result)
        f1, document_detail = f1_at_3(query, result, metadata_sources)
        per_query.append(
            {
                "query_id": query_id,
                "query": query.get("query", ""),
                "fenomeno": query.get("fenomeno"),
                "tipo": query.get("tipo"),
                "result_found": result is not None,
                "ndcg_at_10": ndcg,
                "f1_at_3": f1,
                "fragment_matches": fragment_matches,
                **document_detail,
            }
        )

    return {
        "metric_definition": {
            "ndcg_at_10": "Substring exacto de cada texto_verbatim dentro de fragments[].text; chunk_id ignorado.",
            "f1_at_3": "Intersección entre documentos top-3 y fuentes ground truth; doc_id resuelto a fuente.",
            "precision_at_3_denominator": 3,
            "recall_at_3_denominator": "min(numero_fuentes_relevantes, 3)",
        },
        "summary": {
            "queries_ground_truth": len(ground_truth),
            "queries_with_results": sum(item["result_found"] for item in per_query),
            "ndcg_at_10": mean(item["ndcg_at_10"] for item in per_query),
            "f1_at_3": mean(item["f1_at_3"] for item in per_query),
        },
        "by_fenomeno": grouped_summary(per_query, "fenomeno"),
        "by_tipo": grouped_summary(per_query, "tipo"),
        "per_query": per_query,
    }


def write_csv(path: Path, report: dict[str, Any]) -> None:
    rows = report["per_query"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "query_id",
                "fenomeno",
                "tipo",
                "result_found",
                "ndcg_at_10",
                "f1_at_3",
                "precision_at_3",
                "recall_at_3",
                "predicted_sources",
                "relevant_sources",
                "overlap_sources",
                "unresolved_doc_ids",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "query_id": row["query_id"],
                    "fenomeno": row["fenomeno"],
                    "tipo": row["tipo"],
                    "result_found": row["result_found"],
                    "ndcg_at_10": row["ndcg_at_10"],
                    "f1_at_3": row["f1_at_3"],
                    "precision_at_3": row["precision_at_3"],
                    "recall_at_3": row["recall_at_3"],
                    "predicted_sources": " | ".join(row["predicted_sources"]),
                    "relevant_sources": " | ".join(row["relevant_sources"]),
                    "overlap_sources": " | ".join(row["overlap_sources"]),
                    "unresolved_doc_ids": " | ".join(row["unresolved_doc_ids"]),
                }
            )


def print_summary(report: dict[str, Any], output: Path) -> None:
    summary = report["summary"]
    print(f"Consultas ground truth: {summary['queries_ground_truth']}")
    print(f"Consultas con resultados: {summary['queries_with_results']}")
    print(f"NDCG@10: {summary['ndcg_at_10']:.6f}")
    print(f"F1@3: {summary['f1_at_3']:.6f}")
    print(f"Reporte: {output}")


def find_default_ground_truth(root: Path) -> Path | None:
    candidates = [
        root / "Validacion_20_Preguntas" / "ground_truth_15_preguntas.json",
        root / "Validacion_20_Preguntas" / "ground_truth.json",
    ]
    candidates.extend(sorted(root.glob("ground_truth*.json")))
    return next((path for path in candidates if path.is_file()), None)


def is_configuration_directory(path: Path) -> bool:
    return path.is_dir() and path.name not in {"Validacion_20_Preguntas", "public", "__pycache__"} and re.fullmatch(r"[A-Za-z0-9_-]+", path.name) is not None


def result_files_in(configuration: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in configuration.iterdir()
            if path.is_file() and re.fullmatch(r"(?:resultado|resultados)(?:_.*)?\.json", path.name, re.IGNORECASE)
        ),
        key=lambda path: path.name.lower(),
    )


def metadata_file_in(configuration: Path) -> Path | None:
    exact = configuration / "metadata.jsonl"
    if exact.is_file():
        return exact
    return next(iter(sorted(configuration.glob("metadata*.jsonl"))), None)


def evaluate_all(root: Path, ground_truth_path: Path, write_csv_files: bool = True) -> int:
    """Evalúa cada resultado*.json encontrado en cada configuración."""
    ground_truth = load_json_or_jsonl(ground_truth_path)
    configurations = sorted((path for path in root.iterdir() if is_configuration_directory(path)), key=lambda path: path.name)
    evaluated = 0
    failures = 0

    for configuration in configurations:
        results_paths = result_files_in(configuration)
        if not results_paths:
            print(f"[OMITIDA] {configuration.name}: no se encontró resultado*.json")
            continue
        metadata_path = metadata_file_in(configuration)
        metadata_sources = load_metadata_sources(metadata_path)
        for results_path in results_paths:
            output_path = configuration / f"evaluacion_{results_path.stem}.json"
            csv_path = configuration / f"evaluacion_{results_path.stem}.csv"
            try:
                report = evaluate(ground_truth, load_json_or_jsonl(results_path), metadata_sources)
                output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                if write_csv_files:
                    write_csv(csv_path, report)
                print(f"\n[{configuration.name}] {results_path.name}")
                print_summary(report, output_path)
                if metadata_path:
                    print(f"Metadata: {metadata_path}")
                evaluated += 1
            except (OSError, ValueError, json.JSONDecodeError) as error:
                print(f"[ERROR] {configuration.name}/{results_path.name}: {error}")
                failures += 1

    print(f"\nEvaluaciones completadas: {evaluated}")
    if failures:
        print(f"Evaluaciones con error: {failures}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evalua resultados V3 con NDCG@10 y F1@3 según la especificación del reto."
    )
    parser.add_argument("--auto", action="store_true", help="Recorre todas las configuraciones y evalúa cada resultado*.json.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent, help="Carpeta raíz de la fase para --auto.")
    parser.add_argument("--ground-truth", type=Path, help="Ground truth para la evaluación manual o automática.")
    parser.add_argument("--results", type=Path, help="JSON de resultados para la evaluación manual.")
    parser.add_argument(
        "--metadata",
        type=Path,
        help="metadata.jsonl opcional para resolver doc_id -> fuente.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluacion_ndcg_f1.json"),
    )
    parser.add_argument("--csv", type=Path, help="CSV opcional con métricas por consulta.")
    parser.add_argument("--no-csv", action="store_true", help="En --auto, no genera el CSV por carpeta.")
    args = parser.parse_args()

    if args.auto:
        root = args.root.resolve()
        ground_truth_path = args.ground_truth or find_default_ground_truth(root)
        if ground_truth_path is None or not ground_truth_path.is_file():
            parser.error("--auto no encontró un ground truth. Usa --ground-truth para indicar su ruta.")
        print(f"Ground truth: {ground_truth_path}")
        return evaluate_all(root, ground_truth_path, write_csv_files=not args.no_csv)

    if args.ground_truth is None or args.results is None:
        parser.error("La evaluación manual requiere --ground-truth y --results, o usa --auto.")

    ground_truth = load_json_or_jsonl(args.ground_truth)
    results = load_json_or_jsonl(args.results)
    metadata_sources = load_metadata_sources(args.metadata)
    report = evaluate(ground_truth, results, metadata_sources)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        write_csv(args.csv, report)

    print_summary(report, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
