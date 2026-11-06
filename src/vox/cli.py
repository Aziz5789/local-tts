from pathlib import Path
from tempfile import TemporaryDirectory

import soundfile as sf
import typer

from vox.audio import prepare_reference_audio
from vox.voices import list_voices, load_voice, save_voice, voice_exists

app = typer.Typer()

speak_output_option = typer.Option(
    Path("outputs/vox.wav"),
    "--output",
    "-o",
    help="Path for the generated WAV file.",
)

transcribe_output_option = typer.Option(
    None,
    "--output",
    "-o",
    help="Path for the generated transcript file.",
)

engine_option = typer.Option(
    "kokoro", "--engine", "-e", help="TTS engine to use: kokoro or qwen."
)

voice_option = typer.Option(
    None, "--voice", "-v", help="Stored voice ID required by cloning engines."
)

voice_id_option = typer.Option(..., "--id", "-i", help="ID for the new voice.")

display_name_option = typer.Option(
    None, "--name", "-n", help="Display name. Defaults to a name built from the ID."
)

transcript_file_option = typer.Option(
    None,
    "--transcript-file",
    "-t",
    help="Reviewed transcript of the audio. Omit it to generate a draft.",
)

voices_app = typer.Typer(help="Manage stored voices.")
app.add_typer(voices_app, name="voices")


@app.callback()
def main() -> None:
    """Local text-to-speech and voice-cloning toolkit."""


@app.command()
def speak(
    text: str,
    engine: str = engine_option,
    voice_id: str | None = voice_option,
    output: Path = speak_output_option,
) -> None:
    # Import lazily so non-inference commands do not initialize MLX/Metal.
    from vox.engines.registry import create_engine

    try:
        tts_engine = create_engine(engine)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="--engine") from error

    if tts_engine.supports_cloning:
        if voice_id is None:
            raise typer.BadParameter(
                f"--voice is required for engine '{engine}'.",
                param_hint="--voice",
            )
        try:
            selected_voice = load_voice(voice_id)
        except (ValueError, FileNotFoundError) as error:
            raise typer.BadParameter(
                str(error),
                param_hint="--voice",
            ) from error
    else:
        if voice_id is not None:
            raise typer.BadParameter(
                f"Engine '{engine}' does not support stored voices.",
                param_hint="--voice",
            )
        selected_voice = None

    try:
        tts_engine.load()
        result = tts_engine.synthesize(text=text, voice=selected_voice)
    finally:
        tts_engine.unload()

    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output, result.samples, samplerate=result.sample_rate)
    typer.echo(f"Audio file generated to path: {output}")


@app.command()
def transcribe(
    audio: Path,
    output: Path | None = transcribe_output_option,
) -> None:
    from vox.transcribe import transcribe_audio

    # TO-DO - implement the multiple language support
    text = transcribe_audio(audio=audio)

    if output is None:
        typer.echo(text)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
        typer.echo(f"Transcript saved to {output}")


@voices_app.command("list")
def list_saved_voices() -> None:
    listing = list_voices()

    if not listing.voices and not listing.invalid:
        typer.echo("No saved voices.")
        return

    for voice in listing.voices:
        typer.echo(f"{voice.voice_id} - {voice.display_name}")

    for invalid_voice in listing.invalid:
        typer.echo(
            f"{invalid_voice.voice_id} - unusable: {invalid_voice.reason}", err=True
        )


@voices_app.command("add")
def add_voices(
    audio: Path,
    voice_id: str = voice_id_option,
    display_name: str | None = display_name_option,
    transcript_file: Path | None = transcript_file_option,
) -> None:
    try:
        already_exists = voice_exists(voice_id=voice_id)
    except ValueError as error:
        raise typer.BadParameter(message=str(error), param_hint="--id") from error

    if already_exists:
        raise typer.BadParameter(
            f"Voice ID {voice_id} already exists. "
            "Choose another ID or remove the existing voice first.",
            param_hint="--id",
        )

    if transcript_file is not None and not transcript_file.is_file():
        raise typer.BadParameter(
            f"Transcript file is not a valid path: {transcript_file}",
            param_hint="--transcript-file",
        )

    with TemporaryDirectory(prefix="vox-voice-") as temporary_directory:
        temporary_path = Path(temporary_directory)
        prepared_audio_path = temporary_path / "reference.wav"
        prepare_reference_audio(audio, prepared_audio_path)

        transcript_generated = transcript_file is None
        transcript_model_id: str | None = None

        if transcript_file is not None:
            transcript = transcript_file.read_text(encoding="utf-8")

        else:
            from vox.transcribe import DEFAULT_WHISPER_MODEL_ID, transcribe_audio

            transcript = transcribe_audio(audio=prepared_audio_path)
            transcript_model_id = DEFAULT_WHISPER_MODEL_ID

        clean_transcript = transcript.strip()

        if not clean_transcript:
            if transcript_file is None:
                raise typer.BadParameter("Transcription generated no text.")
            else:
                raise typer.BadParameter(
                    f"Transcript file can't be empty: {transcript_file}"
                )

        voice = save_voice(
            voice_id=voice_id,
            reference_path=prepared_audio_path,
            transcript=clean_transcript,
            original_filename=audio.name,
            display_name=display_name,
            transcript_generated=transcript_generated,
            transcript_model_id=transcript_model_id,
            transcript_language="en",
        )

    transcript_path = voice.reference_path.parent / "transcript.txt"

    typer.echo(f"Voice saved: {voice.voice_id} ({voice.display_name})")
    typer.echo(f"Reference audio: {voice.reference_path}")
    typer.echo(f"Transcript: {transcript_path}")

    if transcript_file is None:
        typer.echo(
            "Review required: Make sure the generated transcript accurately "
            "matches the reference audio before using this voice."
        )
