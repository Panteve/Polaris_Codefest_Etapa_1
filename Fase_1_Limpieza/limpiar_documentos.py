"""Extrae, limpia y normaliza documentos para CODEFEST AD ASTRA.

Este módulo deliberately no hace chunking ni embeddings. Su salida es texto
limpio y trazable, listo para la siguiente etapa del pipeline.

Dependencias opcionales:
    pypdf, beautifulsoup4, openpyxl, langdetect, pillow, pytesseract
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html as html_lib
import json
import logging
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


LOGGER = logging.getLogger("limpiar_documentos")
SUPPORTED = {
    ".pdf", ".html", ".htm", ".md", ".markdown", ".txt", ".json",
    ".csv", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".tif", ".tiff",
    ".pbf",
}
TEXT_FORMATS = {"pdf", "html", "md", "txt", "json", "csv", "xlsx", "xls", "image", "pbf"}


@dataclass
class Extraction:
    """Resultado uniforme devuelto por todos los extractores."""

    text: str
    method: str
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def sha256_file(path: Path) -> str:
    """Calcula el hash SHA-256 leyendo el archivo por bloques."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_text(path: Path) -> tuple[str, str]:
    """Lee el archivo probando UTF-8, Windows-1252 y Latin-1."""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8-replace"


def format_for(path: Path) -> str:
    """Convierte la extensión en el formato lógico usado por el pipeline."""
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in {".md", ".markdown"}:
        return "md"
    if suffix in {".xlsx", ".xls"}:
        return suffix[1:]
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        return "image"
    return suffix[1:]


def extract_pdf(path: Path) -> Extraction:
    """Extrae texto página por página con pypdf y reporta páginas vacías."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return Extraction("", "pypdf", ["Falta la dependencia opcional 'pypdf'."])

    reader = PdfReader(str(path))
    pages: list[str] = []
    warnings: list[str] = []
    for number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if not text.strip():
            warnings.append(f"La página {number} no produjo texto; podría requerir OCR.")
        pages.append(text.strip())
    return Extraction("\n\f\n".join(pages), "pypdf", warnings, {"paginas": len(pages)})


def extract_html(path: Path) -> Extraction:
    """Extrae texto visible de HTML y elimina elementos no semánticos."""
    source, encoding = read_text(path)
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        # Fallback conservador: elimina bloques que nunca son texto visible.
        text = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", source)
        text = re.sub(r"(?s)<[^>]+>", "\n", text)
        return Extraction(html_lib.unescape(text), "html_fallback", ["Falta 'beautifulsoup4'; se usó un extractor básico."], {"encoding": encoding})

    soup = BeautifulSoup(source, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "form", "aside"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    metadata: dict[str, Any] = {"encoding": encoding}
    if soup.title and soup.title.string:
        metadata["titulo"] = soup.title.string.strip()
    return Extraction(text, "beautifulsoup4", [], metadata)


TEXT_KEYS = {
    "title", "titulo", "headline", "body", "body_text", "body_paragraphs",
    "paragraphs", "content", "text", "article", "abstract", "summary", "section",
}
METADATA_KEYS = {"url", "date", "published", "authors", "author", "tags", "id", "source"}


def json_text(value: Any, key: str = "") -> list[str]:
    """Recorre JSON y conserva únicamente campos con contenido textual."""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(json_text(item, key))
        return result
    if isinstance(value, dict):
        result: list[str] = []
        for child_key, child in value.items():
            if child_key.lower() in TEXT_KEYS:
                result.extend(json_text(child, child_key))
        return result
    return []


def extract_json(path: Path) -> Extraction:
    """Interpreta un JSON estructurado y concatena sus campos textuales."""
    source, encoding = read_text(path)
    try:
        data = json.loads(source)
    except json.JSONDecodeError as exc:
        return Extraction("", "json", [f"JSON inválido: {exc.msg} en posición {exc.pos}."], {"encoding": encoding})
    pieces = json_text(data)
    warnings = [] if pieces else ["No se identificaron campos textuales conocidos en el JSON."]
    metadata = {"encoding": encoding, "campos_textuales": sorted(TEXT_KEYS)}
    if isinstance(data, dict):
        metadata["campos_metadata"] = sorted(k for k in data if k.lower() in METADATA_KEYS)
    return Extraction("\n\n".join(pieces), "json_estructurado", warnings, metadata)


def extract_csv(path: Path) -> Extraction:
    """Convierte cada fila CSV en pares explícitos columna-valor."""
    source, encoding = read_text(path)
    rows = list(csv.reader(source.splitlines()))
    if not rows:
        return Extraction("", "csv", ["CSV vacío."], {"encoding": encoding})
    headers = [cell.strip() or f"columna_{i + 1}" for i, cell in enumerate(rows[0])]
    lines: list[str] = []
    for row_number, row in enumerate(rows[1:], start=2):
        values = [f"{header}: {value.strip()}" for header, value in zip(headers, row) if value.strip()]
        if values:
            lines.append(f"[fila {row_number}] " + " | ".join(values))
    return Extraction("\n".join(lines), "csv", [], {"encoding": encoding, "columnas": headers, "filas": max(0, len(rows) - 1)})


def extract_xlsx(path: Path) -> Extraction:
    """Lee todas las hojas XLSX conservando hoja, fila, columna y valor."""
    try:
        import openpyxl
    except ImportError:
        return Extraction("", "openpyxl", ["Falta la dependencia opcional 'openpyxl'."])
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=False)
    lines: list[str] = []
    sheets: list[str] = []
    for sheet in workbook.worksheets:
        sheets.append(sheet.title)
        rows = sheet.iter_rows(values_only=True)
        headers = [str(value).strip() if value is not None else f"columna_{i + 1}" for i, value in enumerate(next(rows, ()), start=0)]
        for row_number, row in enumerate(rows, start=2):
            values = [f"{header}: {value}" for header, value in zip(headers, row) if value is not None and str(value).strip()]
            if values:
                lines.append(f"[hoja {sheet.title}, fila {row_number}] " + " | ".join(values))
    return Extraction("\n".join(lines), "openpyxl", [], {"hojas": sheets})


def extract_image(path: Path) -> Extraction:
    """Aplica OCR opcional a una imagen y registra resultados vacíos."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return Extraction("", "ocr", ["Faltan 'pillow' y/o 'pytesseract'; imagen pendiente de OCR."])
    text = pytesseract.image_to_string(Image.open(path))
    warnings = [] if text.strip() else ["OCR no produjo texto; revisar la imagen manualmente."]
    return Extraction(text, "pytesseract", warnings)


def extract(path: Path) -> Extraction:
    """Selecciona el extractor apropiado según la extensión del archivo."""
    kind = format_for(path)
    if kind == "pdf":
        return extract_pdf(path)
    if kind == "html":
        return extract_html(path)
    if kind in {"md", "markdown", "txt"}:
        text, encoding = read_text(path)
        return Extraction(text, "texto_plano", [], {"encoding": encoding})
    if kind == "json":
        return extract_json(path)
    if kind == "csv":
        return extract_csv(path)
    if kind in {"xlsx", "xls"}:
        return extract_xlsx(path)
    if kind == "image":
        return extract_image(path)
    if kind == "pbf":
        return Extraction("", "pbf_pendiente", ["PBF requiere un lector geoespacial; no se procesó automáticamente."])
    return Extraction("", "no_soportado", [f"Formato no soportado: {path.suffix or '(sin extensión)'}"])


def clean_text(text: str) -> tuple[str, list[str]]:
    """Normaliza texto sin resumir, traducir ni reescribir su contenido.

    También conserva párrafos, elimina caracteres de control y retira ruido de
    páginas solo cuando hay evidencia de repetición.
    """
    warnings: list[str] = []
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " "))
    text = "".join(char for char in text if char in "\n\t" or not unicodedata.category(char).startswith("C"))
    pages = re.split(r"\n\f\n|\f", text)
    if len(pages) > 1:
        text, removed = remove_repeated_page_lines(pages)
        if removed:
            warnings.append(f"Se eliminaron {removed} líneas repetitivas de páginas.")
    else:
        text = "\n".join(remove_page_number_lines(text.split("\n")))
    lines = []
    blank_pending = False
    for raw_line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if not line:
            blank_pending = True
            continue
        if blank_pending and lines:
            lines.append("")
        lines.append(line)
        blank_pending = False
    cleaned = "\n".join(lines).strip()
    if not cleaned:
        warnings.append("El texto limpio quedó vacío.")
    return cleaned, warnings


def remove_page_number_lines(lines: list[str]) -> list[str]:
    """Elimina líneas que contienen únicamente una numeración de página."""
    return [line for line in lines if not re.fullmatch(r"(?:página|page)?\s*[-–—]?\s*\d{1,4}\s*", line.strip(), re.IGNORECASE)]


def remove_repeated_page_lines(pages: list[str]) -> tuple[str, int]:
    """Retira líneas repetidas en al menos la mitad de las páginas."""
    page_lines = [page.split("\n") for page in pages]
    counts = Counter(line.strip() for lines in page_lines for line in lines if line.strip())
    threshold = max(2, (len(pages) + 1) // 2)
    repeated = {line for line, count in counts.items() if count >= threshold and len(line) <= 180}
    removed = 0
    result: list[str] = []
    for lines in page_lines:
        for line in remove_page_number_lines(lines):
            if line.strip() in repeated:
                removed += 1
                continue
            result.append(line)
        result.append("")
    return "\n".join(result), removed


def detect_language(text: str) -> str:
    """Detecta idioma con langdetect o un fallback léxico conservador."""
    sample = " ".join(text.split())[:5000]
    if len(sample.split()) < 20:
        return "unknown"
    try:
        from langdetect import detect
        detected = detect(sample)
        return detected if detected in {"es", "en", "pt"} else detected
    except Exception:
        scores = {
            "es": sum(sample.lower().split().count(word) for word in {"el", "la", "los", "las", "que", "del", "para", "una"}),
            "en": sum(sample.lower().split().count(word) for word in {"the", "and", "of", "for", "with", "from", "this"}),
            "pt": sum(sample.lower().split().count(word) for word in {"o", "a", "os", "as", "que", "para", "uma", "dos"}),
        }
        best = max(scores, key=scores.get)
        return best if scores[best] >= 2 else "unknown"


def load_manifest(path: Path) -> dict[str, dict[str, Any]]:
    """Carga el manifiesto anterior indexado por fuente relativa."""
    if not path.exists():
        return {}
    result: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            result[item["fuente"]] = item
    return result


def next_doc_id(manifest: Iterable[dict[str, Any]]) -> str:
    """Obtiene el siguiente identificador estable con formato DOC-000001."""
    numbers = [int(match.group(1)) for item in manifest if (match := re.fullmatch(r"DOC-(\d{6})", item.get("doc_id", "")))]
    return f"DOC-{max(numbers, default=0) + 1:06d}"


def process(input_dir: Path, output_dir: Path, fenomeno: int | None = None) -> dict[str, int]:
    """Procesa archivos, escribe textos y genera manifiesto y reporte.

    Los originales solo se leen. Si una fuente ya existe en el manifiesto,
    conserva su doc_id para que las ejecuciones posteriores sean reproducibles.
    """
    original_root = input_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "extraidos").mkdir(exist_ok=True)
    (output_dir / "limpios").mkdir(exist_ok=True)
    old_manifest = load_manifest(output_dir / "manifiesto.jsonl")
    entries: list[dict[str, Any]] = []
    files = sorted(path for path in input_dir.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED)
    existing = list(old_manifest.values())
    counters = Counter()
    for path in files:
        source = path.resolve().relative_to(original_root).as_posix()
        previous = old_manifest.get(source)
        doc_id = previous["doc_id"] if previous else next_doc_id(existing + entries)
        extraction = extract(path)
        raw_path = output_dir / "extraidos" / f"{doc_id}.txt"
        raw_path.write_text(extraction.text, encoding="utf-8")
        cleaned, clean_warnings = clean_text(extraction.text)
        clean_path = output_dir / "limpios" / f"{doc_id}.txt"
        clean_path.write_text(cleaned, encoding="utf-8")
        warnings = extraction.warnings + clean_warnings
        entry = {
            "doc_id": doc_id,
            "fuente": source,
            "formato": format_for(path),
            "fenomeno": fenomeno,
            "tamano_bytes": path.stat().st_size,
            "checksum": sha256_file(path),
            "estado": "procesado" if cleaned and not warnings else ("procesado_con_advertencias" if cleaned else "fallido"),
            "idioma": detect_language(cleaned),
            "metodo_extraccion": extraction.method,
            "advertencias": warnings,
            "conteo": {
                "caracteres_bruto": len(extraction.text),
                "caracteres_limpio": len(cleaned),
                "palabras_bruto": len(extraction.text.split()),
                "palabras_limpio": len(cleaned.split()),
                "lineas_limpio": len(cleaned.splitlines()),
            },
            "archivo_extraido": f"extraidos/{doc_id}.txt",
            "archivo_limpio": f"limpios/{doc_id}.txt",
            "version_pipeline": "1.0.0",
            **extraction.metadata,
        }
        entries.append(entry)
        counters[entry["estado"]] += 1
    entries.sort(key=lambda item: item["fuente"])
    (output_dir / "manifiesto.jsonl").write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in entries), encoding="utf-8")
    (output_dir / "reporte_calidad.json").write_text(json.dumps({"total": len(entries), "estados": counters, "version_pipeline": "1.0.0"}, ensure_ascii=False, indent=2, default=dict), encoding="utf-8")
    return dict(counters)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Define la interfaz de línea de comandos."""
    parser = argparse.ArgumentParser(description="Extrae y limpia documentos para CODEFEST AD ASTRA.")
    parser.add_argument("input_dir", type=Path, help="Directorio con archivos originales.")
    parser.add_argument("output_dir", type=Path, help="Directorio de salida del pipeline.")
    parser.add_argument("--fenomeno", type=int, choices=(1, 2, 3), help="Fenómeno aplicado a todos los documentos, si corresponde.")
    parser.add_argument("--verbose", action="store_true", help="Muestra información de procesamiento.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Valida argumentos, ejecuta el pipeline y devuelve el código de salida."""
    args = parse_args(argv or sys.argv[1:])
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s: %(message)s")
    if not args.input_dir.is_dir():
        LOGGER.error("El directorio de entrada no existe: %s", args.input_dir)
        return 2
    summary = process(args.input_dir, args.output_dir, args.fenomeno)
    LOGGER.info("Procesamiento terminado: %s", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
