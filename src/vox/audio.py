import io
import shutil
import subprocess
from pathlib import Path

import soundfile as sf

from vox.engines.base import AudioResult


def encode_wav(result: AudioResult) -> bytes:
    buffer = io.BytesIO()
    sf.write(
        buffer,
        result.samples,
        samplerate=result.sample_rate,
        format="WAV",
        subtype="PCM_16",
    )
    return buffer.getvalue()


def prepare_reference_audio(src: Path, dest: Path) -> None:

    ffmpeg_path = shutil.which("ffmpeg")

    if ffmpeg_path is None:
        raise RuntimeError(
            "FFmpeg is required to prepare audio. Install it with: brew install ffmpeg"
        )

    if not src.is_file():
        raise FileNotFoundError(f"Source audio file not found: {src}")

    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            [
                ffmpeg_path,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(src),
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "24000",
                "-c:a",
                "pcm_s16le",
                str(dest),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip()
        raise RuntimeError(f"FFmpeg conversion failed: {message}") from error
