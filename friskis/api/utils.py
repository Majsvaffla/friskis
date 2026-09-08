from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, TypedDict, assert_never, overload

import httpx

from friskis.api.models import (
    Authorization,
    Booking,
    GroupActivityBooking,
    WaitingListBooking,
)

from .exceptions import TemporarilyUnavailable

if TYPE_CHECKING:

    class RawGroupActivityBooking(TypedDict):
        type: Literal["groupActivityBooking"]
        groupActivityBooking: dict[str, Any]

    class RawWaitingListBooking(TypedDict):
        type: Literal["waitingListBooking"]
        waitingListBooking: dict[str, Any]


@overload
def authorized_request(method: Literal["GET"], url: str, authorization: Authorization) -> httpx.Response: ...


@overload
def authorized_request(
    method: Literal["POST"], url: str, authorization: Authorization, *, json: dict[str, Any]
) -> httpx.Response: ...


def authorized_request(
    method: Literal["GET", "POST"], url: str, authorization: Authorization, *, json: dict[str, Any] | None = None
) -> httpx.Response:
    headers = {
        "authorization": f"{authorization.token_type} {authorization.access_token}",
    }
    try:
        response = httpx.request(method, url, headers=headers, json=json)
    except httpx.TransportError as transport_error:
        raise TemporarilyUnavailable from transport_error
    if response.status_code >= 500:
        raise TemporarilyUnavailable from http_error
    return response



def deserialize_booking(
    data: RawGroupActivityBooking | RawWaitingListBooking,
) -> Booking:
    if data["type"] == "groupActivityBooking":
        return GroupActivityBooking(**{**data, **data["groupActivityBooking"]})
    if data["type"] == "waitingListBooking":
        return WaitingListBooking(**{**data, **data["waitingListBooking"]})
    assert_never(data["type"])


def parse_datetime(s: str) -> datetime:
    return datetime.fromisoformat(s)
