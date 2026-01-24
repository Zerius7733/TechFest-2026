import io
from typing import List, Tuple

from PIL import Image
import pytesseract

def _is_pdf(filename: str, content_type: str | None) -> bool:
    name = (filename or "").lower()
    ctype = (content_type or "").lower()
    return name.endswith(".pdf") or ctype == "application/pdf"

def _is_image(filename: str, content_type: str | None) -> bool:
    name = (filename or "").lower()
    ctype = (content_type or "").lower()
    if ctype.startswith("image/"):
        return True
    return name.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"))

def _ocr_image(img: Image.Image) -> str:
    # mild normalization helps OCR
    if img.mode != "RGB":
        img = img.convert("RGB")
    return pytesseract.image_to_string(img)

def ocr_bytes(
    *,
    file_bytes: bytes,
    filename: str,
    content_type: str | None,
    max_pages: int = 4,
) -> Tuple[str, List[str]]:
    """
    Returns:
      (full_text, per_page_texts)
    Supports:
      - PDF (first max_pages pages)
      - Image formats
    """
    if _is_pdf(filename, content_type):
        # Lazy import because pdf2image needs poppler installed
        from pdf2image import convert_from_bytes

        images = convert_from_bytes(file_bytes, first_page=1, last_page=max_pages)
        per_page = []
        for img in images:
            per_page.append(_ocr_image(img))
        return ("\n\n".join(per_page).strip(), per_page)

    if _is_image(filename, content_type):
        img = Image.open(io.BytesIO(file_bytes))
        text = _ocr_image(img).strip()
        return (text, [text])

    raise ValueError("Unsupported file type. Upload a PDF or an image (png/jpg/webp).")
