from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class Voice:
    voice_id: str
    display_name: str
    reference_path: Path | None = None
    transcript: str | None = None


@dataclass(frozen=True)
class AudioResult:
    samples: NDArray[np.float32]
    sample_rate: int


class TTSEngine(Protocol):
    name: str
    supports_cloning: bool
    native_sample_rate: int

    def load(self) -> None: ...

    def warmup(self) -> None: ...

    def synthesize(
        self, text: str, voice: Voice | None = None, speed: float = 1.0
    ) -> AudioResult: ...

    def unload(self) -> None: ...
