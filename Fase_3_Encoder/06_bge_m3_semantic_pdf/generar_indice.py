from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from index_utils import build_standard_index  # noqa: E402


def main() -> None:
    folder = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Índice BGE-M3 con PDF de chunking semántico.")
    parser.add_argument("--metadata", type=Path, default=folder / "metadata.jsonl")
    parser.add_argument("--output-index", type=Path, default=folder / "index.faiss")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", default=None)
    parser.add_argument("--checkpoint-dir", type=Path, default=folder / ".checkpoint")
    parser.add_argument("--checkpoint-every", type=int, default=10, help="cada cuántos lotes guardar checkpoint")
    parser.add_argument("--fresh", action="store_true", help="ignorar checkpoints existentes")
    args = parser.parse_args()
    build_standard_index(
        metadata_path=args.metadata,
        output_index=args.output_index,
        model_name="BAAI/bge-m3",
        batch_size=args.batch_size,
        device=args.device,
        label="BGE-M3 semantic PDF",
        checkpoint_dir=args.checkpoint_dir,
        checkpoint_every=args.checkpoint_every,
        fresh=args.fresh,
    )


if __name__ == "__main__":
    main()
