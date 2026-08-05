"""Recupera documentos PDF que quedaron vacíos durante el chunking.

El flujo es deliberadamente acotado a los doc_id indicados por
reporte_chunking_pdf.json:

1. vuelve a extraer cada PDF con pdf-inspector;
2. si no devuelve Markdown, genera un PDF temporal con OCRmyPDF y repite la
   extracción;
3. escribe el Markdown en output_final_limpio;
4. actualiza el manifiesto final de Fase 1;
5. opcionalmente vuelve a generar metadata.json, metadata.jsonl y el reporte
   de chunking.

No modifica los PDF originales.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from extraer_pdfs_pdf_inspector import (
    create_ocr_pdf,
    extract_with_pdf_inspector,
    ocr_languages_for_item,
    resolve_pdf,
)


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = next(
    (candidate for candidate in (SCRIPT_DIR, *SCRIPT_DIR.parents)
     if (candidate / "Fase_1_Limpieza").is_dir()),
    SCRIPT_DIR.parents[2],
)
DEFAULT_MANIFEST = PROJECT_ROOT / "Fase_1_Limpieza" / "output_final_limpio" / "manifiesto_final_limpio.json"
DEFAULT_INPUT_ROOT = PROJECT_ROOT / "Fase_1_Limpieza" / "input"
_REPORT_CANDIDATES = sorted(
    (PROJECT_ROOT / "Fase_2_Chunking" / "chunking-pdfs").glob(
        "pdfs_*/reporte_chunking_pdf.json"
    ),
    key=lambda path: path.stat().st_mtime,
    reverse=True,
)
DEFAULT_REPORT = (
    _REPORT_CANDIDATES[0]
    if _REPORT_CANDIDATES
    else PROJECT_ROOT / "Fase_2_Chunking" / "chunking-pdfs" / "reporte_chunking_pdf.json"
)
DEFAULT_CHUNKER = PROJECT_ROOT / "Fase_2_Chunking" / "chunking-pdfs" / "chunk_pdfs.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reextrae con PDF Inspector y OCR los documentos sin chunks."
    )
    parser.add_argument("--reporte", type=Path, default=DEFAULT_REPORT,
                        help="reporte_chunking_pdf.json que contiene documentos_vacios")
    parser.add_argument("--manifiesto", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT,
                        help="raíz donde están los PDF originales")
    parser.add_argument("--output-root", type=Path, default=None,
                        help="raíz output_final_limpio; por defecto se deduce del manifiesto")
    parser.add_argument("--node", default="node")
    parser.add_argument("--node-helper", type=Path,
                        default=SCRIPT_DIR / "extraer_un_pdf_pdf_inspector.mjs")
    parser.add_argument("--ocr-command", default="ocrmypdf")
    parser.add_argument("--ocr-languages", default="auto")
    parser.add_argument("--chunker", type=Path, default=DEFAULT_CHUNKER)
    parser.add_argument("--chunk-output", type=Path, default=None,
                        help="carpeta donde se actualizará metadata; por defecto, la del reporte")
    parser.add_argument("--sin-rechunk", action="store_true",
                        help="solo recupera Markdown y manifiesto, sin regenerar metadata")
    parser.add_argument("--doc-id", action="append", dest="doc_ids",
                        help="limita la recuperación; puede repetirse")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def output_path_for(item: dict[str, Any], manifest_path: Path, output_root: Path | None) -> Path:
    if output_root is None:
        output_root = manifest_path.parent
    relative = item.get("ruta_final")
    if relative:
        return output_root / Path(str(relative))
    return output_root / f"{item.get('doc_id', 'UNKNOWN')}.md"


def empty_doc_ids(report: dict[str, Any]) -> list[str]:
    values = report.get("documentos_vacios", [])
    result = []
    for item in values:
        doc_id = item.get("doc_id") if isinstance(item, dict) else item
        if doc_id:
            result.append(str(doc_id))
    return list(dict.fromkeys(result))


def update_manifest(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_chunker(args: argparse.Namespace, chunk_output: Path) -> int:
    command = [
        sys.executable, str(args.chunker),
        "--entrada", str(args.manifiesto.parent),
        "--manifiesto", str(args.manifiesto),
        "--salida", str(chunk_output),
        "--sin-subcarpeta",
    ]
    completed = subprocess.run(command, check=False)
    return completed.returncode


def main() -> int:
    args = parse_args()
    report = load_json(args.reporte)
    requested_ids = set(args.doc_ids or empty_doc_ids(report))
    records = load_json(args.manifiesto)
    records_by_id = {str(item.get("doc_id")): item for item in records if isinstance(item, dict)}
    selected = [records_by_id[doc_id] for doc_id in sorted(requested_ids) if doc_id in records_by_id]

    if not selected:
        print("No se encontraron documentos vacíos válidos en el manifiesto.")
        return 1

    output_root = args.output_root or args.manifiesto.parent
    recovery_report: dict[str, Any] = {
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "reporte_origen": str(args.reporte),
        "documentos_seleccionados": len(selected),
        "recuperados": 0,
        "ocr_aplicado": 0,
        "errores": 0,
        "documentos": [],
    }

    for item in selected:
        doc_id = str(item["doc_id"])
        target = output_path_for(item, args.manifiesto, args.output_root)
        entry: dict[str, Any] = {"doc_id": doc_id, "ruta_markdown": str(target)}
        try:
            pdf_path = resolve_pdf(item, args.input_root)
            if pdf_path is None:
                raise FileNotFoundError("No se encontró el PDF original.")
            markdown, details = extract_with_pdf_inspector(pdf_path, args.node, args.node_helper)
            used_ocr = False
            languages = None
            if not markdown or not markdown.strip():
                import tempfile
                with tempfile.TemporaryDirectory(prefix="pdf_ocr_recuperacion_") as temp_dir:
                    ocr_pdf = Path(temp_dir) / f"{doc_id}_ocr.pdf"
                    languages = ocr_languages_for_item(item, args.ocr_languages)
                    create_ocr_pdf(pdf_path, args.ocr_command, ocr_pdf, languages)
                    markdown, ocr_details = extract_with_pdf_inspector(
                        ocr_pdf, args.node, args.node_helper
                    )
                    details = {**details, **ocr_details}
                    used_ocr = True
            if not markdown or not markdown.strip():
                raise RuntimeError("PDF Inspector y OCR no produjeron Markdown.")

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(markdown, encoding="utf-8")
            item["archivo_final"] = str(target)
            item["ruta_final"] = str(target.relative_to(output_root))
            item["tipo_contenido_final"] = "markdown"
            item["metodo_extraccion_final"] = (
                "firecrawl_pdf_inspector_ocrmypdf_recuperacion"
                if used_ocr else "firecrawl_pdf_inspector_recuperacion"
            )
            item["ocr_aplicado"] = used_ocr
            if languages:
                item["ocr_languages"] = languages
            entry.update({"estado": "recuperado", "ocr_aplicado": used_ocr, **details})
            recovery_report["recuperados"] += 1
            if used_ocr:
                recovery_report["ocr_aplicado"] += 1
        except Exception as exc:
            entry.update({"estado": "fallido", "error": str(exc)})
            recovery_report["errores"] += 1
        recovery_report["documentos"].append(entry)

    update_manifest(args.manifiesto, records)
    recovery_path = args.manifiesto.parent / "reporte_recuperacion_documentos_vacios.json"
    recovery_path.write_text(json.dumps(recovery_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Recuperados: {recovery_report['recuperados']}/{len(selected)}")
    print(f"OCR aplicado: {recovery_report['ocr_aplicado']}")
    print(f"Errores: {recovery_report['errores']}")
    print(f"Reporte: {recovery_path}")

    if not args.sin_rechunk and recovery_report["recuperados"]:
        chunk_output = args.chunk_output or args.reporte.parent
        return run_chunker(args, chunk_output)
    return 0 if recovery_report["errores"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
