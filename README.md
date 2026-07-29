# Vox

Vox is a local text-to-speech and voice-cloning toolkit for Apple Silicon.
It is being built as a reusable component with a command-line interface, an API,
and a small browser interface.

## Project goals

- Run speech generation locally without API keys or per-character fees.
- Keep reference audio and generated speech on the machine.
- Place every model behind a stable engine interface.
- Start with a small working audio path before adding voice cloning or a web UI.

## Current milestone

Bootstrap the Python project and generate a WAV file through a Kokoro command-line
smoke test.

## Requirements

- Apple Silicon Mac
- Python 3.12, managed by `uv`
- `ffmpeg`
- `espeak-ng`

Install the system tools with Homebrew:

```bash
brew install uv ffmpeg espeak-ng
```

## Development

Create or synchronize the project environment:

```bash
uv sync
```

Run the current placeholder command:

```bash
uv run vox
```

The macOS system Python is not used for this project.
