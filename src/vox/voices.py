import re
import shutil
from pathlib import Path

from vox.engines.base import Voice
from vox.paths import voices_dir

_VOICE_ID_PATTERN = re.compile(r"[a-z0-9_-]+")


def _normalize_voice_id(voice_id: str) -> str:
    normalized_id = voice_id.strip().lower()

    if _VOICE_ID_PATTERN.fullmatch(normalized_id) is None:
        raise ValueError(
            "Invalid voice ID. Use only letters, numbers, underscores, and hyphens."
        )

    return normalized_id


def load_voice(voice_id: str, root: Path | None = None) -> Voice:
    normalized_id = _normalize_voice_id(voice_id)

    voice_root: Path
    if root is None:
        voice_root = voices_dir()
    else:
        voice_root = root

    reference_path: Path = voice_root / normalized_id / "reference.wav"
    transcript_path: Path = voice_root / normalized_id / "transcript.txt"

    if not reference_path.is_file():
        raise FileNotFoundError(f"Reference audio file not found: {reference_path}")

    if not transcript_path.is_file():
        raise FileNotFoundError(
            f"Reference transcript file not found: {transcript_path}"
        )

    transcript = transcript_path.read_text(encoding="utf-8").strip()

    if not transcript:
        raise ValueError("Voice transcript cannot be empty.")

    display_name = re.sub(r"[_-]+", " ", normalized_id).title()

    return Voice(
        voice_id=normalized_id,
        display_name=display_name,
        reference_path=reference_path,
        transcript=transcript,
    )


def save_voice(
    voice_id: str,
    reference_path: Path,
    transcript: str,
    root: Path | None = None,
) -> Voice:
    normalized_id = _normalize_voice_id(voice_id)

    if not reference_path.is_file():
        raise FileNotFoundError(f"Reference audio file not found: {reference_path}")

    clean_transcript = transcript.strip()

    if not clean_transcript:
        raise ValueError("Voice transcript cannot be empty.")

    voice_root: Path
    if root is None:
        voice_root = voices_dir()
    else:
        voice_root = root

    voice_directory = voice_root / normalized_id
    voice_directory.mkdir(parents=True, exist_ok=False)

    shutil.copyfile(reference_path, voice_directory / "reference.wav")

    transcript_path: Path = voice_directory / "transcript.txt"

    transcript_path.write_text(clean_transcript + "\n", encoding="utf-8")

    return load_voice(voice_id=normalized_id, root=voice_root)


def list_voices(root: Path | None = None) -> list[Voice]:
    voice_root: Path
    if root is None:
        voice_root = voices_dir()
    else:
        voice_root = root

    if not voice_root.exists():
        return []

    if not voice_root.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {voice_root}")

    voice_list: list[Voice] = []

    for entry in sorted(voice_root.iterdir()):
        if entry.is_dir():
            voice = load_voice(entry.name, root=voice_root)
            voice_list.append(voice)

    return voice_list
