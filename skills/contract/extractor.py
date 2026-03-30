"""PDF text extraction using PyMuPDF."""

try:
    import fitz  # PyMuPDF
    _HAS_FITZ = True
except ImportError:
    _HAS_FITZ = False


def extract_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes.

    Raises:
        RuntimeError: If PyMuPDF is not installed.
        ValueError: If the PDF is corrupt or contains no extractable text.
    """
    if not _HAS_FITZ:
        raise RuntimeError("PDF analysis not available — install pymupdf")

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Could not extract text from PDF: {exc}") from exc

    text_parts = []
    for page in doc:
        text_parts.append(page.get_text())
    text = "\n".join(text_parts).strip()

    if not text:
        raise ValueError("No text found — this may be a scanned document")

    return text
