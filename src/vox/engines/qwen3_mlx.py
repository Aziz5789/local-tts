import gc
from typing import Any

import mlx.core as mx
import numpy as np
from mlx_audio.tts.utils import load_model

from vox.engines.base import AudioResult, Voice


class Qwen3Engine:
    name: str = "qwen3_mlx"
    supports_cloning: bool = True
    native_sample_rate: int = 24000

    def __init__(
        self,
        model_id: str = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
    ) -> None:
        self._model_id = model_id
        self._model: Any | None = None

    def load(self) -> None:
        if self._model is not None:
            return

        self._model = load_model(self._model_id)

    def unload(self) -> None:
        if self._model is None:
            return
        self._model = None
        gc.collect()
        mx.clear_cache()

    def synthesize(
        self,
        text: str,
        voice: Voice | None = None,
        speed: float = 1.0,
    ) -> AudioResult:
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load() before synthesize().")

        clean_text = text.strip()

        if not clean_text:
            raise ValueError("Input text cannot be empty.")

        if voice is None:
            raise ValueError("A voice is required for Qwen voice cloning.")

        if voice.reference_path is None:
            raise ValueError("Voice reference path is required.")

        if not voice.reference_path.is_file():
            raise FileNotFoundError(
                f"Reference audio file not found: {voice.reference_path}"
            )

        if voice.transcript is None:
            raise ValueError("Voice transcript is required.")

        if not voice.transcript.strip():
            raise ValueError("Voice transcript cannot be empty.")

        if speed != 1.0:
            raise NotImplementedError("Qwen3Engine currently supports only speed=1.0.")

        generation = self._model.generate(
            text=clean_text,
            ref_audio=str(voice.reference_path),
            ref_text=voice.transcript.strip(),
            lang_code="english",
            temperature=0.7,
            top_p=0.9,
            top_k=50,
            repetition_penalty=1.1,
            max_tokens=1200,
            verbose=False,
        )

        segments: list[np.ndarray] = []
        sample_rate: int | None = None

        for gen in generation:
            if sample_rate is None:
                sample_rate = gen.sample_rate
            elif sample_rate != gen.sample_rate:
                raise RuntimeError(
                    f"Qwen3 returned inconsistent sample rates: "
                    f"{sample_rate} and {gen.sample_rate}."
                )

            segments.append(np.asarray(gen.audio, dtype=np.float32))

        if not segments or sample_rate is None:
            raise RuntimeError("Qwen3 generated no audio.")

        return AudioResult(
            samples=np.concatenate(segments),
            sample_rate=sample_rate,
        )

    def warmup(self, voice: Voice | None = None) -> None:
        if voice is None:
            raise ValueError("A voice is required for Qwen warmup.")

        self.synthesize("Warmup.", voice=voice)
