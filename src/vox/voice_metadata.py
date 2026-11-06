import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import soundfile as sf

from vox.files import write_text_atomically

CURRENT_SCHEMA_VERSION = 1
METADATA_FILENAME = "metadata.json"


@dataclass(frozen=True)
class AudioMetadata:
    format: str
    sample_rate: int
    channels: int
    duration_seconds: float


@dataclass(frozen=True)
class TranscriptMetadata:
    # None means unknown: the voice was enrolled before metadata existed.
    generated: bool | None
    language: str | None
    model_id: str | None
    reviewed_at: str | None


@dataclass(frozen=True)
class VoiceMetadata:
    schema_version: int
    voice_id: str
    display_name: str
    created_at: str | None
    updated_at: str | None
    original_filename: str | None
    audio: AudioMetadata
    transcript: TranscriptMetadata


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _read_audio_metadata(reference_path: Path) -> AudioMetadata:
    audio_info = sf.info(reference_path)

    return AudioMetadata(
        format=audio_info.format.lower(),
        sample_rate=audio_info.samplerate,
        channels=audio_info.channels,
        duration_seconds=audio_info.duration,
    )


def write_voice_metadata(metadata: VoiceMetadata, path: Path) -> None:
    data = asdict(metadata)
    json_text = json.dumps(data, indent=2)
    write_text_atomically(path, json_text + "\n")


def read_voice_metadata(path: Path) -> VoiceMetadata:
    if not path.is_file():
        raise FileNotFoundError(f"{path} is not a file.")

    json_text = path.read_text(encoding="utf-8")

    try:
        data = json.loads(json_text)

        if data["schema_version"] != CURRENT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported voice metadata schema version: {data['schema_version']}"
            )

        audio = AudioMetadata(**data["audio"])
        transcript = TranscriptMetadata(**data["transcript"])

        metadata = VoiceMetadata(
            schema_version=data["schema_version"],
            voice_id=data["voice_id"],
            display_name=data["display_name"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            original_filename=data["original_filename"],
            audio=audio,
            transcript=transcript,
        )
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError(f"Invalid voice metadata: {path}") from error

    return metadata


def create_voice_metadata(
    *,
    voice_id: str,
    display_name: str,
    original_filename: str,
    reference_path: Path,
    transcript_generated: bool,
    transcript_language: str,
    transcript_model_id: str | None,
) -> VoiceMetadata:
    timestamp = _utc_timestamp()

    transcript_metadata = TranscriptMetadata(
        generated=transcript_generated,
        language=transcript_language,
        model_id=transcript_model_id if transcript_generated else None,
        reviewed_at=None if transcript_generated else timestamp,
    )

    metadata = VoiceMetadata(
        schema_version=CURRENT_SCHEMA_VERSION,
        voice_id=voice_id,
        display_name=display_name,
        created_at=timestamp,
        updated_at=timestamp,
        original_filename=original_filename,
        audio=_read_audio_metadata(reference_path),
        transcript=transcript_metadata,
    )

    return metadata


def mark_transcript_reviewed(metadata: VoiceMetadata) -> VoiceMetadata:
    timestamp = _utc_timestamp()

    return replace(
        metadata,
        updated_at=timestamp,
        transcript=replace(metadata.transcript, reviewed_at=timestamp),
    )


def create_legacy_voice_metadata(
    *,
    voice_id: str,
    display_name: str,
    reference_path: Path,
) -> VoiceMetadata:
    """Describe a voice enrolled before metadata.json existed.

    Facts that were never recorded stay None instead of being guessed. The
    reference file's creation time is the enrollment time, because enrollment
    wrote it and nothing rewrites it afterwards.
    """
    reference_stat = reference_path.stat()
    created_seconds = getattr(reference_stat, "st_birthtime", reference_stat.st_mtime)
    created_at = datetime.fromtimestamp(created_seconds, UTC).isoformat()

    # Legacy transcripts were reviewed by hand before this format existed.
    transcript_metadata = TranscriptMetadata(
        generated=None,
        language="en",
        model_id=None,
        reviewed_at=_utc_timestamp(),
    )

    return VoiceMetadata(
        schema_version=CURRENT_SCHEMA_VERSION,
        voice_id=voice_id,
        display_name=display_name,
        created_at=created_at,
        updated_at=_utc_timestamp(),
        original_filename=None,
        audio=_read_audio_metadata(reference_path),
        transcript=transcript_metadata,
    )
