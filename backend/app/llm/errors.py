class LLMError(Exception):
    """Base class for everything that can go wrong when calling an LLM.

    `str(error)` is a technical detail for logs. `user_message` is safe and
    friendly enough to show to a student. Neither ever contains the API key or prompt.
    """

    user_message = "The AI service had a problem. Please try again."

    def __init__(self, detail: str = "", *, retryable: bool = False, user_message: str | None = None):
        super().__init__(detail or self.user_message)
        self.retryable = retryable
        if user_message:
            self.user_message = user_message


class MissingAPIKeyError(LLMError):
    """No API key is configured, so the LLM can't be called at all."""

    user_message = "The AI service isn't set up yet: no API key is configured."


class RateLimitError(LLMError):
    """The provider said "too many requests" (HTTP 429) and retrying didn't help."""

    user_message = "The AI service is busy right now. Please wait a moment and try again."

    def __init__(self, detail: str = "", *, retry_after: float | None = None, daily_quota: bool = False):
        # Hitting the daily quota won't fix itself in a few seconds, so don't retry it.
        super().__init__(
            detail,
            retryable=not daily_quota,
            user_message=(
                "The daily limit for the AI service has been reached. Please try again tomorrow."
                if daily_quota
                else None
            ),
        )
        self.retry_after = retry_after
        self.daily_quota = daily_quota


class ProviderError(LLMError):
    """Any other provider failure: bad key, unknown model, server error, timeout, blocked answer."""

    def __init__(
        self,
        detail: str = "",
        *,
        status_code: int | None = None,
        retryable: bool = False,
        user_message: str | None = None,
    ):
        super().__init__(detail, retryable=retryable, user_message=user_message)
        self.status_code = status_code
