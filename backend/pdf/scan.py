""""Scanned" output: make rendered pages look like a real handwritten sheet
that went through a document scanner / phone scan app.

Pipeline per page (all seeded → deterministic):
  rasterise vector page → soften ink edges (pen on paper) → desaturate a little
  → warm paper tone → paper fibre texture + sensor grain → uneven lighting
  (vignette + light falloff across the sheet) → slight page tilt and shift on
  the scanner bed → gentle tone curve → a few dust specks → JPEG compression.

The visible page is an image, like a real scan. An invisible text layer (the
same glyph positions, no rotation) is laid on top, so the PDF stays searchable
and the quality audit can still read every word back.
"""

from __future__ import annotations

import hashlib

import cv2
import numpy as np
import pymupdf as fitz  # PyMuPDF

FINAL_DPI = 200
PREVIEW_DPI = 130


def _seed(*parts: object) -> int:
    return int.from_bytes(hashlib.sha256("\x1f".join(map(str, parts)).encode()).digest()[:8], "big")


def scan_effect(rgb: np.ndarray, seed: int, dpi: int) -> np.ndarray:
    """Apply scanner-like degradation to an RGB uint8 page image."""
    rng = np.random.default_rng(seed)
    h, w = rgb.shape[:2]
    k = dpi / 150.0
    img = rgb.astype(np.float32) / 255.0

    # 1. Ink sits in the paper: soft edges, very slight spread.
    img = cv2.GaussianBlur(img, (0, 0), sigmaX=0.55 * k)

    # 2. Scanners slightly desaturate colours.
    gray = img.mean(axis=2, keepdims=True)
    img = img * 0.88 + gray * 0.12

    # 3. Paper tone (warm off-white, varies per sheet).
    tint = np.array([0.985, 0.972, 0.938], np.float32) + rng.normal(0, 0.006, 3).astype(np.float32)
    img *= tint

    # 4. Paper fibre (fine, faint) + sensor grain (high frequency).
    fib = rng.normal(0, 1, (h // int(3 * k) + 2, w // int(3 * k) + 2)).astype(np.float32)
    fib = cv2.GaussianBlur(cv2.resize(fib, (w, h), interpolation=cv2.INTER_LINEAR), (0, 0), 1.2 * k)
    img *= 1.0 + 0.012 * fib[..., None]
    img += rng.normal(0, 0.008, (h, w, 1)).astype(np.float32)

    # 5. Uneven lighting: vignette + light falling off across the sheet.
    xx = (np.arange(w, dtype=np.float32) / w)[None, :]
    yy = (np.arange(h, dtype=np.float32) / h)[:, None]
    cx, cy = rng.uniform(0.4, 0.6), rng.uniform(0.35, 0.55)
    angle = rng.uniform(0, 2 * np.pi)
    light = 1.0 - 0.09 * ((xx - cx) ** 2 + (yy - cy) ** 2) - 0.03 * ((xx - 0.5) * np.cos(angle) + (yy - 0.5) * np.sin(angle))
    img *= light[..., None]

    # 6. Page slightly tilted and shifted on the scanner bed.
    tilt = rng.normal(0, 0.35)
    tilt = float(np.clip(tilt, -0.8, 0.8))
    m = cv2.getRotationMatrix2D((w / 2, h / 2), tilt, 1.0)
    m[:, 2] += rng.normal(0, 3 * k, 2)
    bed = tuple(float(v) for v in (np.array([0.80, 0.80, 0.79]) + rng.normal(0, 0.01, 3)))
    img = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=bed)

    # 7. Scanner tone curve (slightly more contrast in the darks).
    img = np.clip(img, 0.0, 1.0) ** 1.06

    # 8. A few dust specks.
    for _ in range(int(rng.integers(3, 12))):
        x, y = int(rng.uniform(0, w)), int(rng.uniform(0, h))
        r = max(1, int(rng.uniform(0.6, 1.8) * k))
        v = float(rng.uniform(0.35, 0.75))
        cv2.circle(img, (x, y), r, (v, v, v), -1, lineType=cv2.LINE_AA)

    return (np.clip(img, 0.0, 1.0) * 255).astype(np.uint8)


def scanned_pdf(visible_pdf: bytes, text_layer_pdf: bytes, seed_key: str, dpi: int = FINAL_DPI, jpeg_quality: int = 84) -> bytes:
    """Build the scanned-look PDF: one JPEG per page + invisible text layer."""
    out = fitz.open()
    with fitz.open(stream=visible_pdf, filetype="pdf") as src, fitz.open(stream=text_layer_pdf, filetype="pdf") as layer:
        for i, page in enumerate(src):
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[..., :3]
            scanned = scan_effect(rgb, _seed(seed_key, i), dpi)
            ok, jpg = cv2.imencode(".jpg", cv2.cvtColor(scanned, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
            if not ok:  # pragma: no cover
                raise RuntimeError("JPEG encoding failed")
            new = out.new_page(width=page.rect.width, height=page.rect.height)
            new.insert_image(new.rect, stream=jpg.tobytes())
            new.show_pdf_page(new.rect, layer, i)
        meta = dict(src.metadata)
    out.set_metadata({k: v for k, v in meta.items() if k in ("title", "author", "subject", "keywords", "creator", "producer")})
    data = out.tobytes(garbage=3, deflate=True)
    out.close()
    return data
