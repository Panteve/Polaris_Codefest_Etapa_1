"""Prepara metadata y fuentes para el experimento híbrido late chunking."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: se esperaba un objeto JSON.")
            records.append(value)
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def copy_pdf_sources(
    pdf_records: list[dict[str, Any]],
    manifest_path: Path,
    destination: Path,
) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_doc = {str(item.get("doc_id")): item for item in manifest if isinstance(item, dict)}
    copied_manifest = []
    seen: set[str] = set()
    for record in pdf_records:
        doc_id = str(record.get("doc_id", ""))
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        source_info = by_doc.get(doc_id)
        if not source_info:
            raise FileNotFoundError(f"No hay manifiesto para {doc_id}.")
        source = Path(str(source_info.get("archivo_final") or source_info.get("ruta_final", "")))
        if not source.is_absolute():
            source = manifest_path.parent / source
        if not source.exists():
            # Algunos manifiestos históricos conservan el nombre anterior de
            # la carpeta; la ubicación vigente usa guiones bajos.
            legacy_text = str(source).replace("output final limpio", "output_final_limpio")
            legacy_source = Path(legacy_text)
            if legacy_source.exists():
                source = legacy_source
        if source.suffix.lower() not in {".md", ".txt"}:
            raise ValueError(f"La fuente de {doc_id} no es Markdown/TXT: {source}")
        if not source.exists():
            raise FileNotFoundError(f"No existe la fuente de {doc_id}: {source}")
        target = destination / "documentos" / f"{doc_id}{source.suffix.lower()}"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied_manifest.append({
            **source_info,
            "archivo_final": str(Path("documentos") / target.name),
            "ruta_final": str(Path("documentos") / target.name),
            "tipo_contenido_final": "markdown" if source.suffix.lower() == ".md" else "text",
        })
    (destination / "manifiesto_late_local.json").write_text(
        json.dumps(copied_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    phase2 = root.parent / "Fase_2_Chunking"
    phase1 = root.parent / "Fase_1_Limpieza"
    folder = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf-metadata",
        type=Path,
        default=phase2 / "chunking-pdfs" / "pdfs_late_chunking_objetivo-200palabras_max-250_solapamiento-0_granite_pdf" / "metadata.jsonl",
    )
    parser.add_argument(
        "--json-metadata",
        type=Path,
        default=phase2 / "chunking-jsons" / "salida_json" / "metadata.jsonl",
    )
    parser.add_argument(
        "--otros-metadata",
        type=Path,
        default=phase2 / "chunking-otros" / "salida_otros" / "metadata.jsonl",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=phase1 / "output_final_limpio" / "manifiesto_final_limpio.json",
    )
    args = parser.parse_args()
    pdf_records = [r for r in read_jsonl(args.pdf_metadata) if str(r.get("formato", "")).lower() == "pdf"]
    no_pdf_records = [
        r
        for source in (args.json_metadata, args.otros_metadata)
        for r in read_jsonl(source)
        if str(r.get("formato", "")).lower() != "pdf"
    ]
    pdf_folder = folder / "pdf_late"
    no_pdf_folder = folder / "no_pdf"
    write_jsonl(pdf_folder / "metadata.jsonl", pdf_records)
    write_jsonl(no_pdf_folder / "metadata.jsonl", no_pdf_records)
    copy_pdf_sources(pdf_records, args.manifest, pdf_folder)
    print(f"PDF late: {len(pdf_records):,} registros")
    print(f"No-PDF: {len(no_pdf_records):,} registros")
    print(f"Fuentes copiadas en: {pdf_folder / 'documentos'}")


if __name__ == "__main__":
    main()
