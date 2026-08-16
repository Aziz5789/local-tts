from pathlib import Path
from tempfile import TemporaryDirectory

import soundfile as sf
import typer

from vox.audio import prepare_reference_audio
from vox.voices import list_voices, load_voice, save_voice

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
    from vox.transcribe import WhisperTranscriber

    transcriber = WhisperTranscriber()

    try:
        transcriber.load()
        text = transcriber.transcribe(audio_path=audio)
    finally:
        transcriber.unload()

    if output is None:
        typer.echo(text)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
        typer.echo(f"Transcript saved to {output}")


@voices_app.command("list")
def list_saved_voices() -> None:
    voices_list = list_voices()

    if not voices_list:
        typer.echo("No saved voices.")
    else:
        for voice in voices_list:
            typer.echo(f"{voice.voice_id} - {voice.display_name}")


@voices_app.command("add")
def add_voices(
    audio: Path,
    voice_id: str = typer.Option(..., "--id", "-i"),
    transcript_file: Path = typer.Option(..., "--transcript-file", "-t"),
) -> None:

    if not transcript_file.is_file():
        raise typer.BadParameter(
            f"Transcript file is not a valid path: {transcript_file}"
        )

    transcript = transcript_file.read_text(encoding="utf-8")

    clean_transcript = transcript.strip()

    if not clean_transcript:
        raise typer.BadParameter(f"Transcript file can't be empty: {transcript_file}")

    with TemporaryDirectory(prefix="vox-voice-") as temporary_directory:
        temporary_path = Path(temporary_directory)
        prepared_audio_path = temporary_path / "reference.wav"
        prepare_reference_audio(audio, prepared_audio_path)

        voice = save_voice(
            voice_id=voice_id,
            reference_path=prepared_audio_path,
            transcript=clean_transcript,
        )

    typer.echo(f"{voice.voice_id} - {voice.reference_path}")
