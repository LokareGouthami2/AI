import io
import zipfile

import pytest

from backend.config import get_settings
from backend.documents import ocr
from backend.documents.extract import extract
from backend.documents.validation import UploadRejected, sanitize_filename, validate_upload


def test_pdf_extraction_keeps_typography(pdf_bytes):
    doc = extract("pdf", pdf_bytes)
    assert doc.page_count >= 1
    title = doc.lines[0]
    assert title.text == "Introduction to Machine Learning"
    assert title.is_bold and title.font_size > 20
    body = next(ln for ln in doc.lines if ln.text.startswith("Machine learning is"))
    assert not body.is_bold and 10 < body.font_size < 12


@pytest.mark.skipif(not ocr.tesseract_available(), reason="tesseract not installed")
def test_scanned_pdf_goes_through_ocr(scanned_pdf_bytes):
    doc = extract("pdf", scanned_pdf_bytes)
    assert doc.pages[0].source == "ocr"
    assert doc.pages[0].ocr_confidence > 70
    text = " ".join(ln.text for ln in doc.lines)
    assert "Machine Learning" in text and "training set" in text


def test_docx_and_txt(docx_bytes, txt_bytes):
    d = extract("docx", docx_bytes)
    assert d.lines[0].style == "Title"
    assert any(ln.style == "Heading 1" for ln in d.lines)
    t = extract("txt", txt_bytes)
    assert any("training set" in ln.text for ln in t.lines)


def test_deskew_corrects_rotation():
    import cv2
    import numpy as np

    img = np.full((400, 600), 255, np.uint8)
    for y in range(60, 360, 30):
        cv2.putText(img, "Skewed text line for OCR", (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 0, 2)
    m = cv2.getRotationMatrix2D((300, 200), 5, 1.0)
    rotated = cv2.warpAffine(img, m, (600, 400), borderValue=255)
    assert abs(ocr.estimate_skew(rotated)) > 2
    assert abs(ocr.estimate_skew(ocr.deskew(rotated))) < 1.5


# ---------------------------------------------------------------- validation


def test_validation_accepts_supported(pdf_bytes, docx_bytes, txt_bytes):
    s = get_settings()
    assert validate_upload("a.pdf", pdf_bytes, s).kind == "pdf"
    assert validate_upload("a.docx", docx_bytes, s).kind == "docx"
    assert validate_upload("a.txt", txt_bytes, s).kind == "txt"


@pytest.mark.parametrize(
    "name,data,code",
    [
        ("a.exe", b"MZ....", "UNSUPPORTED_TYPE"),
        ("a.pdf", b"not a pdf at all", "BAD_FILE_TYPE"),
        ("a.docx", b"%PDF-1.4 fake", "BAD_FILE_TYPE"),
        ("a.txt", b"\x00\x01\x02binary", "BAD_FILE_TYPE"),
        ("a.pdf", b"", "EMPTY_FILE"),
        ("a.pdf", b"%PDF-1.4 garbage", "CORRUPT_FILE"),
    ],
)
def test_validation_rejects(name, data, code):
    with pytest.raises(UploadRejected) as e:
        validate_upload(name, data, get_settings())
    assert e.value.code == code


def test_zip_that_is_not_docx_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("hello.txt", "hi")
    with pytest.raises(UploadRejected) as e:
        validate_upload("a.docx", buf.getvalue(), get_settings())
    assert e.value.code == "BAD_FILE_TYPE"


def test_docx_zip_bomb_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<x/>")
        z.writestr("word/document.xml", "<x/>")
        z.writestr("word/bomb.xml", "0" * (101 * 1024 * 1024))
    with pytest.raises(UploadRejected) as e:
        validate_upload("a.docx", buf.getvalue(), get_settings())
    assert e.value.code == "ZIP_BOMB"


def test_size_limit(monkeypatch):
    s = get_settings().model_copy(update={"max_upload_mb": 1})
    with pytest.raises(UploadRejected) as e:
        validate_upload("a.txt", b"a" * (1024 * 1024 + 1), s)
    assert e.value.code == "FILE_TOO_LARGE"


def test_filename_sanitised():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("C:\\Users\\x\\notes <1>.pdf") == "notes _1_.pdf"
    assert sanitize_filename("") == "document"
