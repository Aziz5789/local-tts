import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from vox.engines.base import Voice
from vox.paths import voices_dir
from vox.voice_metadata import (
    METADATA_FILENAME,
    VoiceMetadata,
    create_legacy_voice_metadata,
    create_voice_metadata,
    read_voice_metadata,
    write_voice_metadata,
)

_VOICE_ID_PATTERN = re.compile(r"[a-z0-9_-]+")


@dataclass(frozen=True)
class InvalidVoice:
    voice_id: str
    reason: str


@dataclass(frozen=True)
class VoiceListing:
    voices: list[Voice]
    invalid: list[InvalidVoice]


def _get_root_directory(root: Path | None) -> Path:
    if root is None:
        return voices_dir()
    else:
        return root


def _normalize_voice_id(voice_id: str) -> str:
    normalized_id = voice_id.strip().lower()

    if _VOICE_ID_PATTERN.fullmatch(normalized_id) is None:
        raise ValueError(
            "Invalid voice ID. Use only letters, numbers, underscores, and hyphens."
        )

    return normalized_id


def _default_display_name(normalized_id: str) -> str:
    return re.sub(r"[_-]+", " ", normalized_id).title()


def load_voice_metadata(voice_id: str, root: Path | None = None) -> VoiceMetadata:
    normalized_id = _normalize_voice_id(voice_id)

    voice_root = _get_root_directory(root=root)
    voice_directory: Path = voice_root / normalized_id
    metadata_path: Path = voice_directory / METADATA_FILENAME

    if not voice_directory.is_dir():
        raise FileNotFoundError(f"Voice not found: {normalized_id}")

    # Voices enrolled before metadata existed get it written once, on first use.
    if not metadata_path.exists():
        reference_path: Path = voice_directory / "reference.wav"

        if not reference_path.is_file():
            raise FileNotFoundError(f"Reference audio file not found: {reference_path}")

        legacy_metadata = create_legacy_voice_metadata(
            voice_id=normalized_id,
            display_name=_default_display_name(normalized_id),
            reference_path=reference_path,
        )
        write_voice_metadata(metadata=legacy_metadata, path=metadata_path)

    metadata = read_voice_metadata(metadata_path)

    if metadata.voice_id != normalized_id:
        raise ValueError(
            f"Voice metadata ID '{metadata.voice_id}' does not match "
            f"its directory '{normalized_id}': {metadata_path}"
        )

    return metadata


def load_voice(voice_id: str, root: Path | None = None) -> Voice:
    normalized_id = _normalize_voice_id(voice_id)

    voice_root = _get_root_directory(root=root)

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

    metadata = load_voice_metadata(voice_id=normalized_id, root=voice_root)

    return Voice(
        voice_id=normalized_id,
        display_name=metadata.display_name,
        reference_path=reference_path,
        transcript=transcript,
    )


def save_voice(
    voice_id: str,
    reference_path: Path,
    transcript: str,
    root: Path | None = None,
    *,
    original_filename: str,
    transcript_generated: bool,
    display_name: str | None = None,
    transcript_model_id: str | None = None,
    transcript_language: str = "en",
) -> Voice:
    normalized_id = _normalize_voice_id(voice_id)

    if not reference_path.is_file():
        raise FileNotFoundError(f"Reference audio file not found: {reference_path}")

    clean_transcript = transcript.strip()

    if not clean_transcript:
        raise ValueError("Voice transcript cannot be empty.")

    clean_display_name = (display_name or "").strip() or _default_display_name(
        normalized_id
    )

    voice_root = _get_root_directory(root=root)

    voice_directory = voice_root / normalized_id
    voice_directory.mkdir(parents=True, exist_ok=False)

    shutil.copyfile(reference_path, voice_directory / "reference.wav")

    transcript_path: Path = voice_directory / "transcript.txt"
    transcript_path.write_text(clean_transcript + "\n", encoding="utf-8")

    # Write metadata before loading, or load_voice would treat the new voice as
    # legacy and invent metadata for it.
    metadata = create_voice_metadata(
        voice_id=normalized_id,
        display_name=clean_display_name,
        original_filename=original_filename,
        reference_path=voice_directory / "reference.wav",
        transcript_generated=transcript_generated,
        transcript_language=transcript_language,
        transcript_model_id=transcript_model_id,
    )
    write_voice_metadata(metadata=metadata, path=voice_directory / METADATA_FILENAME)

    return load_voice(voice_id=normalized_id, root=voice_root)


def list_voices(root: Path | None = None) -> VoiceListing:
    voice_root = _get_root_directory(root=root)

    if not voice_root.exists():
        return VoiceListing(voices=[], invalid=[])

    if not voice_root.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {voice_root}")

    voice_list: list[Voice] = []
    invalid_list: list[InvalidVoice] = []

    for entry in sorted(voice_root.iterdir()):
        # Hidden directories are never voices (Finder files, future staging).
        if not entry.is_dir() or entry.name.startswith("."):
            continue

        # One broken voice should be reported, not hide the rest of the library.
        try:
            voice_list.append(load_voice(entry.name, root=voice_root))
        except (ValueError, OSError, RuntimeError) as error:
            invalid_list.append(InvalidVoice(voice_id=entry.name, reason=str(error)))

    return VoiceListing(voices=voice_list, invalid=invalid_list)


def voice_exists(voice_id: str, root: Path | None = None) -> bool:
    normalized_id = _normalize_voice_id(voice_id=voice_id)
    voice_root = _get_root_directory(root=root)
    voice_directory: Path = voice_root / normalized_id

    return voice_directory.exists()
