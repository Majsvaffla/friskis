from datetime import date, datetime, time, timedelta

import httpx

from friskis.api.constants import BUSINESS_UNITS_URL, ENDPOINT, LOGIN_URL
from friskis.api.exceptions import (
    APIException,
    BookingClashesWithOtherBooking,
    TooEarlyToBook,
)
from friskis.api.models import (
    Authorization,
    Booking,
    BusinessUnit,
    Customer,
    GroupActivity,
)
from friskis.api.utils import authorized_request, deserialize_booking
from friskis.constants import TZ
from friskis.exceptions import FriskisException


def log_in(*, email: str, password: str) -> Authorization:
    response = httpx.post(LOGIN_URL, json={"username": email, "password": password})
    if response.status_code == 200:
        return Authorization(**response.json())
    raise APIException(
        message=(
            "Unable to log in because of invalid credentials." if response.status_code == 401 else "Unable to log in."
        ),
        status_code=response.status_code,
    )


def get_customer(authorization: Authorization) -> Customer:
    url = f"{ENDPOINT}/customers/{authorization.username}"
    response = authorized_request("GET", url, authorization=authorization)
    if response.status_code != 200:
        raise APIException(
            f"Unable to fetch customer {authorization.username}.",
            status_code=response.status_code,
        )
    return Customer(**response.json())


def get_bookings(authorization: Authorization) -> list[Booking]:
    url = f"{ENDPOINT}/customers/{authorization.username}/bookings/groupactivities"
    response = authorized_request("GET", url, authorization=authorization)
    if response.status_code != 200:
        raise APIException(
            f"Unable to fetch bookings for {authorization.username}.",
            status_code=response.status_code,
        )
    return [deserialize_booking(booking) for booking in response.json()]


def _get_business_units() -> list[BusinessUnit]:
    response = httpx.get(BUSINESS_UNITS_URL)
    if response.status_code != 200:
        raise APIException(
            "Unable to fetch business units.",
            status_code=response.status_code,
        )
    return [BusinessUnit(**data) for data in response.json()]


def get_business_unit(name: str) -> BusinessUnit:
    business_units = _get_business_units()
    for business_unit in business_units:
        if business_unit.name.lower() == name.lower():
            return business_unit
    raise FriskisException(f"Unable to find business unit {name}.")


def _get_group_activities(location: BusinessUnit, day: date) -> list[GroupActivity]:
    url = f"{BUSINESS_UNITS_URL}/{location.id}/groupactivities"
    period_start = datetime.combine(day, time())
    period_end = period_start + timedelta(days=1)

    def datetime_to_string(dt: datetime) -> str:
        aware = dt.astimezone(TZ)
        date_string = aware.date().isoformat()
        time_string = aware.strftime("%H:%M:%S")
        return f"{date_string}T{time_string}.000Z"

    params = {
        "period.start": datetime_to_string(period_start),
        "period.end": datetime_to_string(period_end),
    }
    response = httpx.get(url, params=params)
    if response.status_code != 200:
        raise APIException(
            f"Unable to fetch group activities at {location.name}.",
            status_code=response.status_code,
        )
    return [GroupActivity(**data) for data in response.json()]


def get_group_activity(name: str, day: date, location: BusinessUnit, moment: time) -> GroupActivity | None:
    activities = _get_group_activities(location, day)
    for activity in activities:
        has_matching_name = activity.name.lower().strip() == name.lower()
        has_matching_time = activity.duration.start.astimezone(TZ).time() == moment
        if has_matching_name and has_matching_time:
            return activity
    return None


def book_group_activity(activity: GroupActivity, authorization: Authorization) -> Booking:
    url = f"{ENDPOINT}/customers/{authorization.username}/bookings/groupactivities"
    params = {
        "groupActivity": activity.id,
        "allowWaitingList": True,
    }
    response = authorized_request("POST", url, json=params, authorization=authorization)
    if response.status_code == 403 and (error := response.json()):
        if error["errorCode"] == "TOO_EARLY_TOO_BOOK":
            bookable_earliest = datetime.fromisoformat(error["earliestTimepoint"])
            raise TooEarlyToBook(
                f"Activity {activity.name} can't be booked until {bookable_earliest}.",
                status_code=response.status_code,
            )
        elif error["errorCode"] == "BOOKING_CLASHES_WITH_OTHER_BOOKING":
            raise BookingClashesWithOtherBooking(
                f"Activity {activity.name} clashes with other booking.",
                status_code=response.status_code,
            )
    if response.status_code != 201:
        raise APIException(
            f"Unable to book activity {activity.name} at {activity.businessUnit.name} "
            f"{activity.duration.start.astimezone(TZ).isoformat()}.",
            status_code=response.status_code,
        )
    return deserialize_booking(response.json())
