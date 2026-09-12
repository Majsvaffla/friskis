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


def request(method: Literal["GET", "POST"], url: str, **kwargs: Any) -> httpx.Response:
    try:
        response = httpx.request(method, url, **kwargs)
    except httpx.TransportError as transport_error:
        raise TemporarilyUnavailable("Temporarily unavailable due to a network error.") from transport_error
    if response.status_code >= 500:
        raise TemporarilyUnavailable(f"Temporarily unavailable due to response status code {response.status_code}.")
    return response


@overload
def authorized_request(method: Literal["GET"], url: str, authorization: Authorization) -> httpx.Response: ...


@overload
def authorized_request(
    method: Literal["POST"], url: str, authorization: Authorization, *, json: dict[str, Any]
) -> httpx.Response: ...


def authorized_request(
    method: Literal["GET", "POST"], url: str, authorization: Authorization, *, json: dict[str, Any] | None = None
) -> httpx.Response:
    return request(method, url, json=json, headers={
        "authorization": f"{authorization.token_type} {authorization.access_token}",
    })



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
