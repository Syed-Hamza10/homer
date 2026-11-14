from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

STATUS_NAMES = {
    400: "INVALID_ARGUMENT",
    401: "UNAUTHENTICATED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
}
COLD_CACHE = "FAILED_PRECONDITION: Request failed due to cold cache data. Please retry in 5 seconds"


class ApiError(Exception):
    def __init__(self, code: int, message: str, status: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status or STATUS_NAMES[code]


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle(_: Request, error: ApiError) -> JSONResponse:
        body = {"code": error.code, "message": error.message, "status": error.status}
        return JSONResponse({"error": body}, status_code=error.code)
