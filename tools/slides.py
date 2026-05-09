"""
Slide parser: extracts text from a PDF, one labelled block per page.

Each block is prefixed with [Slide N] so the LLM can reference specific slides.
Raises ValueError with a human-readable message on failure so the bot can
forward it to the user instead of crashing.
"""

import fitz  # PyMuPDF


def parse_slides(file_path: str) -> str:
    """
    Extract text from every page of a PDF.

    Returns a single string with [Slide N] headers.
    Raises ValueError if the file cannot be read or contains no extractable text.
    """
    try:
        doc = fitz.open(file_path)
    except Exception as exc:
        raise ValueError(f"Cannot open PDF: {exc}") from exc

    pages: list[str] = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        if text:
            pages.append(f"[Slide {i}]\n{text}")

    doc.close()

    if not pages:
        raise ValueError(
            "No extractable text found. The PDF may be scanned/image-based. "
            "Please use a PDF with selectable text."
        )

    return "\n\n".join(pages)
