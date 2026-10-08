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


def make_password_pdf(path, text="Secret notes about mitosis."):
    """A one-page PDF that can't be opened without its password."""
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    doc.save(str(path), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="owner")
    doc.close()
