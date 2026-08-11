"""Chunking determinista para CSV, imágenes y TXT derivados de PBF."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SUPPORTED_FORMATS = {"csv", "image", "pbf"}
EXCLUDED_SOURCES = {"AMAZONUW_amazonunderworld-data"}
ROW_MARKER_RE = re.compile(r"^\s*\[fila\s+\d+\]\s*[:\-]?\s*", re.IGNORECASE)
FIELD_SEPARATOR_RE = re.compile(r"\s*\|\s*")
WHITESPACE_RE = re.compile(r"\s+")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def word_count(text: str) -> int:
    return len(text.split())


def estimated_tokens(text: str) -> int:
    return round(word_count(text) * 1.3)


def clean_text(text: str) -> str:
    text = CONTROL_RE.sub(" ", text.replace("\ufeff", ""))
    text = WHITESPACE_RE.sub(" ", text).strip()
    return ROW_MARKER_RE.sub("", text).strip()


def load_manifest(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    for key in ("documentos", "documents", "registros", "records"):
        if isinstance(data.get(key), list):
            return data[key]
    raise ValueError("El manifiesto no contiene una lista reconocible.")


def resolve_text_path(item: dict[str, Any], manifest_path: Path) -> Path:
    candidates: list[Path] = []
    archivo_final = item.get("archivo_final")
    if archivo_final:
        candidates.append(Path(archivo_final))
    ruta_final = item.get("ruta_final")
    if ruta_final:
        candidates.append(manifest_path.parent / Path(str(ruta_final).replace("\\", "/")))
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"No se encontró el texto final para {item.get('doc_id', 'sin_doc_id')}."
    )


def resolve_project_path(value: str, project_root: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    from_current_directory = Path.cwd() / candidate
    if from_current_directory.exists():
        return from_current_directory
    return project_root / candidate


def split_fields(text: str) -> list[str]:
    return [part.strip() for part in FIELD_SEPARATOR_RE.split(text) if part.strip()]


def split_oversized_record(text: str, max_words: int) -> tuple[list[str], list[str]]:
    """Divide un registro grande por campos, no por caracteres."""
    if word_count(text) <= max_words:
        return [text], []

    fields = split_fields(text)
    if len(fields) <= 1:
        words = text.split()
        pieces = [
            " ".join(words[index:index + max_words])
            for index in range(0, len(words), max_words)
        ]
        return pieces, ["registro sin separadores dividido por límite de palabras"]

    pieces: list[str] = []
    current: list[str] = []
    current_words = 0
    for field in fields:
        count = word_count(field)
        if current and current_words + count > max_words:
            pieces.append(" | ".join(current))
            current = []
            current_words = 0
        if count > max_words:
            field_words = field.split()
            if current:
                pieces.append(" | ".join(current))
                current = []
                current_words = 0
            pieces.extend(
                " ".join(field_words[index:index + max_words])
                for index in range(0, len(field_words), max_words)
            )
            continue
        current.append(field)
        current_words += count
    if current:
        pieces.append(" | ".join(current))
    return pieces, ["registro dividido por campos para respetar el máximo"]


def image_context_and_records(lines: list[str]) -> tuple[str, list[str]]:
    cleaned = [clean_text(line) for line in lines if clean_text(line)]
    if not cleaned:
        return "", []
    if len(cleaned) == 1:
        return "", cleaned
    first = cleaned[0]
    if "|" not in first and not first.lower().startswith(("date:", "category:", "rank:")):
        return first, cleaned[1:]
    return "", cleaned


def records_from_text(text: str, formato: str) -> list[str]:
    lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]
    if formato == "image":
        context, records = image_context_and_records(lines)
        if context:
            records = [f"{context} | {record}" for record in records]
        return records
    return lines


def build_chunk(
    item: dict[str, Any],
    text: str,
    position: int,
    warning: str | None,
) -> dict[str, Any]:
    doc_id = str(item["doc_id"])
    chunk: dict[str, Any] = {
        "doc_id": doc_id,
        "chunk_id": f"{doc_id}-CH-{position:04d}",
        "fuente": item.get("fuente", item.get("ruta_original", "")),
        "formato": item.get("formato", "txt"),
        "fenomeno": int(item.get("fenomeno", 0)),
        "posicion": position,
        "idioma": item.get("idioma", "unknown"),
        "num_palabras": word_count(text),
        "num_tokens": estimated_tokens(text),
        "chunking_mode": "structured_record",
        "texto": text,
        "unidad": "registro",
    }
    return chunk


def process_document(
    item: dict[str, Any],
    manifest_path: Path,
    max_words: int,
    min_words: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    source_path = resolve_text_path(item, manifest_path)
    raw_text = source_path.read_text(encoding="utf-8", errors="replace")
    records = records_from_text(raw_text, item.get("formato", "txt"))
    chunks: list[dict[str, Any]] = []
    warnings: list[str] = []

    for record in records:
        pieces, split_warnings = split_oversized_record(record, max_words)
        warnings.extend(split_warnings)
        for piece in pieces:
            if word_count(piece) < min_words:
                warnings.append(f"registro omitido por tener {word_count(piece)} palabras")
                continue
            chunks.append(
                build_chunk(
                    item,
                    piece,
                    len(chunks),
                    split_warnings[0] if split_warnings else None,
                )
            )
    return chunks, warnings


def write_json_outputs(
    output_dir: Path,
    chunks: list[dict[str, Any]],
    report: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metadata.json").write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (output_dir / "metadata.jsonl").open(
        "w", encoding="utf-8", newline="\n"
    ) as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    (output_dir / "reporte_chunking_otros.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera metadata para CSV, imágenes y TXT derivados de PBF."
    )
    parser.add_argument(
        "--manifest",
        default="Fase_1_Limpieza/output_final_limpio/manifiesto_final_limpio.json",
    )
    parser.add_argument(
        "--output",
        default="Fase_2_Chunking/chunking-otros/salida_otros",
    )
    parser.add_argument("--maximo", type=int, default=250)
    parser.add_argument("--minimo", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[2]
    manifest_path = resolve_project_path(args.manifest, project_root)
    output_dir = resolve_project_path(args.output, project_root)
    records = load_manifest(manifest_path)
    selected = [
        item for item in records
        if item.get("formato") in SUPPORTED_FORMATS
        and item.get("fuente") not in EXCLUDED_SOURCES
    ]
    excluded = [
        {
            "doc_id": item.get("doc_id"),
            "fuente": item.get("fuente"),
            "motivo": "información consolidada en el PBF",
        }
        for item in records
        if item.get("fuente") in EXCLUDED_SOURCES
    ]

    chunks: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "configuracion": {
            "formatos": sorted(SUPPORTED_FORMATS),
            "maximo_palabras": args.maximo,
            "minimo_palabras": args.minimo,
            "estrategia": "un registro autocontenido por chunk, sin solapamiento",
            "num_tokens": "estimacion_1.3_por_palabra",
        },
        "resumen": {
            "documentos_en_manifest": len(records),
            "documentos_seleccionados": len(selected),
            "documentos_excluidos": len(excluded),
            "documentos_procesados": 0,
            "documentos_con_error": 0,
            "chunks_generados": 0,
            "chunks_omitidos": 0,
        },
        "errores": [],
        "exclusiones": excluded,
        "documentos": [],
    }

    for item in selected:
        doc_id = item.get("doc_id", "sin_doc_id")
        try:
            document_chunks, warnings = process_document(
                item, manifest_path, args.maximo, args.minimo
            )
            chunks.extend(document_chunks)
            report["resumen"]["documentos_procesados"] += 1
            report["resumen"]["chunks_generados"] += len(document_chunks)
            report["resumen"]["chunks_omitidos"] += sum(
                "omitido" in warning for warning in warnings
            )
            report["documentos"].append({
                "doc_id": doc_id,
                "formato": item.get("formato"),
                "chunks": len(document_chunks),
                "advertencias": warnings,
            })
        except (OSError, UnicodeError, KeyError, ValueError) as exc:
            report["resumen"]["documentos_con_error"] += 1
            report["errores"].append({"doc_id": doc_id, "mensaje": str(exc)})

    write_json_outputs(output_dir, chunks, report)
    return 0 if not report["errores"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
