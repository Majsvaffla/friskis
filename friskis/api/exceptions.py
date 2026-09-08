from friskis.exceptions import FriskisException


class APIException(FriskisException):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        assert len(message) > 0
        if status_code is not None:
            super().__init__(message, status_code)
        else:
            super().__init__(message)


class TooEarlyToBook(APIException): ...


class BookingClashesWithOtherBooking(APIException): ...


class AlreadyBooked(APIException): ...
