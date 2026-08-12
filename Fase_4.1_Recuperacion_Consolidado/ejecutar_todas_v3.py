"""Ejecuta secuencialmente todas las recuperaciones V3 y guarda sus resultados."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


FOLDER = Path(__file__).resolve().parent
PROJECT_ROOT = FOLDER.parent
DEFAULT_QUESTIONS = FOLDER / "Validacion_20_Preguntas" / "ground_truth_15_preguntas.json"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"

SCRIPTS = (
    ("01_bge_m3_corpus", "recuperar_V3.py"),
    ("03_granite_corpus", "recuperar_V3.py"),
    ("04_bge_m3_overlap_1", "recuperar_V3.py"),
    ("05_granite_overlap_1", "recuperar_V3.py"),
    ("06_bge_m3_semantic_pdf", "recuperar_V3.py"),
)


def utf8_environment() -> dict[str, str]:
    environment = dict(__import__("os").environ)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    return environment


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ejecuta todos los recuperadores V3 en secuencia."
    )
    parser.add_argument(
        "--query",
        help="Ejecuta una sola pregunta en cada script en lugar del archivo completo.",
    )
    parser.add_argument(
        "--questions",
        type=Path,
        default=DEFAULT_QUESTIONS,
        help="Archivo JSON de preguntas.",
    )
    parser.add_argument(
        "--recall-top-k",
        type=int,
        default=100,
        help="Candidatos de recall para cada script.",
    )
    parser.add_argument(
        "--output-top-k",
        type=int,
        default=10,
        help="Fragmentos finales para cada respuesta.",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help="Dispositivo para los modelos, por defecto cpu.",
    )
    parser.add_argument(
        "--mmr-lambda",
        type=float,
        default=0.7,
        help="Balance entre relevancia y diversidad.",
    )
    parser.add_argument(
        "--near-duplicate-threshold",
        type=float,
        default=0.90,
        help="Umbral de similitud para deduplicación semántica.",
    )
    args = parser.parse_args()

    if not args.query and not args.questions.exists():
        raise FileNotFoundError(f"No existe el archivo de preguntas: {args.questions}")
    if args.recall_top_k < 1 or args.output_top_k < 1:
        raise ValueError("recall-top-k y output-top-k deben ser mayores que cero.")

    log_path = FOLDER / "ejecucion_v3.log"
    failures = []
    python_executable = VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")

    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"Inicio: {started_at}\n")
        log.write(f"Preguntas: {args.query if args.query else args.questions}\n")
        log.write(f"Recall: {args.recall_top_k}\n")
        log.write(f"Salida: {args.output_top_k}\n")
        log.write(f"Dispositivo: {args.device}\n\n")

        for position, (corpus_name, script_name) in enumerate(SCRIPTS, 1):
            script_path = FOLDER / corpus_name / script_name
            output_path = FOLDER / corpus_name / "resultado_v3_preguntas.json"
            command = [
                str(python_executable),
                str(script_path),
                "--recall-top-k",
                str(args.recall_top_k),
                "--output-top-k",
                str(args.output_top_k),
                "--near-duplicate-threshold",
                str(args.near_duplicate_threshold),
                "--mmr-lambda",
                str(args.mmr_lambda),
                "--device",
                args.device,
                "--output-json",
                str(output_path),
            ]
            if args.query:
                command.extend(["--query", args.query])
            else:
                command.extend(["--questions", str(args.questions)])

            header = f"[{position}/{len(SCRIPTS)}] {corpus_name}"
            print(f"{header}: iniciando")
            log.write(f"{header}\n")
            log.write("Comando: " + " ".join(command) + "\n")
            log.flush()

            result = subprocess.run(
                command,
                cwd=FOLDER / corpus_name,
                env=utf8_environment(),
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )

            if result.returncode == 0:
                print(f"{header}: terminado -> {output_path}")
                log.write(f"Estado: terminado; salida: {output_path}\n\n")
            else:
                failures.append(corpus_name)
                print(f"{header}: ERROR código {result.returncode}; se continúa")
                log.write(f"Estado: ERROR código {result.returncode}; se continúa\n\n")
            log.flush()

    finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
    summary = f"Fin: {finished_at}\nScripts con error: {', '.join(failures) if failures else 'ninguno'}\n"
    with log_path.open("a", encoding="utf-8") as log:
        log.write(summary)
    print(summary, end="")
    print(f"Log: {log_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
