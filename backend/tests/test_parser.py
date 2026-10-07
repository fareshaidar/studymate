from app.rag.parser import count_pages, extract_pages
from tests.helpers import make_pdf


def test_extracts_text_with_real_page_numbers(tmp_path):
    pdf = tmp_path / "doc.pdf"
    make_pdf(pdf, ["Hello first page", "Second page text"])

    pages = extract_pages(pdf)

    assert [p.number for p in pages] == [1, 2]
    assert "Hello first page" in pages[0].text


def test_blank_page_is_skipped_but_numbers_stay_correct(tmp_path):
    pdf = tmp_path / "doc.pdf"
    make_pdf(pdf, ["First page", "", "Third page"])

    pages = extract_pages(pdf)

    assert [p.number for p in pages] == [1, 3]


def test_count_pages_includes_blank_pages(tmp_path):
    pdf = tmp_path / "doc.pdf"
    make_pdf(pdf, ["First page", "", "Third page"])

    assert count_pages(pdf) == 3
