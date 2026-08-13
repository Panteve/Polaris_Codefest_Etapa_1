"""Celda autocontenida para localizar FAISS y metadata en Kaggle.

Copiar y pegar todo este archivo en una celda de Kaggle.
"""

from pathlib import Path


# Kaggle monta los datasets adjuntos dentro de /kaggle/input.
KAGGLE_INPUT = Path("/kaggle/input")
INDEX_NAME = "index.faiss"
METADATA_NAME = "metadata.jsonl"
INDEX_PATH: Path | None = None
METADATA_PATH: Path | None = None


def find_files(root: Path, filename: str) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(f"No existe la carpeta de entrada: {root}")
    return sorted(path for path in root.rglob(filename) if path.is_file())


def main() -> None:
    global INDEX_PATH, METADATA_PATH
    indexes = find_files(KAGGLE_INPUT, INDEX_NAME)
    metadata_files = find_files(KAGGLE_INPUT, METADATA_NAME)

    print(f"Índices FAISS encontrados: {len(indexes)}")
    for number, path in enumerate(indexes, 1):
        print(f"  [{number}] {path} ({path.stat().st_size / 1024**3:.2f} GB)")

    print(f"Archivos metadata encontrados: {len(metadata_files)}")
    for number, path in enumerate(metadata_files, 1):
        print(f"  [{number}] {path} ({path.stat().st_size / 1024**2:.2f} MB)")

    pairs = []
    for index_path in indexes:
        same_folder = [
            metadata_path
            for metadata_path in metadata_files
            if metadata_path.parent == index_path.parent
        ]
        if len(same_folder) == 1:
            pairs.append((index_path, same_folder[0]))

    print(f"\nParejas index/metadata en la misma carpeta: {len(pairs)}")
    for number, (index_path, metadata_path) in enumerate(pairs, 1):
        print(f"  [{number}]")
        print(f"    index:    {index_path}")
        print(f"    metadata: {metadata_path}")

    if not pairs:
        raise FileNotFoundError(
            "No se encontró una pareja index.faiss + metadata.jsonl en la misma carpeta."
        )

    # Si hay una sola pareja, queda lista automáticamente para usarla.
    # Si hay varias, se selecciona la primera y se muestran todas arriba.
    INDEX_PATH, METADATA_PATH = pairs[0]
    print("\nArchivos seleccionados:")
    print(f"INDEX_PATH = {INDEX_PATH}")
    print(f"METADATA_PATH = {METADATA_PATH}")


main()
