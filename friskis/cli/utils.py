from argparse import ArgumentTypeError
from pathlib import Path

from friskis.constants import CREDENTIALS_FILE_NAME, SCHEDULE_FILE_NAME

__all__ = [
    "ensure_existing_directory",
]


def ensure_path_exists(path: Path) -> None:
    if not path.exists():
        raise ArgumentTypeError(f"{path} does not exist")


def ensure_existing_directory(value: str) -> Path:
    path = Path(value)
    if not path.is_dir():
        raise ArgumentTypeError(f"{path} is not a directory")
    ensure_path_exists(path)
    ensure_path_exists(path / CREDENTIALS_FILE_NAME)
    ensure_path_exists(path / SCHEDULE_FILE_NAME)
    return path
