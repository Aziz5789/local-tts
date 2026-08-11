from collections.abc import Callable

from vox.engines.base import TTSEngine
from vox.engines.kokoro_mlx import KokoroEngine
from vox.engines.qwen3_mlx import Qwen3Engine

EngineFactory = Callable[[], TTSEngine]

_ENGINE_FACTORIES: dict[str, EngineFactory] = {
    "kokoro": KokoroEngine,
    "qwen": Qwen3Engine,
}


def create_engine(name: str) -> TTSEngine:
    normalized_name = name.strip().lower()

    factory = _ENGINE_FACTORIES.get(normalized_name)

    if factory is None:
        available = ", ".join(sorted(_ENGINE_FACTORIES))
        raise ValueError(
            f"Unknown TTS engine '{name}'. Available engines: {available}."
        )

    return factory()
