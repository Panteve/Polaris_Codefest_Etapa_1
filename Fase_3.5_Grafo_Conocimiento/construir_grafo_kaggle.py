# En una celda de Kaggle, antes de ejecutar este archivo:
# %pip install -q "gliner2[local]" networkx

"""Construye el grafo Polaris de forma autónoma en Kaggle.

Este archivo se puede copiar y pegar sin necesitar construir_grafo.py.
Busca un único metadata.jsonl en /kaggle/input y escribe el GraphML en
/kaggle/working/grafo.graphml.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import networkx as nx


KAGGLE_INPUT = Path("/kaggle/input")
KAGGLE_OUTPUT = Path("/kaggle/working")
MODEL_NAME = "fastino/gliner2-multi-v1"

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


def clean(value: Any, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()[:limit]


def node_key(kind: str, label: str) -> str:
    return f"{kind}:{clean(label).casefold()}"


def add_node(graph: nx.MultiDiGraph, node: str, kind: str, label: str, **attrs: Any) -> None:
    values = {key: clean(value) for key, value in attrs.items() if value is not None}
    values.update(kind=kind, label=clean(label))
    graph.add_node(node, **values)


def add_edge_once(graph: nx.MultiDiGraph, source: str, target: str, **attrs: Any) -> None:
    relation = attrs.get("relation")
    for _, target_node, data in graph.out_edges(source, data=True):
        if target_node == target and data.get("relation") == relation:
            return
    graph.add_edge(source, target, **{key: clean(value) for key, value in attrs.items()})


def find_metadata(explicit: Path | None) -> Path:
    if explicit:
        if not explicit.is_file():
            raise FileNotFoundError(f"No existe la metadata: {explicit}")
        return explicit
    candidates = sorted(KAGGLE_INPUT.rglob("metadata.jsonl"))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError("No se encontró metadata.jsonl en /kaggle/input.")
    raise RuntimeError(
        "Hay varias metadata.jsonl; indica una con --metadata:\n"
        + "\n".join(str(path) for path in candidates)
    )


def load_metadata(path: Path) -> list[dict[str, Any]]:
    rows = []
    seen_chunks = set()
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON inválido en línea {number}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"Línea {number}: se esperaba un objeto JSON.")
            missing = sorted(REQUIRED - set(row))
            if missing:
                raise ValueError(f"Línea {number}: faltan campos: {', '.join(missing)}")

            doc_id = clean(row.get("doc_id"))
            chunk_id = clean(row.get("chunk_id"))
            body = row.get("texto") or row.get("text")
            if not doc_id or not chunk_id:
                raise ValueError(f"Línea {number}: doc_id y chunk_id son obligatorios.")
            if not chunk_id.startswith(f"{doc_id}-"):
                raise ValueError(f"Línea {number}: chunk_id no trazable: {chunk_id}")
            if chunk_id in seen_chunks:
                raise ValueError(f"Línea {number}: chunk_id duplicado: {chunk_id}")
            if not body or not str(body).strip():
                raise ValueError(f"Línea {number}: el chunk no tiene texto.")
            if str(row.get("fenomeno")) not in {"1", "2", "3"}:
                raise ValueError(f"Línea {number}: fenomeno debe ser 1, 2 o 3.")
            seen_chunks.add(chunk_id)
            rows.append(row)
    if not rows:
        raise ValueError("No se encontraron registros en la metadata.")
    return rows


def extract(extractor: Any, body: str, threshold: float):
    entity_result = extractor.extract_entities(
        body, ENTITY_TYPES, threshold=threshold,
        include_confidence=True, include_spans=True,
    )
    relation_result = extractor.extract_relations(
        body, RELATION_TYPES, threshold=threshold,
        include_confidence=True, include_spans=True,
    )

    entities = []
    for kind, values in entity_result.get("entities", {}).items():
        for value in values or []:
            item = dict(value) if isinstance(value, dict) else {"text": value}
            if item.get("text"):
                item["kind"] = kind
                entities.append(item)

    relations = []
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


def build_graph(rows: list[dict[str, Any]], extractor: Any, threshold: float) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(name="Polaris Knowledge Graph")
    counts = Counter()
    entity_index = {}

    for row in rows:
        doc = clean(row["doc_id"])
        chunk = clean(row["chunk_id"])
        source = clean(row.get("fuente") or "unknown")
        phenomenon = clean(row["fenomeno"])
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
            label = clean(entity["text"])
            kind = clean(entity["kind"]).lower().replace(" ", "_")
            entity_node = node_key(kind, label)
            entity_index[label.casefold()] = entity_node
            add_node(graph, entity_node, kind, label, confidence=entity.get("confidence"))
            graph.add_edge(chunk_node, entity_node, relation="mentions", doc_id=doc, chunk_id=chunk)

        for item in relations:
            head_label, tail_label = clean(item["head"]), clean(item["tail"])
            head_node = entity_index.get(head_label.casefold(), node_key("entity", head_label))
            tail_node = entity_index.get(tail_label.casefold(), node_key("entity", tail_label))
            if head_node not in graph:
                add_node(graph, head_node, "entity", head_label)
            if tail_node not in graph:
                add_node(graph, tail_node, "entity", tail_label)
            graph.add_edge(
                head_node, tail_node, relation=clean(item["relation"]),
                doc_id=doc, chunk_id=chunk, confidence=item.get("confidence"),
            )

    graph.graph.update(
        schema_version="2.0", extractor="GLiNER2", generative_models="false",
        **{f"stat_{key}": str(value) for key, value in counts.items()},
    )
    return graph


def main() -> None:
    parser = argparse.ArgumentParser(description="Grafo Polaris autónomo para Kaggle.")
    parser.add_argument("--metadata", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=KAGGLE_OUTPUT / "grafo.graphml")
    parser.add_argument("--model", default=MODEL_NAME)
    parser.add_argument("--threshold", type=float, default=0.35)
    args, _ = parser.parse_known_args()
    if not 0 <= args.threshold <= 1:
        parser.error("--threshold debe estar entre 0 y 1")

    metadata_path = find_metadata(args.metadata)
    print(f"[Grafo Kaggle] Metadata: {metadata_path}", flush=True)
    print(f"[Grafo Kaggle] Modelo: {args.model}", flush=True)
    print(f"[Grafo Kaggle] Umbral: {args.threshold}", flush=True)

    from gliner2 import GLiNER2

    print("[Grafo Kaggle] Cargando modelo...", flush=True)
    extractor = GLiNER2.from_pretrained(args.model)
    graph = build_graph(load_metadata(metadata_path), extractor, args.threshold)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    nx.write_graphml(graph, temporary)
    temporary.replace(args.output)
    print(
        f"[Grafo Kaggle] Listo: nodos={graph.number_of_nodes():,} "
        f"aristas={graph.number_of_edges():,}",
        flush=True,
    )
    print(f"[Grafo Kaggle] Salida: {args.output}", flush=True)


if __name__ == "__main__":
    main()
