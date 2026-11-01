from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

STATUS_NAMES = {
    400: "INVALID_ARGUMENT",
    401: "UNAUTHENTICATED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
}


class ApiError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle(_: Request, error: ApiError) -> JSONResponse:
        body = {"code": error.code, "message": error.message, "status": STATUS_NAMES[error.code]}
        return JSONResponse({"error": body}, status_code=error.code)
