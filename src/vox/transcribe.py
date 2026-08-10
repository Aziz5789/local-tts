import gc
import re
from pathlib import Path
from typing import Any

import mlx.core as mx
from mlx_audio.stt.utils import load_model

_TRAILING_SPACED_PERIODS = re.compile(r"(?:\s+\.){2,}$")


class WhisperTranscriber:
    def __init__(self, model_id: str = "mlx-community/whisper-small-asr-6bit") -> None:
        self._model_id = model_id
        self._model: Any | None = None  # S tier type safety

    def load(self) -> None:
        if self._model is not None:
            return

        self._model = load_model(self._model_id)

    def transcribe(self, audio_path: Path, language: str = "en") -> str:
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load() before transcribe().")

        if not audio_path.is_file():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        result = self._model.generate(str(audio_path), language=language, verbose=None)

        text = result.text.strip()
        return _TRAILING_SPACED_PERIODS.sub("", text)

    def unload(self) -> None:
        if self._model is None:
            return
        self._model = None
        gc.collect()
        mx.clear_cache()
