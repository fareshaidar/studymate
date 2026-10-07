import re
from dataclasses import dataclass

from app.rag.parser import Page


@dataclass
class Chunk:
    """A piece of text from one page, ready to be embedded."""

    text: str
    page: int
    index: int  # position of this chunk within the document


def clean_text(text: str) -> str:
    """Turn raw PDF text (hard line breaks everywhere) into flowing text."""
    text = text.replace("\r", "")
    # Rejoin words hyphenated across a line break: "algo-\nrithm" -> "algorithm"
    text = re.sub(r"-\n(?=[a-z])", "", text)
    # Keep blank lines as paragraph breaks, turn single newlines into spaces
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    """Fallback for a 'sentence' longer than max_chars: split on word boundaries."""
    pieces: list[str] = []
    current = ""
    for word in sentence.split():
        if current and len(current) + 1 + len(word) > max_chars:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_page_text(
    text: str, max_chars: int = 1800, overlap_chars: int = 250
) -> list[str]:
    """Split one page's text into overlapping, sentence-aligned chunks."""
    cleaned = clean_text(text)

    sentences: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", cleaned):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > max_chars:
            sentences.extend(_split_long_sentence(sentence, max_chars))
        else:
            sentences.append(sentence)

    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for sentence in sentences:
        if current and length + len(sentence) + 1 > max_chars:
            chunks.append(" ".join(current))
            # Start the next chunk with the last few sentences (the overlap).
            overlap: list[str] = []
            overlap_len = 0
            for previous in reversed(current):
                if overlap_len + len(previous) > overlap_chars:
                    break
                overlap.insert(0, previous)
                overlap_len += len(previous) + 1
            current = overlap
            length = overlap_len
            if length + len(sentence) + 1 > max_chars:
                current, length = [], 0  # no room for the overlap, start clean
        current.append(sentence)
        length += len(sentence) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_pages(
    pages: list[Page],
    max_chars: int = 1800,
    overlap_chars: int = 250,
    min_chars: int = 50,
) -> list[Chunk]:
    """Chunk every page. Chunks never cross a page boundary."""
    chunks: list[Chunk] = []
    for page in pages:
        for text in chunk_page_text(page.text, max_chars, overlap_chars):
            if len(text) < min_chars:
                continue  # skip tiny fragments like page numbers
            chunks.append(Chunk(text=text, page=page.number, index=len(chunks)))
    return chunks