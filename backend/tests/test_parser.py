import pymupdf

from app.rag.parser import extract_pages


def make_pdf(path, page_texts):
    """Build a small PDF in a temp folder; an empty string makes a blank page."""
    doc = pymupdf.open()
    for text in page_texts:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


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