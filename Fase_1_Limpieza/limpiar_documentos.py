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
import io
import json
import logging
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger("limpiar_documentos")
YELLOW = "\033[93m"
RESET = "\033[0m"
SUPPORTED = {
    ".pdf", ".html", ".htm", ".md", ".markdown", ".txt", ".json",
    ".csv", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".tif", ".tiff",
    ".pbf",
}
TEXT_FORMATS = {"pdf", "html", "md", "txt", "json", "csv", "xlsx", "xls", "image", "pbf"}
EXCLUDED_KNOWLEDGE_PATHS = {
    "DAIO/daio_pdfs/DAIO_catalog-2.json",
    "DAIO/daio_pdfs/DAIO_catalog-2.csv",
    "Defensa21_LatAm/defensa21_data/DEFENSA21_articulos-2.json",
    "Defensa21_LatAm/defensa21_data/DEFENSA21_catalog-2.json",
    "RutaN_GEIAL/rutan_pdfs/RUTAN_catalog-2.json",
    "RutaN_GEIAL/rutan_pdfs/RUTAN_catalog-2.csv",
    "CSIS_Aerospace/csis_pdfs/CSIS_catalog-2.json",
    "CSIS_Aerospace/csis_pdfs/CSIS_catalog-2.csv",
    "SWF_Counterspace/swf_counterspace_2026/SWF_report-data.json",
    "SWF_Counterspace/swf_counterspace_2026/SWF_report-data.csv",
    "Amazon_Underworld/AMAZONUW_tiles-index.json",
    "CEEEP/ceeep_catalogo.json",
    "CEEEP/ceeep_registro.json",
    "CEOBS/ceobs_full_catalogo.json",
    "CEOBS/ceobs_full_registro.json",
    "MAPP_OEA/mapp_catalogo.json",
    "MAPP_OEA/mapp_registro.json",
    "MAPP_OEA/oea/mapp_oea_informes/MAPPOEA_mapp-catalog.json",
    "MAPP_OEA/oea/mapp_oea_informes/MAPPOEA_mapp-catalog.csv",
    "RESDAL/resdal_catalogo.json",
    "RESDAL/resdal_registro.json",
    "RESDAL/resdal_atlas/RESDAL_catalog-2.json",
    "RESDAL/resdal_atlas/RESDAL_catalog-2.csv",
    "SIPRI/sipri_full_catalogo.json",
    "SIPRI/sipri_full_registro.json",
    "SIPRI/sipri_data/SIPRI_catalog-2.json",
    "SIPRI/sipri_data/SIPRI_publicaciones-2.csv",
    "CEOBS/ceobs_data/CEOBS_publicaciones-2.csv",
    "AI_Index_Stanford/recursos/Healthcare_Medicine/datasets/AIINDEX_lit-covid-ai-covid-literature-xlsx.xlsx",
    "AI_Index_Stanford/recursos/Research_Development/datasets/AIINDEX_mag-author-lifecycle-xlsx.xlsx",
    "AI_Index_Stanford/recursos/Research_Development/datasets/AIINDEX_mag-conferences-list-xlsx.xlsx",
    "AI_Index_Stanford/recursos/Research_Development/datasets/AIINDEX_mag-publications-fields-xlsx.xlsx",
}


@dataclass
class Extraction:
    """Resultado uniforme devuelto por todos los extractores."""

    text: str
    method: str
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def read_text(path: Path) -> tuple[str, str]:
    """Lee el archivo probando UTF-8, Windows-1252 y Latin-1."""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8-replace"


def sanitize_unicode(text: str) -> tuple[str, int]:
    """Reemplaza surrogates aislados que no pueden serializarse como UTF-8."""
    sanitized = text.encode("utf-8", errors="replace").decode("utf-8")
    return sanitized, sum(1 for char in text if unicodedata.category(char) == "Cs")


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

    pages: list[str] = []
    warnings: list[str] = []
    try:
        reader = PdfReader(str(path))
        for number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                warnings.append(f"La página {number} no produjo texto; podría requerir OCR.")
            pages.append(text.strip())
    except Exception as exc:
        warnings.append(
            f"No se pudo extraer completamente el PDF ({type(exc).__name__}): {exc}"
        )
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
METADATA_KEYS = {
    "url", "date", "published", "authors", "author", "tags", "id", "source",
    "license", "language", "lang", "created_at", "updated_at", "src", "href",
    "detail_url", "pdf_url", "doi",
}
JSON_IGNORED_KEYS = {"links", "pdf_links", "doc_links"}


def json_text(value: Any, key: str = "", path: str = "") -> list[str]:
    """Convierte un JSON en l?neas textuales etiquetadas y trazables."""
    normalized_key = key.lower()
    if normalized_key in JSON_IGNORED_KEYS:
        return []
    if isinstance(value, str):
        stripped_value = value.strip()
        if (
            not stripped_value
            or key.lower() in METADATA_KEYS
            or stripped_value.lower().startswith(("data:image/", "data:application/"))
        ):
            return []
        label = path or key
        return [f"{label}: {stripped_value}" if label else stripped_value]
    if isinstance(value, list):
        result: list[str] = []
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]" if path else f"{key}[{index}]"
            result.extend(json_text(item, key, item_path))
        return result
    if isinstance(value, dict):
        result: list[str] = []
        for child_key, child in value.items():
            if child_key.lower() in METADATA_KEYS or child_key.lower() in JSON_IGNORED_KEYS:
                continue
            child_path = f"{path}.{child_key}" if path else child_key
            result.extend(json_text(child, child_key, child_path))
        return result
    return []


def extract_json(path: Path) -> Extraction:
    """Interpreta un JSON estructurado y concatena sus campos textuales."""
    source, encoding = read_text(path)
    try:
        data = json.loads(source)
    except json.JSONDecodeError as exc:
        return Extraction("", "json", [f"JSON inválido: {exc.msg} en posición {exc.pos}."], {"encoding": encoding})
    raw_pieces = json_text(data)
    pieces: list[str] = []
    seen_values: set[str] = set()
    for piece in raw_pieces:
        value = piece.split(": ", 1)[1] if ": " in piece else piece
        normalized_value = re.sub(r"\s+", " ", value.strip()).casefold()
        if normalized_value and normalized_value in seen_values:
            continue
        if normalized_value:
            seen_values.add(normalized_value)
        pieces.append(piece)
    warnings = [] if pieces else ["No se identificaron campos textuales conocidos en el JSON."]
    metadata = {
        "encoding": encoding,
        "campos_textuales": sorted(TEXT_KEYS),
        "duplicados_textuales_omitidos": len(raw_pieces) - len(pieces),
    }
    if isinstance(data, dict):
        metadata["campos_metadata"] = sorted(k for k in data if k.lower() in METADATA_KEYS)
    return Extraction("\n\n".join(pieces), "json_estructurado", warnings, metadata)


def extract_csv(path: Path) -> Extraction:
    """Convierte cada fila CSV en pares explícitos columna-valor."""
    source, encoding = read_text(path)
    warnings: list[str] = []
    delimiter = ","
    try:
        delimiter = csv.Sniffer().sniff(source[:8192], delimiters=",;\t|").delimiter
    except csv.Error:
        warnings.append("No se pudo detectar el delimitador; se uso coma.")
    try:
        rows = list(csv.reader(io.StringIO(source, newline=""), delimiter=delimiter))
    except csv.Error as exc:
        return Extraction(
            "",
            "csv",
            warnings + [f"CSV invalido: {exc}"],
            {"encoding": encoding, "delimitador": delimiter},
        )
    if not rows:
        return Extraction("", "csv", ["CSV vacío."], {"encoding": encoding})
    headers = [cell.strip() or f"columna_{i + 1}" for i, cell in enumerate(rows[0])]
    max_columns = max((len(row) for row in rows), default=len(headers))
    headers.extend(f"columna_{i + 1}" for i in range(len(headers), max_columns))
    lines: list[str] = []
    irregular_rows: list[int] = []
    for row_number, row in enumerate(rows[1:], start=2):
        if not row or not any(value.strip() for value in row):
            continue
        if len(row) != len(headers):
            irregular_rows.append(row_number)
        values = [
            f"{header}: {row[index].strip()}"
            for index, header in enumerate(headers)
            if index < len(row) and row[index].strip()
        ]
        if values:
            lines.append(f"[fila {row_number}] " + " | ".join(values))
    if irregular_rows:
        warnings.append(
            "Filas con numero de columnas distinto al encabezado: "
            + ", ".join(str(row) for row in irregular_rows[:20])
            + (" ..." if len(irregular_rows) > 20 else ".")
        )
    metadata = {
        "encoding": encoding,
        "delimitador": delimiter,
        "columnas": headers,
        "filas": len(lines),
        "filas_irregulares": len(irregular_rows),
    }
    return Extraction("\n".join(lines), "csv", warnings, metadata)


def pbf_tile_coordinates(path: Path) -> tuple[str, str, str] | None:
    """Infiere z/x/y desde rutas tipo tiles/<z>/<x>/PREFIJO_<y>.pbf."""
    if len(path.parts) < 4:
        return None
    try:
        tiles_index = [part.lower() for part in path.parts].index("tiles")
    except ValueError:
        return None
    if tiles_index + 2 >= len(path.parts):
        return None
    match = re.search(r"_(\d+)$", path.stem)
    if not match:
        return None
    return path.parts[tiles_index + 1], path.parts[tiles_index + 2], match.group(1)


def pbf_companion_csv(path: Path) -> Path | None:
    """Busca un CSV decodificado junto al directorio tiles de la fuente."""
    try:
        tiles_index = [part.lower() for part in path.parts].index("tiles")
    except ValueError:
        return None
    source_root = Path(*path.parts[:tiles_index])
    candidates = sorted(source_root.glob("*amazonunderworld-data.csv"))
    if candidates:
        return candidates[0]
    candidates = sorted(source_root.glob("*data.csv"))
    return candidates[0] if candidates else None


def row_to_pairs(row: dict[str, str], skip_fields: set[str] | None = None) -> str:
    """Convierte una fila estructurada a pares columna: valor, omitiendo vacios."""
    skip_fields = skip_fields or set()
    pairs = []
    for key, value in row.items():
        if key in skip_fields or not value or not str(value).strip():
            continue
        clean_value = re.sub(r"\s+", " ", str(value).strip())
        pairs.append(f"{key}: {clean_value}")
    return " | ".join(pairs)


def extract_pbf_from_companion_csv(path: Path) -> Extraction | None:
    """Usa CSV hermano ya decodificado para representar un tile PBF como filas."""
    coordinates = pbf_tile_coordinates(path)
    companion = pbf_companion_csv(path)
    if not coordinates or not companion or not companion.is_file():
        return None
    z, x, y = coordinates
    source, encoding = read_text(companion)
    rows = csv.DictReader(io.StringIO(source, newline=""))
    lines: list[str] = []
    for row in rows:
        if row.get("tile_zoom") != z or row.get("tile_x") != x or row.get("tile_y") != y:
            continue
        line = row_to_pairs(row, {"tile_zoom", "tile_x", "tile_y"})
        if not line:
            continue
        lines.append(line)
    warnings = [] if lines else [f"No se encontraron filas en {companion.name} para tile z={z}, x={x}, y={y}."]
    return Extraction(
        "\n".join(lines),
        "pbf_csv_decodificado",
        warnings,
        {
            "encoding": encoding,
            "csv_companero": companion.name,
            "tile_zoom": z,
            "tile_x": x,
            "tile_y": y,
            "filas": len(lines),
        },
    )


def extract_pbf_direct(path: Path) -> Extraction:
    """Decodifica Mapbox Vector Tiles si la dependencia opcional existe."""
    try:
        import mapbox_vector_tile
    except ImportError:
        return Extraction(
            "",
            "pbf_pendiente",
            ["PBF requiere 'mapbox-vector-tile' o un CSV companero decodificado; no se proceso automaticamente."],
        )
    try:
        decoded = mapbox_vector_tile.decode(path.read_bytes())
    except Exception as exc:
        return Extraction("", "mapbox_vector_tile", [f"No se pudo decodificar PBF ({type(exc).__name__}): {exc}"])
    lines: list[str] = []
    for layer_name, layer in decoded.items():
        features = layer.get("features", []) if isinstance(layer, dict) else []
        for feature in features:
            properties = dict(feature.get("properties") or {})
            if feature.get("id") is not None:
                properties = {"fid": str(feature["id"]), **properties}
            line = row_to_pairs({"layer": layer_name, **{k: str(v) for k, v in properties.items()}})
            if line:
                lines.append(line)
    warnings = [] if lines else ["El PBF se decodifico, pero no produjo atributos textuales utiles."]
    return Extraction("\n".join(lines), "mapbox_vector_tile", warnings, {"filas": len(lines)})


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
        direct = extract_pbf_direct(path)
        if direct.text.strip() or direct.method != "pbf_pendiente":
            return direct
        fallback = extract_pbf_from_companion_csv(path)
        if fallback:
            fallback.warnings = direct.warnings + fallback.warnings
            fallback.metadata["fallback_de"] = direct.method
            return fallback
        return direct
    return Extraction("", "no_soportado", [f"Formato no soportado: {path.suffix or '(sin extensión)'}"])


MOJIBAKE_PATTERN = re.compile(r"(?:\u00c3.|\u00c2.|\u00e2(?:\u20ac|\u2013|\u2014|\u2026)|\u00cb\u0153|\ufffd)")


def repair_mojibake(text: str) -> tuple[str, int]:
    """Corrige UTF-8 mal interpretado solo si reduce patrones sospechosos."""
    best = text
    best_score = len(MOJIBAKE_PATTERN.findall(text))
    for encoding in ("latin-1", "cp1252"):
        try:
            candidate = text.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        score = len(MOJIBAKE_PATTERN.findall(candidate))
        if score < best_score:
            best, best_score = candidate, score
    return best, len(MOJIBAKE_PATTERN.findall(text)) - best_score


def quality_warnings(text: str, format_name: str) -> list[str]:
    """Detecta salidas no vac?as que carecen de contenido ?til."""
    if format_name != "pdf":
        return []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) >= 3 and len(set(lines)) == 1:
        return ["[CRITICO] El PDF contiene unicamente una linea repetida; requiere OCR o reemplazo."]
    return []

def clean_text(text: str, format_name: str = "") -> tuple[str, list[str]]:
    """Normaliza texto sin resumir, traducir ni reescribir su contenido.

    También conserva párrafos, elimina caracteres de control y retira ruido de
    páginas solo cuando hay evidencia de repetición.
    """
    warnings: list[str] = []
    text, repaired = repair_mojibake(text)
    if repaired:
        warnings.append(f"Se repararon {repaired} secuencias de codificacion sospechosas.")
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " "))
    # Conservamos el separador de página hasta retirar cabeceras y pies repetidos.
    text = "".join(char for char in text if char in "\n\t\f" or not unicodedata.category(char).startswith("C"))
    pages = re.split(r"\n\f\n|\f", text)
    if len(pages) > 1:
        text, removed = remove_repeated_page_lines(pages)
        if removed:
            warnings.append(f"Se eliminaron {removed} líneas repetitivas de páginas.")
    else:
        text = "\n".join(remove_page_number_lines(text.split("\n")))
    if format_name == "pdf":
        text = "\n".join(
            line for line in text.split("\n")
            if not re.fullmatch(r"!\s*!|!\s*\d{1,4}", line.strip())
        )
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


def write_manifest(path: Path, entries: list[dict[str, Any]]) -> None:
    """Escribe el manifiesto completo con formato JSON legible."""
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        temporary.replace(path)
    except PermissionError as exc:
        raise PermissionError(
            f"No se puede actualizar {path}; cierra el manifiesto si está abierto en otro programa."
        ) from exc


def supported_files(input_dir: Path) -> list[Path]:
    """Devuelve los documentos reconocidos en orden estable."""
    return sorted(
        path for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED
    )


def automatic_start_id(input_dir: Path, fenomeno: int | None) -> int:
    """Calcula el primer ID contando los fenómenos anteriores del mismo nivel."""
    if fenomeno is None:
        return 1
    previous_total = 0
    for sibling in input_dir.parent.iterdir():
        if not sibling.is_dir():
            continue
        match = re.match(r"^F(\d+)(?:_|$)", sibling.name, re.IGNORECASE)
        if match and int(match.group(1)) < fenomeno:
            previous_total += len(supported_files(sibling))
    return previous_total + 1


def read_manifest(path: Path) -> list[dict[str, Any]]:
    """Lee el progreso anterior; devuelve una lista vacía si no existe."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def merge_phenomenon_manifests(output_dir: Path) -> list[dict[str, Any]]:
    """Reconstruye el global desde los manifiestos granulares sin borrar datos."""
    global_entries = read_manifest(output_dir / "manifiesto_global.json")
    merged = {item.get("ruta_original"): item for item in global_entries if item.get("ruta_original")}
    for phenomenon_dir in output_dir.iterdir():
        if not phenomenon_dir.is_dir() or not re.match(r"^F\d+(?:_|$)", phenomenon_dir.name, re.IGNORECASE):
            continue
        manifest_path = phenomenon_dir / "manifiesto.json"
        if not manifest_path.exists():
            continue
        phenomenon_name = phenomenon_dir.name
        for item in read_manifest(manifest_path):
            local_source = item.get("ruta_original")
            if not local_source:
                continue
            global_source = item.get("ruta_global") or f"{phenomenon_name}/{local_source}"
            global_item = dict(item)
            global_item["ruta_original"] = global_source
            global_item["ruta_global"] = global_source
            merged[global_source] = global_item
    return sorted(merged.values(), key=lambda item: item.get("doc_id", ""))


def normalized_content_hash(text: str) -> str:
    """Hash estable para detectar salidas textuales equivalentes."""
    normalized = re.sub(r"\s+", " ", text.strip()).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def pbf_line_hash(line: str) -> str:
    """Hash de fila PBF sin depender de saltos o espacios incidentales."""
    return normalized_content_hash(line)


def pbf_field_value(line: str, field: str) -> str:
    """Extrae un valor de una fila tipo campo: valor | campo: valor."""
    pattern = rf"(?:^|\|)\s*{re.escape(field)}:\s*(.*?)(?=\s*\|\s*[^|]+:\s*|$)"
    match = re.search(pattern, line)
    return match.group(1).strip() if match else ""


def pbf_entity_key(line: str) -> str:
    """Clave estable para no repetir la misma entidad territorial entre tiles."""
    for field in ("au_ID_concatenated", "b_ID_concatenated"):
        value = pbf_field_value(line, field)
        if value:
            return f"{field}:{value.casefold()}"
    adm1 = pbf_field_value(line, "b_ADM1_PCODE")
    adm2 = pbf_field_value(line, "b_ADM2_PCODE")
    if adm1 or adm2:
        return f"admin:{adm1.casefold()}:{adm2.casefold()}"
    layer = pbf_field_value(line, "layer")
    fid = pbf_field_value(line, "fid")
    if layer or fid:
        return f"feature:{layer.casefold()}:{fid.casefold()}"
    return pbf_line_hash(line)


def pbf_context_key(path: Path, original_root: Path) -> str:
    """Agrupa tiles PBF por la fuente que contiene el directorio tiles."""
    source = path.resolve().relative_to(original_root).as_posix()
    parts = source.split("/")
    lowered = [part.lower() for part in parts]
    if "tiles" in lowered:
        tiles_index = lowered.index("tiles")
        return "/".join(parts[:tiles_index]) or "."
    return str(Path(source).parent).replace("\\", "/")


def process(
    input_dir: Path,
    output_dir: Path,
    fenomeno: int | None = None,
    formatos: set[str] | None = None,
    id_inicial: int | None = None,
) -> dict[str, int]:
    """Procesa formatos seleccionados y replica la estructura de entrada.

    Los doc_id se asignan según la posición global de cada documento reconocido
    en el orden ordenado de la entrada, aunque el formato quede filtrado.
    """
    original_root = input_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    phenomenon_output_dir = output_dir / input_dir.name
    phenomenon_output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = phenomenon_output_dir / "manifiesto.json"
    global_manifest_path = output_dir / "manifiesto_global.json"
    entries = read_manifest(manifest_path)
    global_entries = merge_phenomenon_manifests(output_dir)
    write_manifest(manifest_path, entries)
    write_manifest(global_manifest_path, global_entries)
    all_files = supported_files(input_dir)
    for directory in input_dir.rglob("*"):
        if directory.is_dir():
            (phenomenon_output_dir / directory.relative_to(input_dir)).mkdir(parents=True, exist_ok=True)
    positions = {path: position for position, path in enumerate(all_files, start=1)}
    files = [path for path in all_files if not formatos or format_for(path) in formatos]
    start_id = id_inicial if id_inicial is not None else automatic_start_id(input_dir, fenomeno)
    print(f"Inicio de numeración global: DOC-{start_id:06d}", flush=True)
    completed = {
        entry["ruta_original"]: entry
        for entry in entries
        if entry.get("estado") in {"procesado", "procesado_con_advertencias"}
        and (output_dir / entry.get("ruta_limpio", "")).is_file()
    }
    rebuild_pbf = not formatos or "pbf" in formatos
    seen_content_hashes: dict[str, dict[str, Any]] = {}
    seen_pbf_rows: set[str] = set()
    for entry in entries:
        if entry.get("estado") not in {"procesado", "procesado_con_advertencias"}:
            continue
        if rebuild_pbf and entry.get("formato") == "pbf":
            continue
        clean_file = output_dir / entry.get("ruta_limpio", "")
        if not clean_file.is_file():
            continue
        content = clean_file.read_text(encoding="utf-8")
        content_hash = entry.get("contenido_hash") or normalized_content_hash(content)
        if content_hash:
            seen_content_hashes.setdefault(content_hash, entry)
        if entry.get("formato") == "pbf":
            for line in content.splitlines():
                entity_key = pbf_entity_key(line)
                if entity_key:
                    seen_pbf_rows.add(entity_key)
    pbf_consolidates: dict[str, dict[str, Any]] = {}
    counters = Counter()
    total_files = len(files)
    for position, path in enumerate(files, start=1):
        original_position = positions[path]
        doc_id = f"DOC-{start_id + original_position - 1:06d}"
        source = path.resolve().relative_to(original_root).as_posix()
        if source in EXCLUDED_KNOWLEDGE_PATHS:
            print(f"[{position}/{total_files}] Excluido del indice: {path.name} ({doc_id})", flush=True)
            excluded_entry = {
                "doc_id": doc_id,
                "fuente": path.stem,
                "ruta_original": source,
                "ruta_global": f"{input_dir.name}/{source}",
                "formato": format_for(path),
                "fenomeno": fenomeno,
                "tamano_bytes": path.stat().st_size,
                "estado": "excluido_no_contenido",
                "apto_para_indice": False,
                "motivo_exclusion": "Reporte o catalogo tecnico del scraper; no contiene contenido de conocimiento para vectorizar.",
                "advertencias": [],
                "version_pipeline": "1.1.0",
            }
            entries = [item for item in entries if item.get("ruta_original") != source]
            entries.append(excluded_entry)
            global_entry = dict(excluded_entry)
            global_entry["ruta_original"] = excluded_entry["ruta_global"]
            global_entries = [
                item for item in global_entries
                if item.get("ruta_original") != global_entry["ruta_original"]
            ]
            global_entries.append(global_entry)
            counters[excluded_entry["estado"]] += 1
            entries.sort(key=lambda item: item["doc_id"])
            global_entries.sort(key=lambda item: item["doc_id"])
            write_manifest(manifest_path, entries)
            write_manifest(global_manifest_path, global_entries)
            continue
        if source in completed and format_for(path) != "pbf":
            print(f"[{position}/{total_files}] Omitido, ya procesado: {path.name} ({doc_id})", flush=True)
            completed_entry = completed[source]
            global_source = f"{input_dir.name}/{source}"
            if not any(item.get("ruta_original") == global_source for item in global_entries):
                global_entry = dict(completed_entry)
                global_entry["ruta_original"] = global_source
                global_entries.append(global_entry)
                global_entries.sort(key=lambda item: item["doc_id"])
                write_manifest(global_manifest_path, global_entries)
            counters[completed_entry["estado"]] += 1
            continue
        print(f"[{position}/{total_files}] Procesando: {path.name} ({doc_id})", flush=True)
        extraction = extract(path)
        extraction.text, surrogate_count = sanitize_unicode(extraction.text)
        if surrogate_count:
            extraction.warnings.append(
                f"Se reemplazaron {surrogate_count} caracteres no válidos para UTF-8."
            )
        format_name = format_for(path)
        cleaned, clean_warnings = clean_text(extraction.text, format_name)
        content_hash = normalized_content_hash(cleaned)
        relative_source = Path(source)
        clean_path = phenomenon_output_dir / relative_source.parent / f"{doc_id}.txt"
        clean_path.parent.mkdir(parents=True, exist_ok=True)
        warnings = extraction.warnings + clean_warnings + quality_warnings(cleaned, format_name)
        if format_name == "pbf":
            context_key = pbf_context_key(path, original_root)
            unique_lines: list[str] = []
            duplicate_rows = 0
            for line in cleaned.splitlines():
                entity_key = pbf_entity_key(line)
                if not entity_key:
                    continue
                if entity_key in seen_pbf_rows:
                    duplicate_rows += 1
                    continue
                seen_pbf_rows.add(entity_key)
                unique_lines.append(line)
            if duplicate_rows:
                warnings.append(f"Se omitieron {duplicate_rows} filas PBF duplicadas ya vistas en tiles anteriores.")
            group = pbf_consolidates.get(context_key)
            if group and unique_lines:
                group["lines"].extend(unique_lines)
                group["sources"].append(source)
                group["tiles"] += 1
                group["raw_chars"] += len(extraction.text)
                group["raw_words"] += len(extraction.text.split())
                consolidated_text = "\n".join(group["lines"])
                group["clean_path"].write_text(consolidated_text, encoding="utf-8")
                group_entry = group["entry"]
                group_entry["conteo"] = {
                    "caracteres_bruto": group["raw_chars"],
                    "caracteres_limpio": len(consolidated_text),
                    "palabras_bruto": group["raw_words"],
                    "palabras_limpio": len(consolidated_text.split()),
                    "lineas_limpio": len(consolidated_text.splitlines()),
                }
                group_entry["contenido_hash"] = normalized_content_hash(consolidated_text)
                group_entry["filas_unicas_limpias"] = len(group["lines"])
                group_entry["pbf_tiles_consolidados"] = group["tiles"]
                group_entry["pbf_fuentes_cubiertas"] = group["sources"]
                entries = [item for item in entries if item.get("ruta_original") != group_entry["ruta_original"]]
                entries.append(group_entry)
                global_entry = dict(group_entry)
                global_entry["ruta_original"] = group_entry["ruta_global"]
                global_entries = [
                    item for item in global_entries
                    if item.get("ruta_original") != global_entry["ruta_original"]
                ]
                global_entries.append(global_entry)
            if group:
                if clean_path.exists():
                    clean_path.unlink()
                covered_entry = {
                    "doc_id": doc_id,
                    "fuente": path.stem,
                    "ruta_original": source,
                    "ruta_global": f"{input_dir.name}/{source}",
                    "formato": format_name,
                    "fenomeno": fenomeno,
                    "tamano_bytes": path.stat().st_size,
                    "estado": "excluido_duplicado",
                    "apto_para_indice": False,
                    "motivo_exclusion": "Contenido PBF cubierto por el TXT consolidado del primer tile de la misma fuente/contexto.",
                    "duplicado_de_doc_id": group["entry"]["doc_id"],
                    "duplicado_de_fuente": group["entry"]["fuente"],
                    "deduplicacion": "consolidado_pbf",
                    "idioma": detect_language("\n".join(unique_lines)),
                    "metodo_extraccion": extraction.method,
                    "advertencias": warnings,
                    "version_pipeline": "1.1.0",
                    "pbf_contexto": context_key,
                    "pbf_consolidado_en": group["entry"]["doc_id"],
                    "filas_duplicadas_omitidas": duplicate_rows,
                    "filas_agregadas_al_consolidado": len(unique_lines),
                    **extraction.metadata,
                }
                entries = [item for item in entries if item.get("ruta_original") != source]
                entries.append(covered_entry)
                global_entry = dict(covered_entry)
                global_entry["ruta_original"] = covered_entry["ruta_global"]
                global_entries = [
                    item for item in global_entries
                    if item.get("ruta_original") != global_entry["ruta_original"]
                ]
                global_entries.append(global_entry)
                counters[covered_entry["estado"]] += 1
                entries.sort(key=lambda item: item["doc_id"])
                global_entries.sort(key=lambda item: item["doc_id"])
                write_manifest(manifest_path, entries)
                write_manifest(global_manifest_path, global_entries)
                print(f"[{position}/{total_files}] Cubierto por consolidado PBF: {path.name} ({doc_id})", flush=True)
                continue
            if extraction.text.strip() and not unique_lines:
                print(f"[{position}/{total_files}] Excluido por duplicado: {path.name} ({doc_id})", flush=True)
                if clean_path.exists():
                    clean_path.unlink()
                duplicate_entry = {
                    "doc_id": doc_id,
                    "fuente": path.stem,
                    "ruta_original": source,
                    "ruta_global": f"{input_dir.name}/{source}",
                    "formato": format_name,
                    "fenomeno": fenomeno,
                    "tamano_bytes": path.stat().st_size,
                    "estado": "excluido_duplicado",
                    "apto_para_indice": False,
                    "motivo_exclusion": "Todas las filas utiles del PBF ya estaban representadas en fuentes anteriores.",
                    "duplicado_de_doc_id": None,
                    "duplicado_de_fuente": None,
                    "deduplicacion": "filas_pbf",
                    "idioma": "unknown",
                    "metodo_extraccion": extraction.method,
                    "advertencias": warnings,
                    "version_pipeline": "1.1.0",
                    "pbf_contexto": context_key,
                    "filas_duplicadas_omitidas": duplicate_rows,
                    "filas_unicas_limpias": 0,
                    **extraction.metadata,
                }
                entries = [item for item in entries if item.get("ruta_original") != source]
                entries.append(duplicate_entry)
                global_entry = dict(duplicate_entry)
                global_entry["ruta_original"] = duplicate_entry["ruta_global"]
                global_entries = [
                    item for item in global_entries
                    if item.get("ruta_original") != global_entry["ruta_original"]
                ]
                global_entries.append(global_entry)
                counters[duplicate_entry["estado"]] += 1
                entries.sort(key=lambda item: item["doc_id"])
                global_entries.sort(key=lambda item: item["doc_id"])
                write_manifest(manifest_path, entries)
                write_manifest(global_manifest_path, global_entries)
                continue
            cleaned = "\n".join(unique_lines)
            content_hash = normalized_content_hash(cleaned)
        duplicate_of = seen_content_hashes.get(content_hash) if content_hash else None
        if duplicate_of:
            warnings.append(f"Contenido duplicado de {duplicate_of.get('doc_id')} ({duplicate_of.get('ruta_original')}).")
        if duplicate_of or (format_name == "pbf" and extraction.text.strip() and not cleaned):
            print(f"[{position}/{total_files}] Excluido por duplicado: {path.name} ({doc_id})", flush=True)
            row_duplicate_only = not duplicate_of and format_name == "pbf"
            if clean_path.exists():
                clean_path.unlink()
            duplicate_entry = {
                "doc_id": doc_id,
                "fuente": path.stem,
                "ruta_original": source,
                "ruta_global": f"{input_dir.name}/{source}",
                "formato": format_name,
                "fenomeno": fenomeno,
                "tamano_bytes": path.stat().st_size,
                "estado": "excluido_duplicado",
                "apto_para_indice": False,
                "motivo_exclusion": (
                    "Todas las filas utiles del PBF ya estaban representadas en tiles anteriores."
                    if row_duplicate_only else "Contenido ya representado en otro TXT limpio."
                ),
                "duplicado_de_doc_id": duplicate_of.get("doc_id") if duplicate_of else None,
                "duplicado_de_fuente": duplicate_of.get("fuente") if duplicate_of else None,
                "deduplicacion": "filas_pbf" if row_duplicate_only else "documento_completo",
                "idioma": detect_language(cleaned),
                "metodo_extraccion": extraction.method,
                "advertencias": warnings,
                "version_pipeline": "1.1.0",
                **extraction.metadata,
            }
            entries = [item for item in entries if item.get("ruta_original") != source]
            entries.append(duplicate_entry)
            global_entry = dict(duplicate_entry)
            global_entry["ruta_original"] = duplicate_entry["ruta_global"]
            global_entries = [
                item for item in global_entries
                if item.get("ruta_original") != global_entry["ruta_original"]
            ]
            global_entries.append(global_entry)
            counters[duplicate_entry["estado"]] += 1
            entries.sort(key=lambda item: item["doc_id"])
            global_entries.sort(key=lambda item: item["doc_id"])
            write_manifest(manifest_path, entries)
            write_manifest(global_manifest_path, global_entries)
            continue
        if format_name == "pbf":
            extraction.metadata.update(
                {
                    "pbf_consolidado": True,
                    "pbf_contexto": context_key,
                    "pbf_fuente_principal": source,
                    "pbf_tiles_consolidados": 1,
                    "pbf_fuentes_cubiertas": [source],
                    "filas_duplicadas_omitidas": duplicate_rows,
                    "filas_unicas_limpias": len(cleaned.splitlines()),
                }
            )
        clean_path.write_text(cleaned, encoding="utf-8")
        if content_hash:
            seen_content_hashes.setdefault(content_hash, {"doc_id": doc_id, "fuente": path.stem, "ruta_original": source})
        entry = {
            "doc_id": doc_id,
            "fuente": path.stem,
            "ruta_original": source,
            "ruta_global": f"{input_dir.name}/{source}",
            "formato": format_name,
            "fenomeno": fenomeno,
            "tamano_bytes": path.stat().st_size,
            "estado": "fallido" if not cleaned or any(w.startswith("[CRITICO]") for w in warnings) else ("procesado_con_advertencias" if warnings else "procesado"),
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
            "ruta_limpio": clean_path.relative_to(output_dir).as_posix(),
            "archivo_limpio": clean_path.relative_to(output_dir).as_posix(),
            "contenido_hash": content_hash,
            "version_pipeline": "1.1.0",
            **extraction.metadata,
        }
        if format_name == "pbf":
            pbf_consolidates[context_key] = {
                "entry": entry,
                "clean_path": clean_path,
                "lines": cleaned.splitlines(),
                "sources": [source],
                "tiles": 1,
                "raw_chars": len(extraction.text),
                "raw_words": len(extraction.text.split()),
            }
        entries = [item for item in entries if item.get("ruta_original") != source]
        entries.append(entry)
        global_entry = dict(entry)
        global_entry["ruta_original"] = entry["ruta_global"]
        global_entries = [
            item for item in global_entries
            if item.get("ruta_original") != global_entry["ruta_original"]
        ]
        global_entries.append(global_entry)
        counters[entry["estado"]] += 1
        entries.sort(key=lambda item: item["doc_id"])
        global_entries.sort(key=lambda item: item["doc_id"])
        write_manifest(manifest_path, entries)
        write_manifest(global_manifest_path, global_entries)
        if warnings:
            print(
                f"{YELLOW}  Advertencias en {doc_id} ({len(warnings)}):{RESET}",
                flush=True,
            )
            for warning in warnings:
                print(f"{YELLOW}    - {warning}{RESET}", flush=True)
    (phenomenon_output_dir / "reporte_calidad.json").write_text(json.dumps({"total": len(entries), "estados": counters, "version_pipeline": "1.1.0"}, ensure_ascii=False, indent=2, default=dict), encoding="utf-8")
    return dict(counters)


def parse_formats(value: str) -> set[str]:
    """Convierte --formatos en nombres lógicos normalizados."""
    aliases = {"htm": "html", "markdown": "md", "xls": "xls", "jpg": "image", "jpeg": "image", "png": "image", "tif": "image", "tiff": "image"}
    formats = {item.strip().lower().lstrip(".") for item in value.split(",") if item.strip()}
    formats = {aliases.get(item, item) for item in formats}
    valid = TEXT_FORMATS
    invalid = formats - valid
    if invalid:
        raise argparse.ArgumentTypeError(
            f"Formatos no soportados: {', '.join(sorted(invalid))}. "
            f"Usa: {', '.join(sorted(valid))}."
        )
    return formats


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Define la interfaz de línea de comandos."""
    parser = argparse.ArgumentParser(description="Extrae y limpia documentos para CODEFEST AD ASTRA.")
    parser.add_argument("input_dir", type=Path, help="Directorio con archivos originales.")
    parser.add_argument("output_dir", type=Path, help="Directorio de salida del pipeline.")
    parser.add_argument(
        "--formatos",
        type=parse_formats,
        help="Formatos a procesar, separados por coma. Ejemplo: pdf,json. Por defecto, todos.",
    )
    parser.add_argument(
        "--id-inicial",
        type=int,
        default=None,
        help="Sobrescribe el primer doc_id. Por defecto se calcula usando los fenómenos anteriores.",
    )
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
    if args.id_inicial is not None and args.id_inicial < 1:
        LOGGER.error("--id-inicial debe ser mayor o igual que 1.")
        return 2
    summary = process(args.input_dir, args.output_dir, args.fenomeno, args.formatos, args.id_inicial)
    LOGGER.info("Procesamiento terminado: %s", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
