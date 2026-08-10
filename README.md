# Vox

Vox is a local, engine-agnostic text-to-speech CLI for Apple Silicon. It turns
text into audio through a stable engine interface and keeps speech generation on
the machine.

## Features

- Local speech generation with no API key or per-character fees.
- A simple `vox speak` command.
- WAV output to a default or user-selected path.
- A swappable TTS engine interface.
- Explicit model loading and unloading for limited unified memory.
- MLX acceleration on Apple Silicon.

Vox currently uses the 8-bit MLX port of Kokoro with the `af_heart` preset voice.

## Requirements

- Apple Silicon Mac
- Python 3.12
- [`uv`](https://docs.astral.sh/uv/)
- `ffmpeg`
- `espeak-ng`

Install the required system tools with Homebrew:

```bash
brew install uv ffmpeg espeak-ng
```

The macOS system Python is not used by this project. `uv` installs and manages the
required Python version and isolated environment.

## Installation

Clone the repository, enter its directory, and synchronize the environment:

```bash
uv sync
```

Confirm that the CLI is available:

```bash
uv run vox --help
```

## Usage

Generate speech with the default output path, `outputs/vox.wav`:

```bash
uv run vox speak "Hello from Vox"
```

Choose a different output path with `--output` or `-o`:

```bash
uv run vox speak "Hello from the Vox command line" --output outputs/hello.wav
uv run vox speak "Using the short option" -o outputs/short-example.wav
```

View help for the `speak` command:

```bash
uv run vox speak --help
```

The CLI creates missing parent directories for the selected output path. Generated
audio under `outputs/` is ignored by Git.

## Architecture

```text
vox speak
    -> TTSEngine implementation
    -> AudioResult (mono float32 samples + sample rate)
    -> WAV encoder
```

Engines return raw audio samples rather than writing files. The CLI owns output-path
handling and WAV encoding, which keeps the engine reusable from future interfaces.

The shared engine lifecycle consists of:

- `load()` — load model weights into memory.
- `warmup()` — prepare a long-running engine before serving real requests.
- `synthesize()` — turn text into an `AudioResult`.
- `unload()` — release the model and cached MLX memory.
