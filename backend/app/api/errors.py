import logging
import math

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.llm.errors import LLMError, MissingAPIKeyError, RateLimitError

logger = logging.getLogger(__name__)

# Stable codes next to "detail", so the UI can act on an error without parsing its text.
DOCUMENT_NOT_FOUND = "document_not_found"
CONVERSATION_NOT_FOUND = "conversation_not_found"
INTERNAL_ERROR = "internal_error"

INTERNAL_ERROR_MESSAGE = "Something went wrong on the server. Please try again."


class NotFoundError(Exception):
    """A 404 with a friendly message and a code. The message never echoes ids from the
    request: those go to the log, where they help debugging without confusing users."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.message = message
        self.code = code


def documents_not_found(missing: list[str]) -> NotFoundError:
    logger.info("Selected documents not found: %s", missing)
    return NotFoundError("One or more of the selected documents no longer exist.", DOCUMENT_NOT_FOUND)


def conversation_not_found() -> NotFoundError:
    return NotFoundError("This conversation no longer exists.", CONVERSATION_NOT_FOUND)


async def _not_found_handler(_: Request, error: NotFoundError) -> JSONResponse:
    return JSONResponse(
        {"detail": error.message, "code": error.code}, status_code=status.HTTP_404_NOT_FOUND
    )


async def _unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
    """Any exception nothing else handled: a friendly JSON 500 instead of plain text.

    The response says nothing about the cause. The log gets the method, path and
    error type (Starlette then re-raises, so the server also logs the traceback);
    never the request body, which may hold a question or a document.
    """
    logger.error("Unexpected %s on %s %s", type(error).__name__, request.method, request.url.path)
    return JSONResponse(
        {"detail": INTERNAL_ERROR_MESSAGE, "code": INTERNAL_ERROR},
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _status_for(error: LLMError) -> int:
    if isinstance(error, RateLimitError):
        # The daily quota won't come back for hours, so it isn't "temporarily unavailable":
        # 429 tells the UI not to offer a retry. A per-minute limit stays 503 + Retry-After.
        if error.daily_quota:
            return status.HTTP_429_TOO_MANY_REQUESTS
        return status.HTTP_503_SERVICE_UNAVAILABLE
    if isinstance(error, MissingAPIKeyError):
        return status.HTTP_500_INTERNAL_SERVER_ERROR
    # ProviderError and anything else from the LLM: the upstream service failed.
    return status.HTTP_502_BAD_GATEWAY


async def _llm_error_handler(_: Request, error: LLMError) -> JSONResponse:
    """Turn an LLM failure into a friendly message, same shape as HTTPException."""
    code = _status_for(error)
    # The technical detail goes to the log; the user only sees the friendly message.
    logger.warning("LLM error -> %d: %s", code, error)
    headers = {}
    if isinstance(error, RateLimitError) and error.retry_after and not error.daily_quota:
        headers["Retry-After"] = str(math.ceil(error.retry_after))
    return JSONResponse({"detail": error.user_message}, status_code=code, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(LLMError, _llm_error_handler)
    app.add_exception_handler(NotFoundError, _not_found_handler)
    app.add_exception_handler(Exception, _unexpected_error_handler)
