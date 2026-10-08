import re

# Box-drawing and block characters (─│┌┐└┘┬ ...) and arrows (→ ↓ ...), as used in text diagrams.
_DIAGRAM_CHARS = re.compile(r"[─-▟←-⇿]+")
_SPACES = re.compile(r"[ \t]{2,}")
# A dot leader: 4 or more dots in a row, optionally spaced (OCR often reads "....." as ". . . .").
_DOT_LEADER = re.compile(r"\.(?:[ \t]*\.){3,}")

# Front-matter rule (see is_front_matter), set on the Skylab report: its 20 contents/list
# chunks have at least 5 leaders and at least one per 14.2 words; the densest other chunk
# (an OCR diagram) has one per 21.1 words. 18 sits about halfway between the two.
MIN_DOT_LEADERS = 5
MAX_WORDS_PER_DOT_LEADER = 18


def alnum_ratio(text: str) -> float:
    """Share of non-whitespace characters that are letters or digits (0.0 to 1.0).

    Prose, numeric tables and code score high; text diagrams made of
    box-drawing characters score low. Empty text scores 0.
    """
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    return sum(c.isalnum() for c in chars) / len(chars)


def count_dot_leaders(text: str) -> int:
    """How many dot leaders ("Title ........ 42") the text contains. "..." is not one."""
    return len(_DOT_LEADER.findall(text))


def count_words(text: str) -> int:
    """Words that contain a letter or digit, so runs of OCR dots don't count as words."""
    return sum(any(c.isalnum() for c in token) for token in text.split())


def is_front_matter(text: str) -> bool:
    """True for table-of-contents and list-of-figures/tables passages.

    The rule: at least 5 dot leaders, and at least one leader per 18 words.
    Those pages are made of "Title ........ page" lines, so leaders are dense;
    body text almost never has them, and a page with a few stray dots (a diagram,
    an ellipsis) is far below one per 20 words. Such passages match many questions
    by their headings but never contain an answer.
    """
    leaders = count_dot_leaders(text)
    return leaders >= MIN_DOT_LEADERS and leaders * MAX_WORDS_PER_DOT_LEADER >= count_words(text)


def strip_diagram_chars(text: str) -> str:
    """Remove box-drawing and arrow characters, keeping the words between them."""
    return _SPACES.sub(" ", _DIAGRAM_CHARS.sub(" ", text)).strip()


def shorten(text: str, max_chars: int) -> str:
    """The start of `text`, cut at a word boundary with "…" added if it was too long."""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return cut + "…"
