import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# A citation like [3], or a group like [1, 4].
_CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
# Spaces left before punctuation once a citation is removed: "mutation [9]." -> "mutation ."
_SPACE_BEFORE_PUNCT = re.compile(r"[ \t]+([.,;:!?)])")
_DOUBLE_SPACES = re.compile(r"[ \t]{2,}")


@dataclass
class CitationResult:
    text: str  # the answer with invalid citations removed
    cited: set[int] = field(default_factory=set)  # valid source numbers used
    removed: list[int] = field(default_factory=list)  # invalid numbers that were stripped


def check_citations(answer: str, n_sources: int) -> CitationResult:
    """Keep citations that point at a real source (1..n_sources), remove the rest.

    Groups are split into separate citations: "[1, 4]" -> "[1][4]".
    """
    result = CitationResult(text=answer)

    def replace(match: re.Match) -> str:
        numbers = [int(n) for n in match.group(1).split(",")]
        valid = [n for n in numbers if 1 <= n <= n_sources]
        result.cited.update(valid)
        result.removed.extend(n for n in numbers if n not in valid)
        return "".join(f"[{n}]" for n in valid)

    text = _CITATION.sub(replace, answer)
    if result.removed:
        text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
        text = _DOUBLE_SPACES.sub(" ", text).strip()
        logger.warning("Removed invalid citations %s (only %d sources)", result.removed, n_sources)
    result.text = text
    return result
