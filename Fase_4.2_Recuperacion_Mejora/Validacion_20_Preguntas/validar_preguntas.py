"""Valida el contrato del conjunto interno de 20 preguntas."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REQUIRED = {"query_id", "fenomeno", "idioma", "pregunta", "respuesta_esperada", "fuente_tipo", "fuente_referencia"}
LANGUAGES = {"es", "en", "pt"}
FORMATS = {"pdf", "json", "csv", "xlsx", "txt", "pbf", "image"}


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    rows: list[dict] = []
    if not path.is_file():
        return [f"No existe el archivo: {path}"]
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"Línea {number}: JSON inválido: {exc.msg}")
            continue
        if not isinstance(row, dict):
            errors.append(f"Línea {number}: debe ser un objeto JSON")
            continue
        missing = sorted(REQUIRED - set(row))
        if missing:
            errors.append(f"Línea {number}: faltan {', '.join(missing)}")
        if row.get("fenomeno") not in {1, 2, 3}:
            errors.append(f"Línea {number}: fenómeno inválido")
        if row.get("idioma") not in LANGUAGES:
            errors.append(f"Línea {number}: idioma inválido")
        if row.get("fuente_tipo") not in FORMATS:
            errors.append(f"Línea {number}: formato inválido")
        rows.append(row)
    ids = [row.get("query_id") for row in rows]
    expected = [f"T{i:03d}" for i in range(1, 21)]
    if len(rows) != 20:
        errors.append(f"Se esperaban 20 preguntas y hay {len(rows)}")
    if ids != expected:
        errors.append("Los query_id deben estar ordenados de T001 a T020")
    if len(set(ids)) != len(ids):
        errors.append("Hay query_id duplicados")
    if Counter(row.get("fenomeno") for row in rows) != Counter({1: 6, 2: 6, 3: 8}):
        errors.append("La distribución por fenómeno no coincide con 6/6/8")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    errors = validate(args.path)
    if errors:
        print("VALIDACIÓN FALLIDA")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("VALIDACIÓN OK: 20 preguntas, IDs ordenados y distribución correcta")
    return 0


if __name__ == "__main__":
    sys.exit(main())
