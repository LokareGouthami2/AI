"""OCR for scanned pages: OpenCV preprocessing + Tesseract.

Preprocessing pipeline (each step is a pure function so it can be unit-tested):
grayscale → deskew → denoise → adaptive threshold.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class OcrLine:
    text: str
    bbox: tuple[float, float, float, float]  # in image pixels
    confidence: float
    height: float


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    if img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)
    return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)


def estimate_skew(gray: np.ndarray) -> float:
    """Skew angle in degrees from the minimum-area rectangle of ink pixels."""
    inv = cv2.bitwise_not(gray)
    _, thresh = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) < 50:
        return 0.0
    angle = cv2.minAreaRect(coords.astype(np.float32))[-1]
    # OpenCV >= 4.5 returns angles in [0, 90); map to a small correction.
    if angle > 45:
        angle -= 90
    return float(-angle) if abs(angle) <= 15 else 0.0


def deskew(gray: np.ndarray) -> np.ndarray:
    angle = estimate_skew(gray)
    if abs(angle) < 0.3:
        return gray
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def binarize(gray: np.ndarray) -> np.ndarray:
    blur = cv2.medianBlur(gray, 3)
    return cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )


def preprocess(img: np.ndarray) -> np.ndarray:
    return binarize(deskew(to_gray(img)))


def ocr_image(img: np.ndarray, lang: str = "eng") -> tuple[list[OcrLine], float]:
    """Run Tesseract; returns lines and mean word confidence (0-100)."""
    import pytesseract

    processed = preprocess(img)
    data = pytesseract.image_to_data(
        processed, lang=lang, config="--psm 3", output_type=pytesseract.Output.DICT
    )
    lines: dict[tuple[int, int, int], list[int]] = {}
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        conf = float(data["conf"][i])
        if conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(i)

    out: list[OcrLine] = []
    confs: list[float] = []
    for key in sorted(lines):
        idx = lines[key]
        words = [data["text"][i] for i in idx]
        c = [float(data["conf"][i]) for i in idx]
        x0 = min(data["left"][i] for i in idx)
        y0 = min(data["top"][i] for i in idx)
        x1 = max(data["left"][i] + data["width"][i] for i in idx)
        y1 = max(data["top"][i] + data["height"][i] for i in idx)
        heights = sorted(data["height"][i] for i in idx)
        out.append(
            OcrLine(
                text=" ".join(words),
                bbox=(x0, y0, x1, y1),
                confidence=sum(c) / len(c),
                height=float(heights[len(heights) // 2]),
            )
        )
        confs.extend(c)
    mean_conf = sum(confs) / len(confs) if confs else 0.0
    return out, mean_conf
