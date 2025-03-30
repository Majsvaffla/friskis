from typing import Final
from zoneinfo import ZoneInfo

__all__ = [
    "TZ",
    "CREDENTIALS_FILE_NAME",
    "SCHEDULE_FILE_NAME",
]

TZ: Final[ZoneInfo] = ZoneInfo("Europe/Stockholm")

CREDENTIALS_FILE_NAME: Final[str] = "credentials.json"

SCHEDULE_FILE_NAME: Final[str] = "schedule.json"
