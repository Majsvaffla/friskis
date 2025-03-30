import logging
import sys
from typing import Final

__all__ = [
    "logger",
    "configure",
]

LOGGER_NAME: Final[str] = "friskis"

logger = logging.getLogger(LOGGER_NAME)


def configure(is_debugging: bool) -> None:
    default_logger = logging.getLogger(LOGGER_NAME)
    default_level = logging.INFO if sys.stdout.isatty() else logging.WARNING
    default_logger.setLevel(logging.DEBUG if is_debugging else default_level)
    default_logger.addHandler(logging.StreamHandler())
