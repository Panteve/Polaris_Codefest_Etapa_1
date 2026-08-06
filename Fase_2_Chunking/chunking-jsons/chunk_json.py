"""Chunking adaptativo para los TXT derivados de documentos JSON.

El manifiesto de Fase 1 conserva el formato original del documento. Por eso
este script procesa solo registros con formato "json", aunque su archivo final
sea un TXT.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger("ChunkerJSON")
LABEL_RE = re.compile(r"^([A-Za-z0-9_$.\[\]-]+):\s*(.*)$")
SENTENCE_RE = re.compile(r"(?<=[.!?。！？｡])\s+")
WHITESPACE_RE = re.compile(r"\s+")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
ROW_INDEX_RE = re.compile(r"\[\d+\]")
ALERT_CONTEXT_LABELS = {
    "codigo": "Código",
    "code": "Código",
    "fecha": "Fecha",
    "fecha_emision": "Fecha",
    "date": "Fecha",
    "municipio": "Municipios",
    "municipios": "Municipios",
    "tipo": "Tipo",
    "type": "Tipo",
}


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    if isinstance(data, list):
        return data
    for key in ("documentos", "documents", "registros", "records"):
        if isinstance(data.get(key), list):
            return data[key]
    raise ValueError("El manifiesto no contiene una lista reconocible.")


def resolve_project_path(value: str, project_root: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    from_current_directory = Path.cwd() / candidate
    if from_current_directory.exists():
        return from_current_directory
    return project_root / candidate


def resolve_text_path(item: dict[str, Any], manifest_path: Path) -> Path:
    candidates: list[Path] = []
    if item.get("archivo_final"):
        candidates.append(Path(str(item["archivo_final"])))
    if item.get("ruta_final"):
        relative = str(item["ruta_final"]).replace("\\", "/")
        candidates.append(manifest_path.parent / relative)
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    raise FileNotFoundError(f"No se encontró el TXT de {item.get('doc_id')}.")


def original_source_name(item: dict[str, Any]) -> str:
    original = item.get("ruta_original")
    if original:
        return Path(str(original).replace("\\", "/")).name
    return str(item.get("fuente", ""))


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        LOGGER.warning("No existe la configuración; se usarán valores predeterminados.")
        return {}
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError("La configuración debe ser un objeto JSON.")
    return data


def word_count(text: str) -> int:
    return len(text.split())


def token_count(text: str) -> int:
    """Estimación estable hasta definir el tokenizer del encoder final."""
    return round(word_count(text) * 1.3)


def clean_value(value: str) -> str:
    value = CONTROL_RE.sub(" ", value.replace("\ufeff", ""))
    return WHITESPACE_RE.sub(" ", value).strip()


def excluded_label(label: str, excluded: set[str]) -> bool:
    simple = ROW_INDEX_RE.sub("", label).lower().split(".")[-1]
    if simple == "title":
        return True
    return any(term.lower() in simple for term in excluded)


def alert_context_label(label: str) -> str | None:
    simple = ROW_INDEX_RE.sub("", label).lower().split(".")[-1]
    return ALERT_CONTEXT_LABELS.get(simple)


def parse_clean_txt(path: Path, config: dict[str, Any]) -> tuple[str, list[str]]:
    warnings: list[str] = []
    excluded = set(config.get("etiquetas_excluidas", []))
    blocks: list[str] = []

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return "", [f"error_lectura: {exc}"]

    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = LABEL_RE.match(line)
        if match:
            label, value = match.groups()
            if excluded_label(label, excluded):
                continue
            value = clean_value(value)
            if value:
                context_label = alert_context_label(label)
                blocks.append(
                    f"{context_label}: {value}" if context_label else value
                )
        else:
            value = clean_value(line)
            if value:
                blocks.append(value)

    text = WHITESPACE_RE.sub(" ", " ".join(blocks)).strip()
    if not text:
        warnings.append("contenido_insuficiente")
    return text, warnings


def sentence_parts(text: str) -> list[str]:
    parts = [part.strip() for part in SENTENCE_RE.split(text) if part.strip()]
    return parts or [text]


def normalized_span(source: str, candidate: str, cursor: int) -> tuple[int, int]:
    tokens = re.findall(r"\S+", candidate)
    if not tokens:
        return cursor, cursor
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    match = re.search(pattern, source[cursor:], flags=re.DOTALL)
    if not match:
        return cursor, cursor + len(candidate)
    return cursor + match.start(), cursor + match.end()


def make_chunk(
    item: dict[str, Any],
    doc_id: str,
    text: str,
    position: int,
    source_text: str,
    cursor_char: int,
    cursor_token: int,
    warnings: list[str],
) -> tuple[dict[str, Any], int, int]:
    text = WHITESPACE_RE.sub(" ", text).strip()
    num_tokens = token_count(text)
    start, end = normalized_span(source_text, text, cursor_char)
    chunk = {
        "doc_id": doc_id,
        "chunk_id": f"{doc_id}-CH-{position:04d}",
        "fuente": original_source_name(item),
        "formato": "json",
        "fenomeno": int(item.get("fenomeno", 0)),
        "posicion": position,
        "texto": text,
        "num_tokens": num_tokens,
        "num_palabras": word_count(text),
        "idioma": item.get("idioma", "unknown"),
        "char_start": start,
        "char_end": end,
        "token_start": cursor_token,
        "token_end": cursor_token + num_tokens,
        "chunking_mode": "late_chunking",
        "offsets_base": "texto_normalizado_del_documento",
    }
    return chunk, end, cursor_token + num_tokens


def generate_chunks(
    item: dict[str, Any],
    text: str,
    warnings: list[str],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    limits = config.get("limites", {})
    target_words = int(limits.get("palabras_objetivo_max", 200))
    absolute_words = int(limits.get("palabras_limite_absoluto", 250))
    doc_id = str(item["doc_id"])
    total_words = word_count(text)

    if total_words <= absolute_words:
        chunk, _, _ = make_chunk(
            item, doc_id, text, 0, text, 0, 0, warnings
        )
        return [chunk]

    blocks: list[str] = []
    current: list[str] = []
    current_words = 0
    for sentence in sentence_parts(text):
        count = word_count(sentence)
        if current and current_words + count > target_words:
            blocks.append(" ".join(current))
            current = []
            current_words = 0
        current.append(sentence)
        current_words += count
    if current:
        blocks.append(" ".join(current))

    chunks: list[dict[str, Any]] = []
    cursor_char = 0
    cursor_token = 0
    for position, block in enumerate(blocks):
        chunk_warnings = list(warnings)
        if word_count(block) > absolute_words:
            chunk_warnings.append("chunk_supera_limite_de_palabras")
        chunk, cursor_char, cursor_token = make_chunk(
            item,
            doc_id,
            block,
            position,
            text,
            cursor_char,
            cursor_token,
            chunk_warnings,
        )
        chunks.append(chunk)
    return chunks


def write_outputs(
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
    (output_dir / "reporte_chunking_json.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepara chunks de TXT cuyo formato original era JSON."
    )
    parser.add_argument(
        "--manifest",
        default="Fase_1_Limpieza/output_final_limpio/manifiesto_final_limpio.json",
    )
    parser.add_argument(
        "--output",
        default="Fase_2_Chunking/chunking-jsons/salida_json",
    )
    parser.add_argument(
        "--config",
        default="Fase_2_Chunking/chunking-jsons/config_script.json",
    )
    parser.add_argument("--sample", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    configure_logging()
    args = parse_args()
    project_root = Path(__file__).resolve().parents[2]
    manifest_path = resolve_project_path(args.manifest, project_root)
    output_dir = resolve_project_path(args.output, project_root)
    config_path = resolve_project_path(args.config, project_root)
    config = load_config(config_path)
    manifest = load_manifest(manifest_path)
    selected = [item for item in manifest if item.get("formato") == "json"]

    if args.sample > 0:
        rng = random.Random(args.seed)
        selected = rng.sample(selected, min(args.sample, len(selected)))
        selected.sort(key=lambda item: str(item.get("doc_id", "")))

    chunks: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "configuracion": {
            "manifest": str(manifest_path),
            "encoder_tokenizer": "estimacion_1.3_por_palabra",
            "late_chunking": True,
            "limite_tokens": None,
            "sample": args.sample,
            "seed": args.seed if args.sample > 0 else None,
        },
        "resumen": {
            "documentos_en_manifest": len(manifest),
            "documentos_json_seleccionados": len(selected),
            "documentos_procesados": 0,
            "documentos_con_error": 0,
            "chunks_generados": 0,
        },
        "advertencias": [],
        "errores": [],
        "documentos": [],
    }

    for item in selected:
        doc_id = str(item.get("doc_id", "sin_doc_id"))
        try:
            source_path = resolve_text_path(item, manifest_path)
            text, warnings = parse_clean_txt(source_path, config)
            doc_report = {
                "doc_id": doc_id,
                "archivo": source_path.name,
                "chunks": 0,
                "advertencias": warnings,
            }
            if not text:
                report["documentos"].append(doc_report)
                report["errores"].append({
                    "doc_id": doc_id,
                    "error": "contenido_insuficiente",
                })
                report["resumen"]["documentos_con_error"] += 1
                continue

            doc_chunks = generate_chunks(item, text, warnings, config)
            chunks.extend(doc_chunks)
            doc_report["chunks"] = len(doc_chunks)
            report["documentos"].append(doc_report)
            report["resumen"]["documentos_procesados"] += 1
            report["resumen"]["chunks_generados"] += len(doc_chunks)
            if warnings:
                report["advertencias"].append({
                    "doc_id": doc_id,
                    "detalles": warnings,
                })
        except (OSError, UnicodeError, KeyError, ValueError) as exc:
            report["resumen"]["documentos_con_error"] += 1
            report["errores"].append({"doc_id": doc_id, "error": str(exc)})

    if args.dry_run:
        LOGGER.info(
            "Dry-run: %s documentos seleccionados, %s chunks calculados.",
            len(selected),
            report["resumen"]["chunks_generados"],
        )
        return 0 if not report["errores"] else 1

    write_outputs(output_dir, chunks, report)
    LOGGER.info("Salida generada en %s", output_dir)
    return 0 if not report["errores"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
