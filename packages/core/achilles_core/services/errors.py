from typing import ClassVar


class DomainError(Exception):
    status_code: ClassVar[int] = 400


class NotFound(DomainError):
    status_code = 404
