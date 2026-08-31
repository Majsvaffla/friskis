import calendar
from datetime import timedelta
from typing import Final

__all__ = ["WEEKDAYS"]

WEEKDAYS: Final[list[str]] = [day.lower() for day in calendar.day_name]

AUTHORIZATION_REFRESH_INTERVAL: Final = timedelta(minutes=90)
ACTIVITY_REFRESH_INTERVAL: Final = timedelta(days=1)
