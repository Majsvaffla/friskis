import datetime

from pydantic import BaseModel

__all__ = ["Credentials", "ScheduleEntry", "UpcomingGroupActivity"]


class Credentials(BaseModel):
    email: str
    password: str


class ScheduleEntry(BaseModel):
    weekday: int
    name: str
    location: str
    time: datetime.time


class UpcomingGroupActivity(BaseModel):
    pass
