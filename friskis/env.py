import os
from pathlib import Path
from typing import Final

__all__ = [
    "PROFILES_LOCATION",
]

PROFILES_LOCATION: Final[Path] = Path(os.environ.get("FRISKIS_PROFILES_LOCATION", default="."))
