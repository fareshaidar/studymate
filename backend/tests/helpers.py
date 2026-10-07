import pymupdf


def make_pdf(path, page_texts):
    """Build a small PDF in a temp folder; an empty string makes a blank page."""
    doc = pymupdf.open()
    for text in page_texts:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()
