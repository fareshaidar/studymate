import re

# Box-drawing and block characters (─│┌┐└┘┬ ...) and arrows (→ ↓ ...), as used in text diagrams.
_DIAGRAM_CHARS = re.compile(r"[─-▟←-⇿]+")
_SPACES = re.compile(r"[ \t]{2,}")


def alnum_ratio(text: str) -> float:
    """Share of non-whitespace characters that are letters or digits (0.0 to 1.0).

    Prose, numeric tables and code score high; text diagrams made of
    box-drawing characters score low. Empty text scores 0.
    """
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    return sum(c.isalnum() for c in chars) / len(chars)


def strip_diagram_chars(text: str) -> str:
    """Remove box-drawing and arrow characters, keeping the words between them."""
    return _SPACES.sub(" ", _DIAGRAM_CHARS.sub(" ", text)).strip()
