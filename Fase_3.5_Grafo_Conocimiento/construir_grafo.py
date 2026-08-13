"""Construye un grafo de conocimiento trazable desde metadata.jsonl.

Usa GLiNER2 para detectar entidades y relaciones semánticas. Cada mención y
cada relación conserva la evidencia del documento y del chunk de origen.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

import networkx as nx


ENTITY_TYPES = {
    "person": "Persona mencionada en el texto",
    "organization": "Organización, institución, organismo o empresa",
    "country": "País o Estado",
    "location": "Ciudad, región, lugar o zona geográfica",
    "technology": "Tecnología, sistema, modelo o capacidad técnica",
    "scientific concept": "Concepto científico o técnico",
    "space mission": "Misión, programa o vehículo espacial",
    "international treaty": "Tratado, acuerdo, convenio o norma internacional",
    "political event": "Evento político, diplomático o militar",
    "institution": "Institución académica, pública o internacional",
    "date": "Fecha o periodo temporal relevante",
}

RELATION_TYPES = {
    "develops": "Una organización o persona desarrolla una tecnología o programa",
    "uses": "Una entidad utiliza una tecnología, sistema o recurso",
    "located_in": "Una entidad está ubicada en un lugar",
    "participates_in": "Una entidad participa en un evento, programa o acuerdo",
    "regulates": "Una norma, institución u organización regula una entidad",
    "signed": "Una entidad firma un tratado o acuerdo",
    "cooperates_with": "Dos entidades cooperan o colaboran",
    "affects": "Una entidad, evento o fenómeno afecta a otra entidad",
    "related_to": "Relación temática explícita entre dos entidades",
}

REQUIRED = {"doc_id", "chunk_id", "fuente", "fenomeno"}


def text(value: Any, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()[:limit]


def node_key(kind: str, label: str) -> str:
    return f"{kind}:{text(label).casefold()}"


def add_node(g: nx.MultiDiGraph, node: str, kind: str, label: str, **attrs: Any) -> None:
    clean_attrs = {key: text(value) for key, value in attrs.items() if value is not None}
    clean_attrs.update(kind=kind, label=text(label))
    g.add_node(node, **clean_attrs)


def add_edge_once(g: nx.MultiDiGraph, source: str, target: str, **attrs: Any) -> None:
    relation = attrs.get("relation")
    for _, target_node, data in g.out_edges(source, data=True):
        if target_node == target and data.get("relation") == relation:
            return
    g.add_edge(source, target, **{key: text(value) for key, value in attrs.items()})


def load(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"No existe la metadata: {path}")

    rows: list[dict[str, Any]] = []
    seen_chunks: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON inválido en línea {number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"La línea {number} no contiene un objeto JSON.")

        missing = sorted(REQUIRED - set(row))
        if missing:
            raise ValueError(f"Línea {number}: faltan campos obligatorios: {', '.join(missing)}")
        doc_id = text(row.get("doc_id"))
        chunk_id = text(row.get("chunk_id"))
        body = row.get("texto") or row.get("text")
        if not doc_id or not chunk_id:
            raise ValueError(f"Línea {number}: doc_id y chunk_id no pueden estar vacíos.")
        if not chunk_id.startswith(f"{doc_id}-"):
            raise ValueError(f"Línea {number}: chunk_id no trazable a doc_id: {chunk_id}")
        if chunk_id in seen_chunks:
            raise ValueError(f"Línea {number}: chunk_id duplicado: {chunk_id}")
        if not body or not str(body).strip():
            raise ValueError(f"Línea {number}: el chunk {chunk_id} no tiene texto.")
        if str(row.get("fenomeno")) not in {"1", "2", "3"}:
            raise ValueError(f"Línea {number}: fenomeno debe ser 1, 2 o 3.")

        seen_chunks.add(chunk_id)
        rows.append(row)

    if not rows:
        raise ValueError("No hay registros con texto en la metadata.")
    return rows


def load_extractor(model_name: str, device: str = "auto"):
    try:
        from gliner2 import GLiNER2
    except ImportError as exc:
        raise RuntimeError(
            "Falta GLiNER2. Instala las dependencias con "
            "python -m pip install -r requirements-grafo.txt"
        ) from exc
    if device not in {"auto", "cpu", "cuda"}:
        raise ValueError("device debe ser auto, cpu o cuda")
    if device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
    if device == "cuda":
        try:
            import torch
            if not torch.cuda.is_available():
                raise RuntimeError("Se solicitó CUDA, pero no hay una GPU disponible.")
        except ImportError as exc:
            raise RuntimeError("Para usar CUDA se necesita PyTorch.") from exc
    print(f"Dispositivo de inferencia: {device.upper()}", flush=True)
    try:
        return GLiNER2.from_pretrained(model_name, map_location=device), device
    except Exception as exc:
        if device != "cuda":
            raise
        print(f"CUDA no pudo cargar el modelo ({exc}); cambiando a CPU.", flush=True)
        return GLiNER2.from_pretrained(model_name, map_location="cpu"), "cpu"


def extract(extractor: Any, body: str, threshold: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entity_result = extractor.extract_entities(
        body, ENTITY_TYPES, threshold=threshold,
        include_confidence=True, include_spans=True,
    )
    relation_result = extractor.extract_relations(
        body, RELATION_TYPES, threshold=threshold,
        include_confidence=True, include_spans=True,
    )

    entities: list[dict[str, Any]] = []
    for kind, values in entity_result.get("entities", {}).items():
        for value in values or []:
            item = dict(value) if isinstance(value, dict) else {"text": value}
            if item.get("text"):
                item["kind"] = kind
                entities.append(item)

    relations: list[dict[str, Any]] = []
    for relation, values in relation_result.get("relation_extraction", {}).items():
        for value in values or []:
            if isinstance(value, dict):
                head = value.get("head", {})
                tail = value.get("tail", {})
                item = {
                    "relation": relation,
                    "head": head.get("text", "") if isinstance(head, dict) else head,
                    "tail": tail.get("text", "") if isinstance(tail, dict) else tail,
                    "confidence": value.get("confidence"),
                }
            elif isinstance(value, (list, tuple)) and len(value) == 2:
                item = {"relation": relation, "head": value[0], "tail": value[1]}
            else:
                continue
            if item["head"] and item["tail"]:
                relations.append(item)
    return entities, relations


def build(
    rows: list[dict[str, Any]], extractor: Any, threshold: float = 0.35,
    progress_label: str = "Grafo",
) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(name="Polaris Knowledge Graph")
    counts = Counter()
    entity_index: dict[str, str] = {}

    total = len(rows)
    next_progress = 5
    started = time.perf_counter()
    print(f"[{progress_label}] Registros a procesar: {total:,}", flush=True)
    for row_number, row in enumerate(rows, 1):
        doc = text(row["doc_id"])
        chunk = text(row["chunk_id"])
        source = text(row.get("fuente") or row.get("source") or "unknown")
        phenomenon = text(row["fenomeno"])
        body = str(row.get("texto") or row.get("text") or "").strip()
        doc_node, chunk_node = f"doc:{doc}", f"chunk:{chunk}"
        source_node = f"source:{source.casefold()}"
        phenomenon_node = f"phenomenon:{phenomenon}"

        add_node(graph, doc_node, "document", doc, doc_id=doc, fuente=source)
        add_node(
            graph, chunk_node, "chunk", chunk, doc_id=doc, chunk_id=chunk,
            fuente=source, fenomeno=phenomenon, formato=row.get("formato"),
            idioma=row.get("idioma"), posicion=row.get("posicion"),
        )
        add_node(graph, source_node, "source", source, fuente=source)
        add_node(graph, phenomenon_node, "phenomenon", f"Fenómeno {phenomenon}", fenomeno=phenomenon)
        add_edge_once(graph, doc_node, chunk_node, relation="contains")
        add_edge_once(graph, doc_node, source_node, relation="comes_from")
        add_edge_once(graph, doc_node, phenomenon_node, relation="belongs_to")

        entities, relations = extract(extractor, body, threshold)
        counts["chunks"] += 1
        counts["entities"] += len(entities)
        counts["relations"] += len(relations)

        for entity in entities:
            label = text(entity["text"])
            kind = text(entity["kind"]).lower().replace(" ", "_")
            entity_node = node_key(kind, label)
            entity_index[label.casefold()] = entity_node
            add_node(graph, entity_node, kind, label, confidence=entity.get("confidence"))
            graph.add_edge(chunk_node, entity_node, relation="mentions", doc_id=doc, chunk_id=chunk)

        for item in relations:
            head_label, tail_label = text(item["head"]), text(item["tail"])
            head_node = entity_index.get(head_label.casefold(), node_key("entity", head_label))
            tail_node = entity_index.get(tail_label.casefold(), node_key("entity", tail_label))
            if head_node not in graph:
                add_node(graph, head_node, "entity", head_label)
            if tail_node not in graph:
                add_node(graph, tail_node, "entity", tail_label)
            graph.add_edge(
                head_node, tail_node, relation=text(item["relation"]),
                doc_id=doc, chunk_id=chunk, confidence=item.get("confidence"),
            )

        percent = row_number * 100 / total
        while next_progress <= 100 and percent >= next_progress:
            elapsed = max(time.perf_counter() - started, 1e-9)
            rate = row_number / elapsed
            print(
                f"[{progress_label}] {next_progress}% | "
                f"{row_number:,}/{total:,} chunks | "
                f"{rate:,.1f} chunks/s | "
                f"nodos={graph.number_of_nodes():,} aristas={graph.number_of_edges():,}",
                flush=True,
            )
            next_progress += 5

    graph.graph.update(
        schema_version="2.0", extractor="GLiNER2", generative_models="false",
        **{f"stat_{key}": str(value) for key, value in counts.items()},
    )
    return graph


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="fastino/gliner2-multi-v1")
    parser.add_argument("--threshold", type=float, default=0.35)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        parser.error("--threshold debe estar entre 0 y 1")

    extractor, _ = load_extractor(args.model, args.device)
    graph = build(load(args.metadata), extractor, args.threshold, "Grafo local")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    nx.write_graphml(graph, temporary)
    temporary.replace(args.output)
    print(f"Grafo generado: {args.output} | nodos={graph.number_of_nodes()} aristas={graph.number_of_edges()}")


if __name__ == "__main__":
    main()
