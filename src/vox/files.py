import os
from pathlib import Path


def write_text_atomically(path: Path, text: str) -> None:
    # Write beside the target, then swap it in, so a crash never leaves a
    # half-written file behind.
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.write_text(text, encoding="utf-8")
    os.replace(temporary_path, path)
