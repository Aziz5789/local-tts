from pathlib import Path

import soundfile as sf
import typer

from vox.engines.registry import create_engine
from vox.transcribe import WhisperTranscriber
from vox.voices import load_voice

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
