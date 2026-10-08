import logging
import math

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.llm.errors import LLMError, MissingAPIKeyError, RateLimitError

logger = logging.getLogger(__name__)


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
