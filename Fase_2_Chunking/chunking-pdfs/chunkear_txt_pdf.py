"""Fragmenta los TXT derivados de PDF para la Fase 2.

El modo ``late_chunking`` no calcula embeddings. Produce los mismos límites
deterministas que el modo convencional y añade offsets para que Fase 3 pueda
contextualizar el documento completo antes de hacer pooling por chunk.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("Fase_1_Limpieza/output_post_limpieza")
DEFAULT_MANIFEST = DEFAULT_INPUT / "manifiesto_post_limpieza.json"
DEFAULT_OUTPUT = Path("Fase_2_Chunking/chunking-pdfs")

WORD_RE = re.compile(r"\S+", re.UNICODE)
SENTENCE_END_RE = re.compile(r"[.!?。！？](?:[\"'”’»)]*)$")
HEADING_RE = re.compile(r"^(?:#{1,6}\s+|\d+(?:\.\d+)*[.)]?\s+)")
ABBREVIATIONS = {
    "a", "art", "cap", "dr", "etc", "fig", "inc", "no", "núm", "p", "pág",
    "prof", "sr", "sra", "sta", "st", "vs", "e.g", "i.e", "u.s", "ee.uu",
}


@dataclass
class Sentence:
    text: str
    char_start: int
    char_end: int
    word_count: int


@dataclass
class Block:
    text: str
    char_start: int
    char_end: int
    is_heading: bool = False
    section: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera metadata JSON/JSONL de chunks para TXT provenientes de PDF."
    )
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--mode",
        choices=("standard", "late_chunking"),
        default="standard",
        help="standard o late_chunking (este último solo prepara offsets).",
    )
    parser.add_argument("--target-words", type=int, default=200)
    parser.add_argument("--max-words", type=int, default=250)
    parser.add_argument(
        "--overlap-sentences",
        type=int,
        default=0,
        help="Cantidad de oraciones finales que se repiten al inicio del siguiente chunk.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=0,
        help="Límite opcional de tokens. 0 desactiva el límite hasta elegir encoder.",
    )
    parser.add_argument(
        "--label",
        default="",
        help="Nombre adicional para la carpeta de salida, por ejemplo bge_m3.",
    )
    return parser.parse_args()


def load_manifest(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("El manifiesto debe ser una lista de documentos.")
    return [item for item in data if isinstance(item, dict)]


def resolve_text_path(item: dict[str, Any], input_root: Path) -> Path | None:
    candidates: list[Path] = []
    for key in ("archivo_limpio_post", "ruta_limpio_post", "ruta_limpio", "archivo_limpio"):
        value = item.get(key)
        if value:
            candidate = Path(str(value))
            candidates.extend((candidate, input_root / candidate))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def normalize_text(raw: str) -> str:
    text = unicodedata.normalize("NFC", raw).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u00ad", "")
    text = "".join(char for char in text if char in "\n\t" or not unicodedata.category(char).startswith("C"))

    paragraphs: list[str] = []
    current: list[str] = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            current.append(line)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs).strip()


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def looks_like_heading(text: str) -> bool:
    stripped = text.strip()
    if HEADING_RE.match(stripped):
        return True
    if len(stripped) > 140 or word_count(stripped) > 16:
        return False
    if SENTENCE_END_RE.search(stripped):
        return False
    letters = [char for char in stripped if char.isalpha()]
    return bool(letters) and sum(char.isupper() for char in letters) / len(letters) > 0.65


def split_blocks(text: str) -> list[Block]:
    raw_blocks: list[Block] = []
    cursor = 0
    for match in re.finditer(r"\n\n+", text):
        start, end = cursor, match.start()
        block_text = text[start:end].strip()
        if block_text:
            actual_start = start + len(text[start:end]) - len(text[start:end].lstrip())
            raw_blocks.append(Block(block_text, actual_start, actual_start + len(block_text), looks_like_heading(block_text)))
        cursor = match.end()
    block_text = text[cursor:].strip()
    if block_text:
        actual_start = cursor + len(text[cursor:]) - len(text[cursor:].lstrip())
        raw_blocks.append(Block(block_text, actual_start, actual_start + len(block_text), looks_like_heading(block_text)))

    # Un encabezado aislado de un PDF debe viajar con el contenido inmediato.
    # Así se conserva la señal estructural sin convertir el encabezado en un
    # chunk vacío o independiente.
    blocks: list[Block] = []
    index = 0
    while index < len(raw_blocks):
        block = raw_blocks[index]
        if block.is_heading and index + 1 < len(raw_blocks):
            following = raw_blocks[index + 1]
            blocks.append(Block(
                text=f"{block.text}\n\n{following.text}",
                char_start=block.char_start,
                char_end=following.char_end,
                section=block.text,
            ))
            index += 2
        else:
            blocks.append(block)
            index += 1
    return blocks


def split_sentences(block: Block) -> list[Sentence]:
    text = block.text
    sentences: list[Sentence] = []
    start = 0
    for index, char in enumerate(text):
        if char not in ".!?。！？":
            continue
        suffix = text[index + 1 :]
        if suffix and not re.match(r"[\s\"'”’»)]", suffix):
            continue
        prefix = text[max(0, start) : index + 1]
        previous_word = re.findall(r"[\wÀ-ÿ.]+", prefix.lower())
        if char == "." and previous_word:
            token = previous_word[-1].rstrip(".")
            if token in ABBREVIATIONS or (token.isdigit() and index + 1 < len(text) and text[index + 1 :].lstrip()[:1].isdigit()):
                continue
        end = index + 1
        while end < len(text) and text[end] in "\"'”’»)]":
            end += 1
        sentence = text[start:end].strip()
        if sentence:
            local_start = start + len(text[start:end]) - len(text[start:end].lstrip())
            sentences.append(Sentence(sentence, block.char_start + local_start, block.char_start + local_start + len(sentence), word_count(sentence)))
        start = end
    tail = text[start:].strip()
    if tail:
        local_start = start + len(text[start:]) - len(text[start:].lstrip())
        sentences.append(Sentence(tail, block.char_start + local_start, block.char_start + local_start + len(tail), word_count(tail)))
    return sentences


def estimate_tokens(text: str) -> int:
    # Estimación conservadora y reproducible hasta elegir tokenizer en Fase 3.
    return max(1, len(re.findall(r"\w+|[^\w\s]", text, re.UNICODE)))


def sentence_fits(sentences: list[Sentence], candidate: Sentence, target: int, max_words: int, max_tokens: int) -> bool:
    text = " ".join(sentence.text for sentence in sentences + [candidate])
    words = word_count(text)
    if words > max_words:
        return False
    if len(sentences) and words > target:
        return False
    return not max_tokens or estimate_tokens(text) <= max_tokens


def make_chunks(text: str, target: int, max_words: int, overlap: int, max_tokens: int) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    chunks: list[dict[str, Any]] = []
    for block in split_blocks(text):
        sentences = split_sentences(block)
        index = 0
        while index < len(sentences):
            current: list[Sentence] = []
            while index < len(sentences):
                sentence = sentences[index]
                if not current:
                    current.append(sentence)
                    index += 1
                    continue
                if sentence_fits(current, sentence, target, max_words, max_tokens):
                    current.append(sentence)
                    index += 1
                else:
                    break
            chunk_text = " ".join(sentence.text for sentence in current).strip()
            chunk_words = word_count(chunk_text)
            if chunk_words > max_words:
                warnings.append(f"Chunk excede max_words por una oración indivisible: {chunk_words} palabras.")
            if max_tokens and estimate_tokens(chunk_text) > max_tokens:
                warnings.append(f"Chunk excede max_tokens por una oración indivisible: {estimate_tokens(chunk_text)} tokens estimados.")
            chunks.append({
                "texto": chunk_text,
                "char_start": current[0].char_start,
                "char_end": current[-1].char_end,
                "num_palabras": chunk_words,
                "num_tokens_estimados": estimate_tokens(chunk_text),
                "seccion": block.section,
            })
            if overlap and index < len(sentences):
                index = max(index - min(overlap, len(current)), index - 1)
    return chunks, warnings


def output_folder(args: argparse.Namespace) -> Path:
    label = f"_{args.label}" if args.label else ""
    return args.output_root / (
        f"pdfs_{args.mode}_objetivo-{args.target_words}palabras_"
        f"max-{args.max_words}_solapamiento-{args.overlap_sentences}{label}"
    )


def build_record(item: dict[str, Any], chunk: dict[str, Any], position: int, mode: str) -> dict[str, Any]:
    record = {
        "doc_id": item.get("doc_id"),
        "chunk_id": f"{item.get('doc_id')}-CH-{position + 1:04d}",
        "fuente": item.get("fuente"),
        "formato": "pdf",
        "fenomeno": item.get("fenomeno"),
        "posicion": position,
        "idioma": item.get("idioma", "unknown"),
        "num_palabras": chunk["num_palabras"],
        "num_tokens": chunk["num_tokens_estimados"],
        "texto": chunk["texto"],
    }
    if mode == "late_chunking":
        record.update({
            "chunking_mode": "late_chunking",
            "char_start": chunk["char_start"],
            "char_end": chunk["char_end"],
            "offsets_base": "texto_normalizado_del_documento",
        })
    if chunk.get("seccion"):
        record["seccion"] = chunk["seccion"]
    return record


def main() -> int:
    args = parse_args()
    if args.target_words <= 0 or args.max_words <= 0 or args.target_words > args.max_words:
        raise SystemExit("target-words debe ser positivo y no superar max-words.")
    if args.overlap_sentences < 0:
        raise SystemExit("overlap-sentences no puede ser negativo.")

    manifest = load_manifest(args.manifest)
    destination = output_folder(args)
    destination.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "version_pipeline": "1.0.0",
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "configuracion": {
            "modo": args.mode,
            "target_words": args.target_words,
            "max_words": args.max_words,
            "overlap_sentences": args.overlap_sentences,
            "max_tokens": args.max_tokens or None,
            "token_count": "estimacion_determinista; reemplazar por tokenizer del encoder en Fase 3",
        },
        "resumen": {
            "documentos_pdf_manifest": sum(item.get("formato") == "pdf" for item in manifest),
            "documentos_procesados": 0,
            "documentos_sin_archivo": 0,
            "documentos_vacios": 0,
            "documentos_con_advertencias": 0,
            "chunks_generados": 0,
        },
        "documentos": [],
        "advertencias": [],
    }

    for item in manifest:
        if item.get("formato") != "pdf":
            continue
        path = resolve_text_path(item, args.input_root)
        doc_report: dict[str, Any] = {"doc_id": item.get("doc_id"), "fuente": item.get("fuente")}
        if path is None:
            report["resumen"]["documentos_sin_archivo"] += 1
            doc_report["estado"] = "sin_archivo"
            report["documentos"].append(doc_report)
            continue
        try:
            text = normalize_text(path.read_text(encoding="utf-8"))
            if not text:
                report["resumen"]["documentos_vacios"] += 1
                doc_report["estado"] = "vacio"
                report["documentos"].append(doc_report)
                continue
            chunks, warnings = make_chunks(text, args.target_words, args.max_words, args.overlap_sentences, args.max_tokens)
            for position, chunk in enumerate(chunks):
                records.append(build_record(item, chunk, position, args.mode))
            report["resumen"]["documentos_procesados"] += 1
            report["resumen"]["chunks_generados"] += len(chunks)
            if warnings:
                report["resumen"]["documentos_con_advertencias"] += 1
                report["advertencias"].extend({"doc_id": item.get("doc_id"), "mensaje": warning} for warning in warnings)
            doc_report.update({"estado": "procesado", "ruta_txt": str(path), "chunks": len(chunks), "advertencias": warnings})
            report["documentos"].append(doc_report)
        except Exception as exc:  # cada documento falla de forma auditable
            doc_report.update({"estado": "error", "error": str(exc)})
            report["advertencias"].append({"doc_id": item.get("doc_id"), "mensaje": str(exc)})
            report["documentos"].append(doc_report)

    (destination / "metadata.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (destination / "metadata.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    report["resumen"]["chunks_por_documento"] = dict(Counter(record["doc_id"] for record in records))
    (destination / "reporte_chunking.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Salida preparada en: {destination}")
    print(f"Chunks generados: {len(records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
