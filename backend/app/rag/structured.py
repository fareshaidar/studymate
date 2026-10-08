"""Asking the LLM for JSON and checking it with Pydantic before anything else uses it."""

import logging
import re
from typing import Annotated, Any, TypeVar

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    ValidationError,
    ValidationInfo,
    field_validator,
)

from app.llm.base import LLMClient
from app.llm.errors import InvalidLLMOutputError

logger = logging.getLogger(__name__)

# ```json ... ``` (or plain ```) around the whole reply, which models often add.
_CODE_FENCE = re.compile(r"^```[a-zA-Z]*\s*\n?(.*?)\n?\s*```$", re.DOTALL)

# A non-empty string, with surrounding whitespace removed.
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def strip_code_fences(reply: str) -> str:
    """The reply without a Markdown code fence around it, if there is one."""
    reply = reply.strip()
    match = _CODE_FENCE.match(reply)
    return match.group(1).strip() if match else reply


class _FromPassage(BaseModel):
    """An item that says which numbered passage it came from.

    The allowed range comes from the validation context (`n_passages`), because
    it depends on how many passages we sent, not on the schema.
    """

    passage: int

    @field_validator("passage")
    @classmethod
    def passage_was_sent(cls, value: int, info: ValidationInfo) -> int:
        n_passages = (info.context or {}).get("n_passages")
        if n_passages is not None and not 1 <= value <= n_passages:
            raise ValueError(f"must be a passage number from 1 to {n_passages}")
        return value


class QuizItemLLM(_FromPassage):
    question: Text
    options: list[Text] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: Text

    @field_validator("options")
    @classmethod
    def options_are_distinct(cls, options: list[str]) -> list[str]:
        # "Paris" and " paris" are the same option to a student.
        if len({o.casefold() for o in options}) != len(options):
            raise ValueError("the 4 options must all be different")
        return options


class QuizLLM(BaseModel):
    questions: list[QuizItemLLM] = Field(min_length=1)


class FlashcardLLM(_FromPassage):
    front: Text
    back: Text


class FlashcardsLLM(BaseModel):
    cards: list[FlashcardLLM] = Field(min_length=1)


M = TypeVar("M", bound=BaseModel)


def generate_json(
    llm: LLMClient,
    prompt: str,
    *,
    system: str,
    schema: type[M],
    context: dict[str, Any] | None = None,
) -> M:
    """Ask for JSON matching `schema`; retry once with the errors; then give up.

    One retry is usually enough: the model sees exactly what was wrong. More
    retries would cost free-tier quota for little gain. Raises InvalidLLMOutputError
    (shown to the student as a friendly 502) if the second reply is also invalid.
    """
    attempt_prompt = prompt
    for attempt in (1, 2):
        reply = llm.generate(attempt_prompt, system=system)
        try:
            return schema.model_validate_json(strip_code_fences(reply), context=context)
        except ValidationError as exc:
            # Counts only: the reply is generated content and is never logged.
            logger.warning("study invalid_json attempt=%d errors=%d", attempt, exc.error_count())
            if attempt == 2:
                raise InvalidLLMOutputError(
                    f"LLM reply failed validation twice ({exc.error_count()} errors)"
                ) from exc
            attempt_prompt = f"{prompt}\n\n{_retry_note(exc)}"
    raise AssertionError("unreachable")  # the loop always returns or raises


def _retry_note(exc: ValidationError) -> str:
    """What was wrong with the last reply, in a form the model can act on."""
    problems = "\n".join(
        f"- {'.'.join(str(part) for part in error['loc']) or 'reply'}: {error['msg']}"
        for error in exc.errors(include_url=False, include_input=False)
    )
    return (
        "Your previous reply could not be used because:\n"
        f"{problems}\n"
        "Reply again with JSON only, exactly in the format described above."
    )
