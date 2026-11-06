# Vox

Vox turns text into speech on your Mac, in a built-in voice or in a voice you clone
from a short recording. It runs entirely on your machine: no account, no API key, no
per-character fees, and your recordings never leave your computer.

You can use it two ways, and both share the same voice library:

- **The web app**: a local dashboard to type, listen, and manage voices.
- **The `vox` command**: the same features from your terminal.

## Requirements

- A Mac with Apple Silicon (M1 or newer)
- macOS 15 or later
- [Homebrew](https://brew.sh)

Vox runs its models with Apple's MLX framework, so Intel Macs, Windows, and Linux
are not supported.

## Setup

Install the tools Vox needs:

```bash
brew install uv ffmpeg espeak-ng
```

Then, from the project folder, install Vox:

```bash
uv sync
```

Check that it works:

```bash
uv run vox --help
```

The speech models download automatically the first time you use them, so the first
run takes longer and needs an internet connection. After that, everything works
offline.

## Using the web app

Start it with:

```bash
uv run vox init
```

Vox opens in your browser at `http://127.0.0.1:8000`. Press `Ctrl+C` in the terminal
to stop it.

- **Studio**: type some text, pick a voice from the menu, and press the arrow
  (or `⌘ Enter`). Play the result or download it as a WAV file.
- **Voices**: add a new voice, review its transcript, use it in Studio, or delete it.
- **Help**: tips for writing text that sounds natural.

Use `--port 8001` if port 8000 is busy, or `--no-open` to start it without opening
the browser.

### Cloning a voice

1. Record about **15–25 seconds** of one person talking in a quiet room. Voice
   Memos works well, and any audio or video format is fine.
2. Go to **Voices → Add voice**, drop in the recording, and give it an ID like
   `gavin`.
3. Vox writes a draft transcript of the recording. **Listen to the clip and fix any
   wrong words** before saving. The cloned voice is only as good as this transcript.
4. Pick the voice in Studio and start typing.

A cloned voice takes about 20 seconds per generation on an M1, mostly spent loading
the model. The built-in voice takes a few seconds.

## Using the command line

Every command below runs from the project folder. Add `--help` to any of them to
see all options.

**Speak with the built-in voice**

```bash
uv run vox speak "Hello from Vox." -o hello.wav
```

**Speak with a cloned voice**

```bash
uv run vox speak "Hello from Vox." -e qwen -v gavin -o hello.wav
```

Without `-o`, audio is saved to `outputs/vox.wav` and replaces the previous file.

**Manage voices**

```bash
uv run vox voices add recording.m4a --id gavin --name "Gavin"
uv run vox voices list
uv run vox voices remove gavin
```

`voices add` drafts a transcript automatically and prints where it's saved. Open
that file and correct it, or skip the draft by passing your own transcript with
`--transcript-file transcript.txt`. `voices remove` asks first and can't be undone.

**Transcribe a recording**

```bash
uv run vox transcribe recording.m4a
```

## Tips for natural speech

- End sentences with punctuation, and keep them short.
- Write numbers, times, and abbreviations the way they should be spoken:
  "three thirty", not "3:30".
- Leave out emoji, links, and hashtags.
- A cloned voice copies the tone of its recording, so record it the way you want it
  to sound.
- Keep each cloned-voice generation under about a minute and a half of speech.
  Split longer scripts into parts.

The **Help** page in the web app has more tips, examples, and troubleshooting.

## Good to know

- **Your data** lives in `~/Library/Application Support/Vox`. Each voice is a folder
  with its recording, transcript, and settings. To use a different folder, set
  `VOX_DATA_DIR`, for example `VOX_DATA_DIR=~/vox-test uv run vox init`.
- **The CLI and the web app stay in sync.** A voice added in one shows up in the
  other, even while the web app is open.
- **The web app only accepts requests from your own Mac.** It isn't reachable from
  other devices or other websites.
- **Cloned voices speak English only for now.** The model supports more languages,
  but Vox doesn't expose them yet.
- **Only clone voices you have permission to use.**

## Models

| Used for | Model | License |
| --- | --- | --- |
| Built-in voice | [Kokoro 82M](https://huggingface.co/mlx-community/Kokoro-82M-8bit) | Apache 2.0 |
| Voice cloning | [Qwen3-TTS 0.6B Base](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit) | Apache 2.0 |
| Transcription | [Whisper small](https://huggingface.co/mlx-community/whisper-small-asr-6bit) | MIT |

All three run through [MLX-Audio](https://github.com/Blaizzy/mlx-audio).
