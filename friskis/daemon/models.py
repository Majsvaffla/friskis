import datetime

from pydantic import BaseModel

__all__ = ["Credentials", "ScheduleEntry"]


class Credentials(BaseModel):
    email: str
    password: str


class ScheduleEntry(BaseModel):
    weekday: int
    name: str
    location: str
    time: datetime.time
