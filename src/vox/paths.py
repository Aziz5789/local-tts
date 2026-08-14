import os
from pathlib import Path

import platformdirs


def data_dir() -> Path:
    override_path_string = os.getenv("VOX_DATA_DIR")

    if override_path_string and override_path_string.strip():
        return Path(override_path_string.strip()).expanduser()

    return platformdirs.user_data_path("Vox")


def voices_dir() -> Path:
    return data_dir() / "voices"
