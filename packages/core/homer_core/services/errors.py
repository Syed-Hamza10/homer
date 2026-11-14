from typing import ClassVar


class DomainError(Exception):
    status_code: ClassVar[int] = 400
    headers: ClassVar[dict[str, str]] = {}


class NotFound(DomainError):
    status_code = 404


class GoogleFailed(DomainError):
    status_code = 502
