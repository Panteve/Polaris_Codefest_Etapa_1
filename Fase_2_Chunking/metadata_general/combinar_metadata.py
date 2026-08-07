"""Combina metadata de JSON, otros formatos y cada experimento PDF.

Las carpetas originales no se modifican. Para cada carpeta de experimento PDF
se crea una carpeta homónima dentro de metadata_general con metadata.json y
metadata.jsonl ordenados por doc_id y, dentro de cada documento, por chunk.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable


DOC_NUMBER_RE = re.compile(r"^(.*?)(\d+)$")
CHUNK_NUMBER_RE = re.compile(r"-CH-(\d+)$")


# El nombre de la carpeta PDF describe solamente la variante de chunking PDF.
# La salida combinada incluye tambien JSON y otros formatos, por lo que usa un
# nombre canonico que identifica la configuracion completa del corpus.
COMBINED_OUTPUT_NAMES = {
    "pdfs_standard_objetivo-200palabras_max-250_solapamiento-0_bge_m3":
        "corpus_bge_m3_standard",
    "pdfs_standard_objetivo-200palabras_max-250_solapamiento-0_granite":
        "corpus_granite_standard",
    "pdfs_late_chunking_objetivo-200palabras_max-250_solapamiento-0_granite_pdf":
        "corpus_bge_m3_granite_late_pdf",
    "pdfs_standard_objetivo-200palabras_max-250_solapamiento-1_bge_m3_overlap_1":
        "corpus_bge_m3_overlap_1",
    "pdfs_standard_objetivo-200palabras_max-250_solapamiento-1_granite_overlap_1":
        "corpus_granite_overlap_1",
    "pdfs_semantic_objetivo-200palabras_max-250_solapamiento-0_bge_m3_semantic":
        "corpus_bge_m3_semantic_pdf",
}


def combined_output_name(pdf_dir: Path) -> str:
    """Devuelve un nombre estable para la metadata combinada."""
    return COMBINED_OUTPUT_NAMES.get(pdf_dir.name, pdf_dir.name)


def resolve_project_path(value: str, project_root: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    from_current_directory = Path.cwd() / candidate
    if from_current_directory.exists():
        return from_current_directory
    return project_root / candidate


def read_metadata(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    if path.suffix.lower() == ".jsonl":
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_number}: {exc}") from exc
                if isinstance(value, dict):
                    records.append(value)
        return records
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} no contiene un arreglo JSON.")
    return [item for item in data if isinstance(item, dict)]


def numeric_tail(value: Any) -> tuple[int, str]:
    text = str(value or "")
    match = DOC_NUMBER_RE.match(text)
    if match:
        return int(match.group(2)), text
    return 2**63 - 1, text


def chunk_number(value: Any, position: Any) -> int:
    match = CHUNK_NUMBER_RE.search(str(value or ""))
    if match:
        return int(match.group(1))
    try:
        return int(position)
    except (TypeError, ValueError):
        return 2**63 - 1


def sort_key(item: dict[str, Any], source_priority: int) -> tuple[Any, ...]:
    doc_number, doc_text = numeric_tail(item.get("doc_id"))
    return (
        doc_number,
        doc_text,
        chunk_number(item.get("chunk_id"), item.get("posicion")),
        source_priority,
        str(item.get("chunk_id", "")),
    )


def combine(
    json_path: Path,
    otros_path: Path,
    pdf_path: Path,
) -> list[dict[str, Any]]:
    sources: Iterable[tuple[int, Path]] = (
        (0, json_path),
        (1, otros_path),
        (2, pdf_path),
    )
    records: list[tuple[int, dict[str, Any]]] = []
    for priority, path in sources:
        records.extend((priority, item) for item in read_metadata(path))
    records.sort(key=lambda pair: sort_key(pair[1], pair[0]))
    return [item for _, item in records]


def write_metadata(output_dir: Path, records: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metadata.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (output_dir / "metadata.jsonl").open(
        "w", encoding="utf-8", newline="\n"
    ) as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Combina metadata JSON, otros formatos y experimentos PDF."
    )
    parser.add_argument(
        "--json-input",
        default="Fase_2_Chunking/chunking-jsons/salida_json/metadata.jsonl",
    )
    parser.add_argument(
        "--otros-input",
        default="Fase_2_Chunking/chunking-otros/salida_otros/metadata.jsonl",
    )
    parser.add_argument(
        "--pdf-root",
        default="Fase_2_Chunking/chunking-pdfs",
    )
    parser.add_argument(
        "--output-root",
        default="Fase_2_Chunking/metadata_general",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[2]
    json_path = resolve_project_path(args.json_input, project_root)
    otros_path = resolve_project_path(args.otros_input, project_root)
    pdf_root = resolve_project_path(args.pdf_root, project_root)
    output_root = resolve_project_path(args.output_root, project_root)

    pdf_dirs = sorted(path for path in pdf_root.iterdir() if path.is_dir())
    if not pdf_dirs:
        raise FileNotFoundError(f"No se encontraron carpetas PDF en {pdf_root}.")

    for pdf_dir in pdf_dirs:
        pdf_metadata = pdf_dir / "metadata.jsonl"
        combined = combine(json_path, otros_path, pdf_metadata)
        output_name = combined_output_name(pdf_dir)
        write_metadata(output_root / output_name, combined)
        print(f"{pdf_dir.name} -> {output_name}: {len(combined)} registros")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
