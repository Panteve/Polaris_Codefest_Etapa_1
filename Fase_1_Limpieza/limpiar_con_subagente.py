"""Limpia el corpus en una salida paralela usando reglas locales y DeepSeek."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import time
import unicodedata
from collections import Counter
from pathlib import Path

from openai import OpenAI


LIGATURES = str.maketrans({"ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"})
BULLET_PREFIX = re.compile(r"^\s*[•▪◦‣⁃∙·●○■□➢➤-]\s+")
URL_BREAK = re.compile(r"(https?://[^\s]+)\n([^\s]+)", re.IGNORECASE)
PAGE_NUMBER = re.compile(r"^\s*(\d{1,4})\s*$")
REFERENCE_LINE = re.compile(r"^\s*(?:\[\d+\]|\d+[.)])\s+")
REFERENCE_HEADING = re.compile(
    r"^(?:references|bibliography|works cited|sources|referencias|bibliograf[ií]a|fuentes|notas)$",
    re.IGNORECASE,
)
CONTENT_HEADING = re.compile(
    r"\b(?:chapter|section|introduction|overview|conclusion|methodology|results|"
    r"technical performance|research and development|bibliography|references|index)\b",
    re.IGNORECASE,
)
GENERIC_HEADING = re.compile(
    r"^(?:chapter|chap\.?|part|section|appendix)\s+[a-z]?\d+(?:\s+(?:preview|highlights?))?\s*$",
    re.IGNORECASE,
)
STRUCTURAL_WORD_HEADING = {
    "introduction",
    "overview",
    "annual report",
    "symbols",
    "report highlights",
    "top takeaways",
}
REMOVABLE_WORD_HEADING = {
    "table of contents",
    "contents",
    "acknowledgements",
    "acknowledgments",
    "public data and tools",
    "get involved",
}

SYSTEM_PROMPT = """Eres un revisor de limpieza de texto extraído de PDFs.
No reescribas ni resumas el documento. Devuelve únicamente JSON válido con:
remove_exact_lines, remove_exact_blocks, regex_rules, warnings y confidence.

remove_exact_lines debe contener líneas editoriales o bibliográficas aisladas.
remove_exact_blocks debe contener bloques completos de portada, índice,
bibliografía, referencias o notas cuando su texto aparezca literalmente.
Cada operación debe incluir text, reason y confidence entre 0 y 1.

regex_rules debe contener únicamente reglas para eliminar líneas editoriales
repetidas. Cada regla debe incluir pattern, action, reason, confidence y
examples. El patrón debe estar anclado con ^ y $, no debe capturar párrafos
completos y action debe ser remove_line. No propongas regex para cifras,
fechas, nombres, URLs, tablas o títulos con contenido. Sí puedes proponer
regex para líneas de bibliografía, referencias, DOI, notas o créditos.
Dentro de pattern evita comillas dobles literales. Si necesitas representar
comillas, usa clases simples sin comillas o escápalas como \\u0022 para que el
JSON siga siendo válido.

Conserva titulos, encabezados y nombres de secciones cuando organicen el
contenido del documento, por ejemplo introduccion, metodologia, resultados,
conclusiones, capitulos, partes, secciones o encabezados tematicos. Estas
senales se usaran despues para chunking estructural.
Conserva nombres propios, cifras, fechas y tablas cuando sean contenido.
Elimina bibliografía, referencias, índices, notas al pie, créditos editoriales,
DOI y URLs que funcionen como referencias.
No corrijas ortografía, no traduzcas, no parafrasees y no inventes texto.
Si hay duda, devuelve una advertencia y no propongas eliminarlo."""


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent
    default_input = root / "output"
    default_output = root / "output_post_limpieza"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=default_input)
    parser.add_argument("--output-dir", type=Path, default=default_output)
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument(
        "--formatos",
        type=parse_formats,
        default=None,
        help="Filtra por formato original segun el manifiesto, por ejemplo: pdf o pdf,json.",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sample-size", type=int, default=0, help="Selecciona N documentos aleatorios.")
    parser.add_argument("--seed", type=int, default=20260801)
    parser.add_argument("--shard-count", type=int, default=1, help="Numero total de particiones paralelas.")
    parser.add_argument("--shard-index", type=int, default=0, help="Indice de esta particion, empezando en 0.")
    parser.add_argument(
        "--reprocesar-doc-id",
        action="append",
        default=[],
        help="Fuerza reprocesar un doc_id concreto aunque su TXT de salida ya exista. Se puede repetir.",
    )
    parser.add_argument(
        "--unir-manifiestos-shards",
        action="store_true",
        help="Une los manifiestos de shards y sale sin procesar documentos.",
    )
    parser.add_argument("--sin-api", action="store_true", help="Usa solo reglas locales.")
    parser.add_argument(
        "--con-reportes-limpieza",
        action="store_true",
        help="Guarda un JSON detallado por documento en reportes_limpieza/.",
    )
    parser.add_argument(
        "--sobrescribir-salida",
        action="store_true",
        help="Reprocesa documentos aunque el TXT de salida ya exista.",
    )
    return parser.parse_args()


def parse_formats(value: str) -> set[str]:
    formatos = {item.strip().lower().lstrip(".") for item in value.split(",") if item.strip()}
    if not formatos:
        raise argparse.ArgumentTypeError("Debe indicar al menos un formato.")
    return formatos


def is_structural(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if REFERENCE_LINE.match(stripped) or stripped.lower().startswith(("http://", "https://")):
        return True
    if BULLET_PREFIX.match(line):
        return True
    if len(stripped) <= 100 and not stripped.endswith((".", ",", ";", ":")):
        letters = [char for char in stripped if char.isalpha()]
        if letters and sum(char.isupper() for char in letters) / len(letters) >= 0.7:
            return True
    if re.match(r"^\d+(?:\.\d+)?%?\s+[A-Z]", stripped):
        return True
    if len(re.findall(r"\b\d[\d,.%$-]*\b", stripped)) >= 4 and len(stripped) <= 180:
        return True
    return False


def is_structural_heading_to_keep(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", line.strip().rstrip(":"))
    return bool(normalized) and (
        GENERIC_HEADING.fullmatch(normalized)
        or normalized.lower() in STRUCTURAL_WORD_HEADING
    )


def is_removable_heading(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", line.strip().rstrip(":"))
    return bool(normalized) and normalized.lower() in REMOVABLE_WORD_HEADING


def is_generic_heading(line: str) -> bool:
    return is_structural_heading_to_keep(line) or is_removable_heading(line)


def contains_non_latin_script(text: str) -> bool:
    scripts = ("CJK", "HIRAGANA", "KATAKANA", "HANGUL", "ARABIC", "HEBREW", "DEVANAGARI", "THAI")
    return any(any(script in unicodedata.name(char, "") for script in scripts) for char in text)


def local_clean(text: str) -> tuple[str, list[dict]]:
    changes: list[dict] = []
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    ligatures = sum(text.count(char) for char in ("ﬁ", "ﬂ", "ﬃ", "ﬄ"))
    text = text.translate(LIGATURES)
    if ligatures:
        changes.append({"rule": "normalizar_ligaduras", "count": ligatures})

    controls = sum(
        1 for char in text if unicodedata.category(char) == "Cc" and char not in "\n\t"
    )
    text = "".join(
        char for char in text if not (unicodedata.category(char) == "Cc" and char not in "\n\t")
    )
    if controls:
        changes.append({"rule": "eliminar_caracteres_control", "count": controls})

    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    lines = text.split("\n")

    cleaned_lines: list[str] = []
    repeated = Counter(line.strip() for line in lines if line.strip())
    removed_headers = 0
    removed_references = 0
    in_reference_block = False
    for raw in lines:
        line = raw.strip()
        if REFERENCE_HEADING.fullmatch(line):
            in_reference_block = True
            removed_references += 1
            continue
        if in_reference_block:
            if line and is_structural(line) and not REFERENCE_LINE.match(line):
                in_reference_block = False
            else:
                removed_references += 1
                continue
        if is_removable_heading(line):
            removed_headers += 1
            continue
        if BULLET_PREFIX.match(line):
            line = BULLET_PREFIX.sub("", line).strip()
            changes.append({"rule": "quitar_vineta", "count": 1})
        page_match = PAGE_NUMBER.match(line)
        if page_match and page_match.group(1) not in {str(year) for year in range(1900, 2101)}:
            if int(page_match.group(1)) <= 999:
                removed_headers += 1
                continue
        if (
            line
            and repeated[line] >= 3
            and len(line) <= 120
            and not any(char.isdigit() for char in line)
            and not contains_non_latin_script(line)
        ):
            removed_headers += 1
            continue
        cleaned_lines.append(line)
    if removed_headers:
        changes.append({"rule": "quitar_paginacion_o_encabezado_repetido", "count": removed_headers})
    if removed_references:
        changes.append({"rule": "quitar_bibliografia_referencias_notas", "count": removed_references})

    paragraphs: list[str] = []
    current = ""
    pending_blank = False
    for line in cleaned_lines:
        if not line:
            pending_blank = bool(current)
            continue
        if is_structural(line):
            if current:
                paragraphs.append(current)
                current = ""
            pending_blank = False
            paragraphs.append(line)
            continue
        if not current:
            current = line
        elif current.endswith("-") and line and line[0].islower():
            current = current[:-1] + line
            pending_blank = False
        else:
            current += " " + line
            pending_blank = False
    if current:
        paragraphs.append(current)

    result = "\n\n".join(paragraphs).strip() + "\n"
    url_matches = URL_BREAK.findall(result)
    if url_matches:
        result = URL_BREAK.sub(r"\1\2", result)
        changes.append({"rule": "reconstruir_url_partida", "count": len(url_matches)})
    return result, changes


def apply_agent_operations(text: str, report: dict, doc_id: str = "") -> tuple[str, list[dict]]:
    changes = []
    for operation in report.get("remove_exact_lines", []) or []:
        if isinstance(operation, dict):
            candidate = str(operation.get("text", "")).strip()
            try:
                confidence = float(operation.get("confidence", 0))
            except (TypeError, ValueError):
                continue
        elif isinstance(operation, str):
            candidate = operation.strip()
            confidence = 0.9
        else:
            continue
        occurrences = sum(1 for line in text.splitlines() if line.strip() == candidate)
        safe_line = (
            candidate
            and confidence >= 0.9
            and occurrences >= 2
            and len(candidate) <= 120
            and not (
                CONTENT_HEADING.search(candidate)
                and not is_removable_heading(candidate)
                and not REFERENCE_HEADING.fullmatch(candidate)
            )
            and not is_structural_heading_to_keep(candidate)
            and not candidate.endswith(":")
            and not contains_non_latin_script(candidate)
        )
        if safe_line:
            text = "\n".join(line for line in text.split("\n") if line.strip() != candidate)
            changes.append({"rule": "agente_quitar_linea_editorial", "text": candidate})
    for operation in report.get("remove_exact_blocks", []) or []:
        if not isinstance(operation, dict):
            continue
        candidate = str(operation.get("text", ""))
        try:
            confidence = float(operation.get("confidence", 0))
        except (TypeError, ValueError):
            continue
        if (
            candidate
            and confidence >= 0.95
            and text.count(candidate) == 1
            and not contains_non_latin_script(candidate)
        ):
            text = text.replace(candidate, "")
            changes.append({"rule": "agente_quitar_bloque_editorial", "text": candidate[:200]})
    for rule in report.get("regex_rules", []) or []:
        if not isinstance(rule, dict):
            continue
        pattern = str(rule.get("pattern", ""))
        action = str(rule.get("action", ""))
        try:
            confidence = float(rule.get("confidence", 0))
        except (TypeError, ValueError):
            continue
        if action != "remove_line" or confidence < 0.9 or not (pattern.startswith("^") and pattern.endswith("$")):
            continue
        if len(pattern) > 200 or "\\n" in pattern:
            continue
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error:
            continue
        lines = text.splitlines()
        matches = sum(1 for line in lines if compiled.fullmatch(line.strip()))
        if matches < 2:
            continue
        text = "\n".join(line for line in lines if not compiled.fullmatch(line.strip()))
        changes.append(
            {
                "rule": "agente_regex_linea_editorial",
                "pattern": pattern,
                "matches": matches,
                "reason": rule.get("reason", ""),
            }
        )
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n", changes


def ask_agent(client: OpenAI, model: str, doc_id: str, text: str) -> dict:
    last_warning = ""
    last_content = ""
    for attempt in range(1, 3):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"doc_id": doc_id, "texto": text}, ensure_ascii=False)},
        ]
        if attempt == 2:
            messages.insert(
                1,
                {
                    "role": "system",
                    "content": (
                        "Tu respuesta anterior no fue JSON valido. Reintenta. "
                        "Devuelve un unico objeto JSON valido, sin markdown, sin comentarios, "
                        "sin comillas dobles literales sin escapar dentro de strings."
                    ),
                },
            )
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=messages,
            )
        except Exception as exc:
            return {
                "warnings": [f"No se pudo consultar el agente ({type(exc).__name__}): {exc}"],
                "remove_exact_lines": [],
                "remove_exact_blocks": [],
                "regex_rules": [],
            }
        content = response.choices[0].message.content or "{}"
        try:
            report = json.loads(content)
            if attempt == 2:
                warnings = report.setdefault("warnings", [])
                if isinstance(warnings, list):
                    warnings.append("El agente requirio un reintento por JSON invalido en la primera respuesta.")
                print(f"  JSON del agente corregido en reintento para {doc_id}.", flush=True)
            return report
        except json.JSONDecodeError as exc:
            last_content = content
            last_warning = (
                f"El agente devolvio JSON invalido para {doc_id} en intento {attempt}/2. "
                f"{exc.msg} en linea {exc.lineno}, columna {exc.colno}."
            )
            if attempt == 1:
                print(f"  JSON invalido del agente en {doc_id}; reintentando...", flush=True)
                continue

    print(f"  JSON del agente siguio invalido en {doc_id}; se usa limpieza local/manual.", flush=True)
    return {
        "warnings": [f"{last_warning} Se uso solo limpieza local."],
        "remove_exact_lines": [],
        "remove_exact_blocks": [],
        "regex_rules": [],
        "raw_response": last_content,
    }


def read_existing_manifest(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, list):
        return {}
    return {
        str(entry.get("ruta_limpio_post", "")): entry
        for entry in data
        if entry.get("ruta_limpio_post")
    }


def read_existing_manifests(output_dir: Path) -> dict[str, dict]:
    manifests: dict[str, dict] = {}
    for manifest_path in sorted(output_dir.glob("manifiesto_post_limpieza*.json")):
        manifests.update(read_existing_manifest(manifest_path))
    return manifests


def read_source_entries(input_dir: Path) -> list[dict]:
    entries_by_doc_id: dict[str, dict] = {}
    for manifest_path in sorted(input_dir.glob("F*/manifiesto.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            entries = data if isinstance(data, list) else data.get("documentos", [])
            for entry in entries:
                if entry.get("doc_id"):
                    entries_by_doc_id[entry["doc_id"]] = entry
        except (OSError, json.JSONDecodeError):
            continue
    return list(entries_by_doc_id.values())


def shard_manifest_path(output_dir: Path, shard_index: int, shard_count: int) -> Path:
    if shard_count <= 1:
        return output_dir / "manifiesto_post_limpieza.json"
    return output_dir / f"manifiesto_post_limpieza_shard_{shard_index}_de_{shard_count}.json"


def merge_shard_manifests(
    output_dir: Path,
    input_dir: Path,
    formatos: set[str] | None = None,
) -> int:
    manifests = read_existing_manifests(output_dir)
    if formatos:
        manifests = {
            ruta: entry
            for ruta, entry in manifests.items()
            if str(entry.get("formato", "")).lower() in formatos
        }

    existing_doc_ids = {entry.get("doc_id") for entry in manifests.values()}
    added_initial = 0
    for source_entry in read_source_entries(input_dir):
        doc_id = source_entry.get("doc_id")
        source_format = str(source_entry.get("formato", "")).lower()
        if not doc_id or doc_id in existing_doc_ids:
            continue
        if formatos and source_format not in formatos:
            continue
        if source_entry.get("estado") not in {"procesado", "procesado_con_advertencias"}:
            continue

        relative_source = source_entry.get("ruta_limpio") or source_entry.get("archivo_limpio")
        if not relative_source:
            continue
        source_path = input_dir / relative_source
        destination = output_dir / relative_source
        if not source_path.is_file():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.is_file():
            shutil.copy2(source_path, destination)
        manifests[Path(relative_source).as_posix()] = {
            **source_entry,
            "ruta_limpio_post": Path(relative_source).as_posix(),
            "archivo_limpio_post": str(destination.resolve()),
            "conteo_post": source_entry.get("conteo", {}),
            "estado_limpieza": "procesado_inicial",
        }
        existing_doc_ids.add(doc_id)
        added_initial += 1

    merged = sorted(manifests.values(), key=lambda entry: entry.get("doc_id", ""))
    target = output_dir / "manifiesto_post_limpieza.json"
    write_manifest(target, merged)
    print(f"Manifiesto unido: {target.resolve()}")
    print(f"Entradas: {len(merged)}")
    print(f"Documentos incorporados desde la limpieza inicial: {added_initial}")
    return 0


def write_manifest(path: Path, manifest: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    pid = os.getpid()
    temporary = path.with_name(f".{path.name}.{pid}.tmp")
    for attempt in range(1, 6):
        try:
            temporary.write_text(payload, encoding="utf-8")
            temporary.replace(path)
            return
        except PermissionError as exc:
            if attempt == 5:
                fallback = path.with_name(f"{path.stem}_pid_{pid}{path.suffix}")
                fallback.write_text(payload, encoding="utf-8")
                print(
                    f"  ADVERTENCIA: Windows bloqueo {path.name}; "
                    f"se escribio respaldo {fallback.name}. Detalle: {exc}",
                    flush=True,
                )
                return
            time.sleep(0.25 * attempt)


def skipped_manifest_entry(
    source: Path,
    destination: Path,
    relative: Path,
    source_metadata: dict[str, dict],
) -> dict:
    doc_id = source.stem
    original = source.read_text(encoding="utf-8-sig", errors="replace")
    cleaned = destination.read_text(encoding="utf-8-sig", errors="replace")
    return {
        **source_metadata.get(doc_id, {}),
        "doc_id": doc_id,
        "ruta_limpio_post": relative.as_posix(),
        "archivo_limpio_post": str(destination.resolve()),
        "conteo_post": {
            "caracteres_antes": len(original),
            "caracteres_despues": len(cleaned),
        },
        "estado_limpieza": "procesado_existente",
    }


def main() -> int:
    args = parse_args()
    if args.shard_count < 1:
        raise SystemExit("--shard-count debe ser mayor o igual a 1.")
    if args.shard_index < 0 or args.shard_index >= args.shard_count:
        raise SystemExit("--shard-index debe estar entre 0 y --shard-count - 1.")
    if args.unir_manifiestos_shards:
        return merge_shard_manifests(args.output_dir, args.input_dir, args.formatos)

    source_metadata: dict[str, dict] = {}
    for manifest_path in args.input_dir.glob("F*/manifiesto.json"):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            entries = data if isinstance(data, list) else data.get("documentos", [])
            for entry in entries:
                if entry.get("doc_id"):
                    source_metadata[entry["doc_id"]] = entry
        except (OSError, json.JSONDecodeError):
            continue

    files = sorted(
        path for path in args.input_dir.rglob("*.txt") if args.output_dir not in path.parents
    )
    if args.formatos:
        files = [
            path
            for path in files
            if source_metadata.get(path.stem, {}).get("formato", "").lower() in args.formatos
        ]
    if args.sample_size:
        import random

        if args.sample_size > len(files):
            raise SystemExit(f"Se solicitaron {args.sample_size}, pero solo hay {len(files)} TXT filtrados")
        files = sorted(
            random.Random(args.seed).sample(files, args.sample_size),
            key=lambda path: str(path).lower(),
        )
    elif args.limit:
        files = files[: args.limit]
    if not files:
        filtro = f" con formatos {sorted(args.formatos)}" if args.formatos else ""
        raise SystemExit(f"No hay TXT{filtro} en {args.input_dir}")
    total_files_before_shard = len(files)
    if args.shard_count > 1:
        files = [
            path
            for position, path in enumerate(files)
            if position % args.shard_count == args.shard_index
        ]
        print(
            f"Shard {args.shard_index}/{args.shard_count}: "
            f"{len(files)} de {total_files_before_shard} documentos",
            flush=True,
        )

    client = None
    if not args.sin_api:
        key = os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise SystemExit("Falta DEEPSEEK_API_KEY. Usa --sin-api para ejecutar solo reglas locales.")
        client = OpenAI(api_key=key, base_url="https://api.deepseek.com")

    reports_dir = args.output_dir / "reportes_limpieza"
    if args.con_reportes_limpieza:
        reports_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = shard_manifest_path(args.output_dir, args.shard_index, args.shard_count)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    existing_manifest = read_existing_manifests(args.output_dir)
    forced_doc_ids = set(args.reprocesar_doc_id or [])
    manifest = []
    processed = 0
    skipped = 0
    for index, source in enumerate(files, start=1):
        doc_id = source.stem
        relative = source.relative_to(args.input_dir)
        destination = args.output_dir / relative
        relative_post = str(relative).replace("\\", "/")
        force_reprocess = doc_id in forced_doc_ids
        if destination.is_file() and not args.sobrescribir_salida and not force_reprocess:
            print(f"[{index}/{len(files)}] Omitido, ya procesado: {doc_id}", flush=True)
            manifest.append(
                existing_manifest.get(
                    relative_post,
                    skipped_manifest_entry(source, destination, relative, source_metadata),
                )
            )
            skipped += 1
            write_manifest(manifest_path, manifest)
            continue

        if force_reprocess and destination.is_file():
            print(f"[{index}/{len(files)}] Reprocesando por solicitud: {doc_id}", flush=True)
        else:
            print(f"[{index}/{len(files)}] Procesando: {doc_id}", flush=True)
        original = source.read_text(encoding="utf-8-sig", errors="replace")
        cleaned, local_changes = local_clean(original)
        agent_report = {}
        agent_changes = []
        if client:
            agent_report = ask_agent(client, args.model, doc_id, cleaned)
            if agent_report.get("raw_response"):
                print("  Respuesta invalida del agente:", flush=True)
                print("  --- inicio respuesta agente ---", flush=True)
                print(agent_report["raw_response"], flush=True)
                print("  --- fin respuesta agente ---", flush=True)
            cleaned, agent_changes = apply_agent_operations(cleaned, agent_report, doc_id)

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(cleaned, encoding="utf-8", newline="\n")
        report = {
            "doc_id": doc_id,
            "archivo_original": str(source.resolve()),
            "archivo_limpio": str(destination.resolve()),
            "caracteres_antes": len(original),
            "caracteres_despues": len(cleaned),
            "cambios_locales": local_changes,
            "cambios_agente_aplicados": agent_changes,
            "reglas_regex_propuestas": agent_report.get("regex_rules", []),
            "advertencias_agente": agent_report.get("warnings", []),
            "operaciones_agente_no_aplicadas": {
                "lineas": agent_report.get("remove_exact_lines", []),
                "bloques": agent_report.get("remove_exact_blocks", []),
            },
            "estado": "procesado_con_advertencias" if agent_report.get("warnings") else "procesado",
        }
        if agent_report.get("raw_response"):
            report["respuesta_agente_invalida"] = agent_report["raw_response"]
        report_path = reports_dir / f"{doc_id}.json"
        if args.con_reportes_limpieza:
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        manifest_entry = {
            **source_metadata.get(doc_id, {}),
            "doc_id": doc_id,
            "ruta_limpio_post": str(relative).replace("\\", "/"),
            "archivo_limpio_post": str(destination.resolve()),
            "conteo_post": {
                "caracteres_antes": len(original),
                "caracteres_despues": len(cleaned),
            },
            "estado_limpieza": report["estado"],
        }
        if args.con_reportes_limpieza:
            manifest_entry["reporte_limpieza"] = str(report_path.resolve())
        manifest.append(manifest_entry)
        processed += 1
        write_manifest(manifest_path, manifest)

    write_manifest(manifest_path, manifest)
    print(f"Completado: {len(files)} documentos ({processed} procesados, {skipped} omitidos)")
    print(f"Salida: {args.output_dir.resolve()}")
    print(f"Manifiesto: {manifest_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
