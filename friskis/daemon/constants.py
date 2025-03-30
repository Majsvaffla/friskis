import calendar
from typing import Final

__all__ = ["WEEKDAYS"]

WEEKDAYS: Final[list[str]] = [day.lower() for day in calendar.day_name]
