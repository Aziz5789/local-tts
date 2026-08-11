import re
from pathlib import Path

from vox.engines.base import Voice

_VOICE_ID_PATTERN = re.compile(r"[a-z0-9_-]+")


def load_voice(voice_id: str, root: Path = Path("voices/dev")) -> Voice:
    normalized_id = voice_id.strip().lower()

    if _VOICE_ID_PATTERN.fullmatch(normalized_id) is None:
        raise ValueError(
            "Invalid voice ID. Use only letters, numbers, underscores, and hyphens."
        )

    reference_path: Path = root / "audio" / f"{normalized_id}.wav"
    transcript_path: Path = root / "transcripts" / f"{normalized_id}.txt"

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
