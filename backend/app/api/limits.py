"""Size limits for request inputs that had none (Phase 9).

Real use never comes near them; they stop malformed or abusive requests before any
work is done. Pydantic checks them while reading the request body, so a request
over a limit gets a 422 before any search or LLM call.
"""

from typing import Annotated

from pydantic import Field, StringConstraints

MAX_DOCUMENT_IDS = 200
MAX_ID_LENGTH = 64  # real ids are 32 characters (uuid4 hex)
MAX_FILENAME_LENGTH = 255  # the usual limit for one file name on disk

# A document or conversation id.
Id = Annotated[str, StringConstraints(max_length=MAX_ID_LENGTH)]
# The documents a request is limited to.
DocumentIds = Annotated[list[Id], Field(max_length=MAX_DOCUMENT_IDS)]


def shorten_filename(name: str) -> str:
    """Cut a too-long file name to MAX_FILENAME_LENGTH, keeping its extension.

    A long name isn't the user's fault, so it is shortened rather than refused.
    """
    if len(name) <= MAX_FILENAME_LENGTH:
        return name
    stem, dot, extension = name.rpartition(".")
    if not dot:  # no extension: just cut
        return name[:MAX_FILENAME_LENGTH]
    suffix = "." + extension
    return stem[: MAX_FILENAME_LENGTH - len(suffix)] + suffix
