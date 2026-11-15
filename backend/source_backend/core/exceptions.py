
class FireAtlasException(Exception):
    """Base exception for FIRE ATLAS application errors."""

    def __init__(
        self,
        message: str,
        code: str,
        status_code: int,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class BadRequestException(FireAtlasException):
    def __init__(
        self,
        message: str,
        code: str = "BAD_REQUEST",
    ):
        super().__init__(message, code, 400)


class DataUnavailableException(FireAtlasException):
    def __init__(
        self,
        message: str = "Requested data is currently unavailable.",
        code: str = "DATA_UNAVAILABLE",
    ):
        super().__init__(message, code, 503)
