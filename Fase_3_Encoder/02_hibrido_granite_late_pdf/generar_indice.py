from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from index_utils import build_late_index  # noqa: E402


def main() -> None:
    folder = Path(__file__).resolve().parent
    project_root = folder.parents[1]
    parser = argparse.ArgumentParser(description="Índice Granite late chunking para PDF.")
    parser.add_argument("--metadata", type=Path, default=folder / "metadata.jsonl")
    parser.add_argument("--manifest", type=Path, default=project_root / "Fase_1_Limpieza/output_final_limpio/manifiesto_final_limpio.json")
    parser.add_argument("--output-index", type=Path, default=folder / "index.faiss")
    parser.add_argument("--device", default=None)
    parser.add_argument("--checkpoint-dir", type=Path, default=folder / ".checkpoint")
    parser.add_argument("--checkpoint-every", type=int, default=10, help="cada cuántos documentos guardar checkpoint")
    parser.add_argument("--fresh", action="store_true", help="ignorar checkpoints existentes")
    args = parser.parse_args()
    build_late_index(
        metadata_path=args.metadata,
        manifest_path=args.manifest,
        output_index=args.output_index,
        model_name="ibm-granite/granite-embedding-311m-multilingual-r2",
        device=args.device,
        selector=lambda record: str(record.get("formato", "")).lower() == "pdf",
        label="Granite late PDF",
        checkpoint_dir=args.checkpoint_dir,
        checkpoint_every=args.checkpoint_every,
        fresh=args.fresh,
    )


if __name__ == "__main__":
    main()
