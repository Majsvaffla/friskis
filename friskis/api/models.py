from __future__ import annotations

import datetime  # noqa: TC003
from typing import TYPE_CHECKING

from pydantic import BaseModel

from friskis import env

if TYPE_CHECKING:
    from pathlib import Path


class Authorization(BaseModel):
    token_type: str
    access_token: str
    username: str


class GroupActivityProduct(BaseModel):
    id: int
    name: str


class BusinessUnit(BaseModel):
    id: int
    name: str
    location: str
    companyNameForInvoice: str

    def __str__(self) -> str:
        return self.name


class Customer(BaseModel):
    id: int
    firstName: str
    lastName: str

    @classmethod
    def from_profile_identifier(cls, profile_identifier: str) -> Customer:
        id, first_name, last_name = profile_identifier.split("_")
        return cls(
            id=int(id),
            firstName=first_name.replace("-", " ").capitalize(),
            lastName=last_name.replace("-", " ").capitalize(),
        )

    @property
    def profile_location(self) -> Path:
        return env.PROFILES_LOCATION / "_".join(
            [str(self.id), self.firstName.replace(" ", "-").lower(), self.lastName.replace(" ", "-").lower()]
        )


class Duration(BaseModel):
    start: datetime.datetime
    end: datetime.datetime


class Order(BaseModel):
    id: int
    number: int


class Booking(BaseModel):
    id: int
    groupActivity: GroupActivityProduct
    businessUnit: BusinessUnit
    customer: Customer
    duration: Duration
    checkedIn: None


class GroupActivityBooking(Booking):
    order: Order
    additionToEventBooking: None


class WaitingListBooking(Booking):
    waitingListPosition: int


class Location(BaseModel):
    id: int
    name: str


class Slots(BaseModel):
    total: int
    totalBookable: int
    reservedForDropin: int
    leftToBook: int
    leftToBookIncDropin: int
    hasWaitingList: bool
    inWaitingList: int | None = None


class Instructor(BaseModel):
    id: int
    name: str
    isSubstitute: bool


class GroupActivity(BaseModel):
    id: int
    name: str
    duration: Duration
    groupActivityProduct: GroupActivityProduct
    businessUnit: BusinessUnit
    locations: list[Location]
    instructors: list[Instructor]
    bookableEarliest: datetime.datetime
    bookableLatest: datetime.datetime
    bookableEarliestExtended: bool | None
    bookableLatestExtended: bool | None
    externalMessage: str | None
    internalMessage: str | None
    cancelled: bool
    slots: Slots
