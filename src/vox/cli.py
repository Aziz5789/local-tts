from pathlib import Path

import soundfile as sf
import typer

from vox.engines.kokoro_mlx import KokoroEngine

app = typer.Typer()

output_option = typer.Option(
    Path("outputs/vox.wav"),
    "--output",
    "-o",
    help="Path for the generated WAV file.",
)


@app.callback()
def main() -> None:
    """Local text-to-speech and voice-cloning toolkit."""


@app.command()
def speak(text: str, output: Path = output_option) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)

    koko_engine = KokoroEngine()

    try:
        koko_engine.load()
        result = koko_engine.synthesize(text=text)
        sf.write(output, result.samples, samplerate=result.sample_rate)
    finally:
        koko_engine.unload()

    typer.echo(f"Audio file generated to path: {output}")
