"""Genera un grafo GraphML trazable desde metadata.jsonl.

El grafo es determinista, no usa modelos generativos y evita crear conexiones
entre todos los pares de chunks (un patrón que crece de forma cuadrática).

Uso:
    python construir_grafo.py --metadata metadata.jsonl --output grafo.graphml
"""
from __future__ import annotations
import argparse, json, re
from collections import Counter
from pathlib import Path
import networkx as nx

PATTERNS = {
    "country": re.compile(r"\b(Argentina|Brasil|Brazil|Chile|Colombia|Ecuador|México|Mexico|Perú|Peru|Venezuela|Bolivia|Uruguay|Paraguay|China|India|Rusia|Russia|Ucrania|Ukraine)\b", re.I),
    "organization": re.compile(r"\b(ONU|UNOOSA|SIPRI|RESDAL|CEEEP|MAPP[- ]?OEA|Atlantic Council|Stanford AI Index|NASA|INPE)\b", re.I),
    "concept": re.compile(r"\b(inteligencia artificial|artificial intelligence|IA|AI|machine learning|órbita baja terrestre|Low Earth Orbit|LEO|space debris|desechos espaciales|cambio climático|climate change|migración|migration|gobernanza|governance|seguridad espacial|space security|peace and security|desarrollo humano)\b", re.I),
}

def text(value, limit=500):
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()[:limit]

def add_node(g, node, kind, label, **attrs):
    g.add_node(node, kind=kind, label=text(label), **{k: text(v) for k, v in attrs.items()})

def entities(value):
    found = set()
    for kind, pattern in PATTERNS.items():
        for match in pattern.finditer(value):
            found.add((kind, text(match.group(1)).lower()))
    return found

REQUIRED = {"doc_id", "chunk_id", "fuente", "fenomeno"}


def load(path: Path):
    if not path.is_file():
        raise FileNotFoundError(f"No existe la metadata: {path}")
    rows = []
    seen_docs = set()
    seen_chunks = set()
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
        body = row.get("texto") or row.get("text")
        if not body or not str(body).strip():
            raise ValueError(f"Línea {number}: el chunk {row.get('chunk_id')} no tiene texto.")
        if row["doc_id"] in seen_docs and not str(row["chunk_id"]).startswith(f"{row['doc_id']}-"):
            raise ValueError(f"Línea {number}: chunk_id no trazable a doc_id.")
        if row["chunk_id"] in seen_chunks:
            raise ValueError(f"Línea {number}: chunk_id duplicado: {row['chunk_id']}")
        seen_docs.add(row["doc_id"])
        seen_chunks.add(row["chunk_id"])
        rows.append(row)
    if not rows:
        raise ValueError("No hay registros con texto en la metadata.")
    return rows

def build(rows, max_entities_per_chunk=30):
    g = nx.MultiDiGraph(name="Polaris Knowledge Graph")
    phenomena = {}
    counts = Counter()
    for i, row in enumerate(rows):
        doc = text(row.get("doc_id") or f"DOC-{i:06d}")
        chunk = text(row.get("chunk_id") or f"{doc}-CH-{i:06d}")
        source = text(row.get("fuente") or row.get("source") or "unknown")
        phen = text(row.get("fenomeno") or "unknown")
        body = text(row.get("texto") or row.get("text"), 50000)
        dn, cn, sn = f"doc:{doc}", f"chunk:{chunk}", f"source:{source}"
        pn = phenomena.setdefault(phen, f"phenomenon:{phen}")
        add_node(g, dn, "document", doc, doc_id=doc, fuente=source)
        add_node(g, cn, "chunk", chunk, doc_id=doc, chunk_id=chunk)
        add_node(g, sn, "source", source, fuente=source)
        add_node(g, pn, "phenomenon", f"Fenómeno {phen}", fenomeno=phen)
        g.add_edge(dn, cn, relation="contains")
        g.add_edge(dn, sn, relation="comes_from")
        g.add_edge(dn, pn, relation="belongs_to")
        found = sorted(entities(body))[:max_entities_per_chunk]
        counts["chunks"] += 1
        counts["entities"] += len(found)
        for kind, label in found:
            en = f"{kind}:{label}"
            add_node(g, en, kind, label)
            g.add_edge(cn, en, relation="mentions")
            g.add_edge(dn, en, relation="document_mentions")
    g.graph.update(schema_version="1.1", generative_models="false", **{f"stat_{k}": str(v) for k, v in counts.items()})
    return g

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-entities-per-chunk", type=int, default=30)
    args = parser.parse_args()
    if args.max_entities_per_chunk < 1:
        parser.error("--max-entities-per-chunk debe ser mayor que cero")
    graph = build(load(args.metadata), args.max_entities_per_chunk)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    nx.write_graphml(graph, temporary)
    temporary.replace(args.output)
    print(f"Grafo generado: {args.output} | nodos={graph.number_of_nodes()} aristas={graph.number_of_edges()}")

if __name__ == "__main__":
    main()
