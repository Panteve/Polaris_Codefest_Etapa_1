"""Genera un grafo por cada configuración de Fase_4.1.

El script se puede ejecutar desde la carpeta Fase_3.5_Grafo_Conocimiento y
solo necesita que Fase_4.1_Recuperacion_Consolidado esté junto a ella:

    python generar_grafos_4_1.py

Cada configuración que contenga metadata.jsonl recibe su propio archivo:
Fase_4.1_Recuperacion_Consolidado/<configuracion>/grafo.graphml
"""
from __future__ import annotations

import argparse
from pathlib import Path

import networkx as nx

from construir_grafo import build, load, load_extractor


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PHASE_4 = SCRIPT_DIR.parent / "Fase_4.1_Recuperacion_Consolidado"


def configurations(root: Path, selected: str | None) -> list[Path]:
    if not root.is_dir():
        raise FileNotFoundError(f"No existe la Fase 4.1: {root}")
    folders = sorted(path for path in root.iterdir() if path.is_dir())
    if selected:
        folders = [path for path in folders if path.name == selected]
    result = [path for path in folders if (path / "metadata.jsonl").is_file()]
    if not result:
        suffix = f" para {selected}" if selected else ""
        raise FileNotFoundError(f"No hay configuraciones con metadata.jsonl{suffix} en {root}")
    return result


def write_graph(graph: nx.MultiDiGraph, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    nx.write_graphml(graph, temporary)
    temporary.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera grafos para las configuraciones de Fase 4.1.")
    parser.add_argument("--fase-4", type=Path, default=DEFAULT_PHASE_4)
    parser.add_argument("--configuracion", default=None, help="Procesa solo una carpeta, por ejemplo 01_bge_m3_corpus.")
    parser.add_argument("--model", default="fastino/gliner2-multi-v1")
    parser.add_argument("--threshold", type=float, default=0.35)
    parser.add_argument("--salida", type=Path, default=None, help="Raíz alternativa para los GraphML.")
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        parser.error("--threshold debe estar entre 0 y 1")

    configs = configurations(args.fase_4.resolve(), args.configuracion)
    output_root = args.salida.resolve() if args.salida else args.fase_4.resolve()
    print(f"Configuraciones encontradas: {len(configs)}")
    print(f"Modelo: {args.model}")
    print(f"Umbral: {args.threshold}")
    print("Cargando modelo...")
    extractor = load_extractor(args.model)

    for number, config in enumerate(configs, 1):
        metadata = config / "metadata.jsonl"
        output = output_root / config.name / "grafo.graphml"
        print(f"[{number}/{len(configs)}] {config.name}")
        print(f"  metadata: {metadata}")
        graph = build(load(metadata), extractor, args.threshold)
        write_graph(graph, output)
        print(f"  salida: {output}")
        print(f"  nodos={graph.number_of_nodes():,} aristas={graph.number_of_edges():,}")


if __name__ == "__main__":
    main()
