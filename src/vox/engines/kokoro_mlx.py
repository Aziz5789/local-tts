import gc

import mlx.core as mx
import numpy as np
from mlx_audio.tts.models.kokoro import Model as KokoroModel
from mlx_audio.tts.utils import load_model

from vox.engines.base import AudioResult, Voice


class KokoroEngine:
    name: str = "kokoro_mlx"
    supports_cloning: bool = False
    native_sample_rate: int = 24000

    def __init__(
        self,
        model_id: str = "mlx-community/Kokoro-82M-8bit",
        default_voice: str = "af_heart",
    ) -> None:
        self._model_id = model_id
        self._default_voice = default_voice
        self._model: KokoroModel | None = None

    def load(self) -> None:
        if self._model is not None:
            return

        model = load_model(self._model_id)

        if not isinstance(model, KokoroModel):
            raise TypeError("Configured model is not a Kokoro model.")

        self._model = model

    def unload(self) -> None:
        if self._model is None:
            return
        self._model = None
        gc.collect()
        mx.clear_cache()

    def synthesize(
        self, text: str, voice: Voice | None = None, speed: float = 1.0
    ) -> AudioResult:
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load() before synthesize().")

        clean_text = text.strip()

        if not clean_text:
            raise ValueError("Input text cannot be empty.")

        if speed <= 0:
            raise ValueError("Speed must be a positive value.")

        selected_voice = self._default_voice if voice is None else voice.voice_id

        generation = self._model.generate(clean_text, voice=selected_voice, speed=speed)

        segments: list[np.ndarray] = []
        sample_rate: int | None = None

        for gen in generation:
            segments.append(np.asarray(gen.audio, dtype=np.float32))
            sample_rate = gen.sample_rate

        if not segments or sample_rate is None:
            raise RuntimeError("Kokoro generated no audio.")

        return AudioResult(
            samples=np.concatenate(segments),
            sample_rate=sample_rate,
        )

    def warmup(self, voice: Voice | None = None) -> None:
        self.synthesize("Warmup.")
