from app.rag.chunker import chunk_page_text, chunk_pages, clean_text
from app.rag.parser import Page


def test_clean_text_joins_hyphenated_words():
    assert clean_text("algo-\nrithm") == "algorithm"


def test_clean_text_joins_hard_line_breaks():
    assert clean_text("line one\nline two") == "line one line two"


def test_clean_text_keeps_paragraph_breaks():
    assert clean_text("para one\n\npara two") == "para one\n\npara two"


def test_chunks_never_exceed_max_chars():
    text = "This is a sentence. " * 200
    chunks = chunk_page_text(text, max_chars=200, overlap_chars=50)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)


def test_very_long_sentence_is_still_split():
    text = "word " * 500  # one giant "sentence" with no punctuation
    chunks = chunk_page_text(text, max_chars=200, overlap_chars=50)
    assert all(len(c) <= 200 for c in chunks)


def test_consecutive_chunks_overlap():
    sentences = [f"Sentence number {i}." for i in range(60)]
    chunks = chunk_page_text(" ".join(sentences), max_chars=200, overlap_chars=60)

    assert len(chunks) > 1
    last_in_first = [s for s in sentences if s in chunks[0]][-1]
    assert last_in_first in chunks[1]


def test_chunks_keep_their_own_page_number():
    long_text = "This sentence is long enough to be kept as a chunk. " * 3
    pages = [Page(number=2, text=long_text), Page(number=5, text=long_text)]

    chunks = chunk_pages(pages)

    assert {c.page for c in chunks} == {2, 5}
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_tiny_fragments_are_dropped():
    assert chunk_pages([Page(number=1, text="42")]) == []