from pathlib import Path

import soundfile as sf
import typer

from vox.engines.kokoro_mlx import KokoroEngine
from vox.transcribe import WhisperTranscriber

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


@app.callback()
def main() -> None:
    """Local text-to-speech and voice-cloning toolkit."""


@app.command()
def speak(text: str, output: Path = speak_output_option) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)

    koko_engine = KokoroEngine()

    try:
        koko_engine.load()
        result = koko_engine.synthesize(text=text)
    finally:
        koko_engine.unload()

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
