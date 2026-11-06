import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import TypeVar

T = TypeVar("T")


class InferenceWorker:
    """Runs model work one job at a time on a single dedicated thread.

    MLX crashes outright when two threads use the GPU at once, and FastAPI
    happily serves concurrent requests. Every MLX call from the web app goes
    through here, so jobs queue instead of colliding. Running one job at a time
    also keeps Whisper and Qwen from ever sharing memory.
    """

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vox-mlx")

    async def run(self, function: Callable[..., T], /, *args, **kwargs) -> T:
        loop = asyncio.get_running_loop()
        # The event loop stays free to serve other requests while this waits.
        return await loop.run_in_executor(
            self._executor, partial(function, *args, **kwargs)
        )

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)
