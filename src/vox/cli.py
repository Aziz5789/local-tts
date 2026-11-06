from pathlib import Path

import soundfile as sf
import typer

from vox.services import (
    VoiceNotFoundError,
    VoxInputError,
    delete_voice,
    enroll_voice,
    get_voice_library,
    synthesize_speech,
    transcribe_file,
)

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

skip_confirmation_option = typer.Option(
    False, "--yes", "-y", help="Delete without asking for confirmation."
)

port_option = typer.Option(8000, "--port", "-p", help="Port for the web app.")

open_browser_option = typer.Option(
    True, "--open/--no-open", help="Open the web app in your browser."
)

voices_app = typer.Typer(help="Manage stored voices.")
app.add_typer(voices_app, name="voices")

# Maps the field named by a VoxInputError to how the CLI spells that input.
_PARAM_HINTS = {
    "text": "TEXT",
    "engine": "--engine",
    "voice": "--voice",
    "audio": "AUDIO",
    "id": "--id",
    "transcript": "--transcript-file",
}


def _bad_parameter(error: VoxInputError) -> typer.BadParameter:
    return typer.BadParameter(str(error), param_hint=_PARAM_HINTS.get(error.field))


def _fail(error: Exception) -> typer.Exit:
    typer.echo(f"Error: {error}", err=True)
    return typer.Exit(code=1)


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
        result = synthesize_speech(text=text, engine_name=engine, voice_id=voice_id)
    except VoxInputError as error:
        raise _bad_parameter(error) from error
    except RuntimeError as error:
        raise _fail(error) from error

    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output, result.samples, samplerate=result.sample_rate)
    typer.echo(f"Audio file generated to path: {output}")


@app.command()
def transcribe(
    audio: Path,
    output: Path | None = transcribe_output_option,
) -> None:
    # TO-DO - implement the multiple language support
    try:
        text = transcribe_file(audio)
    except VoxInputError as error:
        raise _bad_parameter(error) from error

    if output is None:
        typer.echo(text)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
        typer.echo(f"Transcript saved to {output}")


@app.command()
def init(
    port: int = port_option,
    open_browser: bool = open_browser_option,
) -> None:
    """Start the Vox web app on this Mac. It only listens on localhost."""
    import threading
    import webbrowser

    import uvicorn

    from vox.api import create_app

    url = f"http://127.0.0.1:{port}"
    typer.echo(f"Vox web app running at {url} (press Ctrl+C to stop)")

    if open_browser:
        # Give the server a moment to start before the browser asks for the page.
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")


@voices_app.command("list")
def list_saved_voices() -> None:
    library = get_voice_library()

    if not library.voices and not library.invalid:
        typer.echo("No saved voices.")
        return

    for details in library.voices:
        voice = details.voice
        review_note = (
            ""
            if details.metadata.transcript.reviewed_at
            else " (transcript not reviewed)"
        )
        typer.echo(f"{voice.voice_id} - {voice.display_name}{review_note}")

    for invalid_voice in library.invalid:
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
    transcript: str | None = None

    if transcript_file is not None:
        if not transcript_file.is_file():
            raise typer.BadParameter(
                f"Transcript file is not a valid path: {transcript_file}",
                param_hint="--transcript-file",
            )
        transcript = transcript_file.read_text(encoding="utf-8")

    try:
        details = enroll_voice(
            audio_path=audio,
            voice_id=voice_id,
            display_name=display_name,
            transcript=transcript,
        )
    except VoxInputError as error:
        raise _bad_parameter(error) from error
    except RuntimeError as error:
        raise _fail(error) from error

    voice = details.voice
    transcript_path = voice.reference_path.parent / "transcript.txt"

    typer.echo(f"Voice saved: {voice.voice_id} ({voice.display_name})")
    typer.echo(f"Reference audio: {voice.reference_path}")
    typer.echo(f"Transcript: {transcript_path}")

    if transcript_file is None:
        typer.echo(
            "Review required: Make sure the generated transcript accurately "
            "matches the reference audio before using this voice."
        )


@voices_app.command("remove")
def remove_saved_voice(
    voice_id: str,
    skip_confirmation: bool = skip_confirmation_option,
) -> None:
    """Permanently delete a stored voice."""
    if not skip_confirmation:
        typer.confirm(
            f"Permanently delete voice '{voice_id}'? This can't be undone.", abort=True
        )

    try:
        delete_voice(voice_id)
    except VoxInputError as error:
        raise typer.BadParameter(str(error), param_hint="VOICE_ID") from error
    except (VoiceNotFoundError, OSError) as error:
        raise _fail(error) from error

    typer.echo(f"Deleted voice '{voice_id}'.")
