from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event
from time import sleep
from typing import TYPE_CHECKING, Literal

from friskis.api import actions as api
from friskis.api.exceptions import BookingClashesWithOtherBooking, TooEarlyToBook
from friskis.api.models import (
    Authorization,
    Booking,
    GroupActivity,
    GroupActivityBooking,
    WaitingListBooking,
)
from friskis.constants import CREDENTIALS_FILE_NAME, SCHEDULE_FILE_NAME, TZ
from friskis.daemon.models import Credentials, ScheduleEntry
from friskis.utils.logging import logger

from .constants import ACTIVITY_REFRESH_INTERVAL, AUTHORIZATION_REFRESH_INTERVAL

if TYPE_CHECKING:
    from collections.abc import Iterator

    NotBookedReason = Literal["too_early", "clashing_booking"]

__all__ = [
    "initialize_activities",
    "authorize_profile",
    "get_upcoming_activities",
    "book",
    "is_time_to_book",
]


def _read_credentials(location: Path) -> Credentials:
    assert location.is_dir()
    credentials_path = location / CREDENTIALS_FILE_NAME
    return Credentials(**json.loads(credentials_path.read_text(encoding="utf8")))


def _read_schedule(location: Path) -> list[ScheduleEntry]:
    assert location.is_dir()
    schedule_path = location / SCHEDULE_FILE_NAME
    if not Path(schedule_path).exists():
        return []
    return [ScheduleEntry(**d) for d in json.loads(schedule_path.read_text(encoding="utf8"))]


def initialize_activities(profile_location: Path) -> dict[int, GroupActivity]:
    logger.debug(f"Initializing bookable activities for {profile_location.stem}...")
    schedule = _read_schedule(profile_location)
    activities: dict[int, GroupActivity] = {}
    for activity in get_upcoming_activities(schedule):
        logger.debug(
            f"Found upcoming activity {activity.name=} "
            f"at {activity.duration.start.date()=} "
            f"for {profile_location.stem=}."
        )
        activities[activity.id] = activity
    return activities


def authorize_profile(profile_location: Path) -> Authorization:
    logger.debug(f"Setting up authorization for {profile_location.stem}...")
    credentials = _read_credentials(profile_location)
    return api.log_in(**credentials.model_dump())


def _get_upcoming_activity(entry: ScheduleEntry) -> GroupActivity | None:
    today = datetime.now(TZ).date()
    activity_date = today + timedelta(days=1)
    while activity_date.isoweekday() != entry.weekday:
        activity_date += timedelta(days=1)
    business_unit = api.get_business_unit(entry.location)
    activity = api.get_group_activity(entry.name, activity_date, business_unit, entry.time)
    return activity


def get_upcoming_activities(
    schedule: list[ScheduleEntry],
) -> Iterator[GroupActivity]:
    for entry in schedule:
        activity = _get_upcoming_activity(entry)
        if activity:
            yield activity
        else:
            logger.error(f"Activity {entry.name} at {entry.location} {entry.time.isoformat()} is not scheduled.")


def is_bookable(activity: GroupActivity, authorization: Authorization) -> bool:
    if activity.cancelled:
        logger.warning(
            f"Activity {activity.name} at {activity.businessUnit.name} "
            f"{activity.duration.start.astimezone(TZ).isoformat()} is cancelled.",
        )
        return False
    for booking in api.get_bookings(authorization):
        if isinstance(booking, GroupActivityBooking):
            if activity.id == booking.groupActivity.id:
                logger.info(
                    f"{booking.customer.id} is already booked for activity {activity.name} at "
                    f"{activity.businessUnit.name} {activity.duration.start.astimezone(TZ).isoformat()}."
                )
                return False
        elif isinstance(booking, WaitingListBooking):
            if activity.id == booking.groupActivity.id:
                logger.warning(
                    f"{booking.customer.id} is already on the waiting list "
                    f"({booking.waitingListPosition}) for activity {activity.name} at "
                    f"{activity.businessUnit.name} {activity.duration.start.astimezone(TZ).isoformat()}."
                )
                return False
    return True


def book(activity: GroupActivity, authorization: Authorization) -> Booking | NotBookedReason:
    try:
        booking = api.book_group_activity(activity, authorization)
    except TooEarlyToBook:
        logger.debug(
            f"It's too early to book activity {activity.name} at {activity.businessUnit.name} "
            f"{activity.duration.start.astimezone(TZ).isoformat()}."
        )
        return "too_early"
    except BookingClashesWithOtherBooking:
        logger.error(
            f"Activity {activity.name} at {activity.businessUnit.name} "
            f"{activity.duration.start.astimezone(TZ).isoformat()} clashes "
            f"with other booking for {authorization.username}."
        )
        return "clashing_booking"
    else:
        if isinstance(booking, GroupActivityBooking):
            logger.info(
                f"Booked {authorization.username} for activity {activity.name} at {activity.businessUnit.name} "
                f"{activity.duration.start.astimezone(TZ).isoformat()}."
            )
        elif isinstance(booking, WaitingListBooking):
            logger.info(
                f"Put {authorization.username} on the waiting list ({booking.waitingListPosition}) for activity "
                f"{activity.name} at {activity.businessUnit.name} {activity.duration.start.astimezone(TZ).isoformat()}."
            )
        return booking


def is_time_to_book(activity: GroupActivity) -> bool:
    now = datetime.now(TZ)
    is_bookable_soon = activity.bookableEarliest - timedelta(seconds=3) <= now
    is_bookable_since_1_day = activity.bookableEarliest + timedelta(days=1) < now
    return is_bookable_soon and not is_bookable_since_1_day


def wait_for_upcoming_activities(authorization: Authorization, activities: dict[int, GroupActivity]) -> None:
    if not activities:
        sleep(60)
        return
    for activity in list(activities.values()):
        if not is_time_to_book(activity):
            continue
        if not is_bookable(activity, authorization):
            del activities[activity.id]
            continue
        while book(activity, authorization) == "too_early":
            sleep(0.02)
    sleep(1)
