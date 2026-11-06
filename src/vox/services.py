"""Workflows shared by the CLI and the web app.

Nothing here knows about Typer or HTTP. Expected problems with what the user
asked for raise VoxInputError naming the offending field, so each interface
can phrase the error its own way.

Model libraries are imported inside the functions that need them, so listing
or reviewing voices never initializes MLX/Metal.
"""

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from vox.audio import prepare_reference_audio
from vox.engines.base import AudioResult, Voice
from vox.voice_metadata import VoiceMetadata
from vox.voices import (
    InvalidVoice,
    list_voices,
    load_voice,
    load_voice_metadata,
    remove_voice,
    review_transcript,
    save_voice,
    voice_exists,
)


class VoxInputError(ValueError):
    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class VoiceExistsError(VoxInputError):
    pass


class VoiceNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class VoiceDetails:
    voice: Voice
    metadata: VoiceMetadata


@dataclass(frozen=True)
class VoiceLibrary:
    voices: list[VoiceDetails]
    invalid: list[InvalidVoice]


def _require_existing_voice(voice_id: str) -> None:
    try:
        exists = voice_exists(voice_id=voice_id)
    except ValueError as error:
        raise VoxInputError(str(error), field="voice") from error

    if not exists:
        raise VoiceNotFoundError(f"Voice not found: {voice_id}")


def get_voice(voice_id: str) -> VoiceDetails:
    _require_existing_voice(voice_id)
    voice = load_voice(voice_id)
    return VoiceDetails(voice=voice, metadata=load_voice_metadata(voice.voice_id))


def get_voice_library() -> VoiceLibrary:
    listing = list_voices()
    details = [
        VoiceDetails(voice=voice, metadata=load_voice_metadata(voice.voice_id))
        for voice in listing.voices
    ]
    return VoiceLibrary(voices=details, invalid=listing.invalid)


def update_voice_transcript(voice_id: str, transcript: str) -> VoiceDetails:
    _require_existing_voice(voice_id)

    try:
        review_transcript(voice_id=voice_id, transcript=transcript)
    except ValueError as error:
        raise VoxInputError(str(error), field="transcript") from error

    return get_voice(voice_id)


def delete_voice(voice_id: str) -> None:
    """Permanently delete a voice. Broken voices can be deleted too."""
    _require_existing_voice(voice_id)
    remove_voice(voice_id)


def enroll_voice(
    *,
    audio_path: Path,
    voice_id: str,
    display_name: str | None = None,
    transcript: str | None = None,
    original_filename: str | None = None,
) -> VoiceDetails:
    """Prepare audio, draft a transcript if none was given, and store the voice.

    A supplied transcript counts as reviewed. A Whisper draft does not; it
    must be reviewed before the voice can be trusted.
    """
    try:
        already_exists = voice_exists(voice_id=voice_id)
    except ValueError as error:
        raise VoxInputError(str(error), field="id") from error

    if already_exists:
        raise VoiceExistsError(
            f"Voice ID {voice_id} already exists. "
            "Choose another ID or remove the existing voice first.",
            field="id",
        )

    if transcript is not None and not transcript.strip():
        raise VoxInputError("Transcript can't be empty.", field="transcript")

    with TemporaryDirectory(prefix="vox-voice-") as temporary_directory:
        prepared_audio_path = Path(temporary_directory) / "reference.wav"

        try:
            prepare_reference_audio(audio_path, prepared_audio_path)
        except FileNotFoundError as error:
            raise VoxInputError(str(error), field="audio") from error

        transcript_generated = transcript is None
        transcript_model_id: str | None = None

        if transcript is None:
            from vox.transcribe import DEFAULT_WHISPER_MODEL_ID, transcribe_audio

            transcript = transcribe_audio(audio=prepared_audio_path)
            transcript_model_id = DEFAULT_WHISPER_MODEL_ID

            if not transcript.strip():
                raise VoxInputError(
                    "Transcription generated no text. Is there speech in the audio?",
                    field="audio",
                )

        voice = save_voice(
            voice_id=voice_id,
            reference_path=prepared_audio_path,
            transcript=transcript,
            original_filename=original_filename or audio_path.name,
            display_name=display_name,
            transcript_generated=transcript_generated,
            transcript_model_id=transcript_model_id,
            transcript_language="en",
        )

    return VoiceDetails(voice=voice, metadata=load_voice_metadata(voice.voice_id))


def synthesize_speech(
    *, text: str, engine_name: str, voice_id: str | None = None
) -> AudioResult:
    from vox.engines.registry import create_engine

    if not text.strip():
        raise VoxInputError("Text cannot be empty.", field="text")

    try:
        engine = create_engine(engine_name)
    except ValueError as error:
        raise VoxInputError(str(error), field="engine") from error

    selected_voice: Voice | None = None

    if engine.supports_cloning:
        if voice_id is None:
            raise VoxInputError(
                f"A voice is required for engine '{engine_name}'.", field="voice"
            )

        try:
            selected_voice = load_voice(voice_id)
        except (ValueError, FileNotFoundError) as error:
            raise VoxInputError(str(error), field="voice") from error
    elif voice_id is not None:
        raise VoxInputError(
            f"Engine '{engine_name}' does not support stored voices.", field="voice"
        )

    try:
        engine.load()
        return engine.synthesize(text=text, voice=selected_voice)
    finally:
        engine.unload()


def transcribe_file(audio_path: Path, language: str = "en") -> str:
    from vox.transcribe import transcribe_audio

    if not audio_path.is_file():
        raise VoxInputError(f"Audio file not found: {audio_path}", field="audio")

    return transcribe_audio(audio=audio_path, language=language)
