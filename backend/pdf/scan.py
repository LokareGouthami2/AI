""""Scanned" output: make rendered pages look like a real handwritten sheet
that went through a document scanner / phone scan app.

Pipeline per page (all seeded → deterministic):
  rasterise vector page → soften ink edges (pen on paper) → desaturate a little
  → warm paper tone → paper fibre texture + sensor grain → uneven lighting
  (vignette + light falloff across the sheet) → slight page tilt and shift on
  the scanner bed → gentle tone curve → a few dust specks → JPEG compression.

Optional show-through: writing on the back of a thin sheet shows faintly,
mirrored and blurred, as it does on real assignment paper.

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


def ink_mask(rgb: np.ndarray) -> np.ndarray:
    """0..1 amount of ink per pixel (anything darker than the paper)."""
    lum = rgb.astype(np.float32).min(axis=2) / 255.0
    return np.clip((0.97 - lum) / 0.7, 0.0, 1.0)


def back_of_page(masks: list[np.ndarray], i: int) -> np.ndarray:
    """Ink on the reverse of sheet i, as seen through the paper: another page's
    writing (the next one, else the previous one), mirrored left↔right. A
    single page uses its own writing shifted down a little, so the faint
    lines never sit exactly behind the visible ones."""
    if len(masks) > 1:
        src = masks[i + 1] if i + 1 < len(masks) else masks[i - 1]
    else:
        src = np.roll(masks[i], masks[i].shape[0] // 37, axis=0)
    return np.ascontiguousarray(src[:, ::-1])


def _smooth_noise(rng, h: int, w: int, sigma: float, amp: float) -> np.ndarray:
    """Smooth random field with standard deviation ``amp`` and feature size
    ``sigma`` px. Drawn at low resolution and resized, so it is cheap."""
    step = max(1, int(sigma / 2))
    small = rng.standard_normal((h // step + 3, w // step + 3), dtype=np.float32)
    small = cv2.GaussianBlur(small, (0, 0), max(0.5, sigma / step))
    small *= amp / max(1e-6, float(small.std()))
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)


def hand_warp(rgb: np.ndarray, rng, dpi: int) -> np.ndarray:
    """Make every letter its own: a smooth, small displacement field bends
    strokes differently everywhere on the page (no two 'a's identical), and a
    long-wave part makes lines gently wavy like a real hand. Works on the
    uint8 page before the float stages to keep memory low."""
    h, w = rgb.shape[:2]
    k = dpi / 150.0
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    gx += _smooth_noise(rng, h, w, 2.6 * k, 0.75 * k)
    gx += _smooth_noise(rng, h, w, 55 * k, 1.0 * k)
    gy += _smooth_noise(rng, h, w, 2.6 * k, 0.75 * k)
    gy += _smooth_noise(rng, h, w, 55 * k, 1.0 * k)
    m1, m2 = cv2.convertMaps(gx, gy, cv2.CV_16SC2)
    del gx, gy
    return cv2.remap(rgb, m1, m2, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


# Show-through levels: (darkening strength, blur in px at 150 DPI). Medium
# matches a photographed assignment on ordinary 70 gsm paper.
THROUGH_LEVELS = {"light": (1.0, 2.4), "medium": (2.6, 1.5), "strong": (4.0, 1.1)}


def pen_groove_shadow(img: np.ndarray, ink: np.ndarray, k: float) -> None:
    """A ballpoint presses a groove into the paper; light from the side puts
    a faint shadow along one edge of every stroke. Darkens the paper just
    below-right of the ink (in place)."""
    h, w = ink.shape
    d = max(1.0, 1.1 * k)
    m = np.float32([[1, 0, d], [0, 1, d]])
    shadow = cv2.warpAffine(ink, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
    cv2.GaussianBlur(shadow, (0, 0), 0.9 * k, dst=shadow)
    shadow *= 1.0 - ink  # only on paper, never over the ink itself
    for c, tone in enumerate((0.14, 0.14, 0.12)):  # grey, a touch warm
        img[..., c] *= 1.0 - tone * shadow


def scan_effect(rgb: np.ndarray, seed: int, dpi: int, back: np.ndarray | None = None, look: str = "scanned", thin_px: int = 0, through: str = "medium", pen_shadow: bool = False) -> np.ndarray:
    """Apply scanner-like degradation to an RGB uint8 page image. ``back`` is
    an optional ink mask of the reverse side (already mirrored).

    Works in place on one float32 page buffer (plus single-channel scratch
    planes), so a 200 DPI A4 page needs ~110 MB at peak rather than several
    full-page copies: the whole app fits a 512 MB container."""
    rng = np.random.default_rng(seed)
    h, w = rgb.shape[:2]
    k = dpi / 150.0
    photo = look == "photo"
    rgb = hand_warp(rgb, np.random.default_rng(seed + 1), dpi)
    if thin_px:
        # A fine ballpoint: grow the paper into the strokes (thinner lines).
        n = max(1, round(thin_px * dpi / 200))
        rgb = cv2.dilate(rgb, np.ones((n + 1, n + 1), np.uint8))
    img = rgb.astype(np.float32)
    img *= 1.0 / 255.0

    # Ballpoint ink is never perfectly even: it skips and pools a little
    # along each stroke. Only ink is affected (paper has ~no ink to vary).
    flow = _smooth_noise(rng, h, w, 1.3 * k, 0.16)
    flow += 1.0
    np.clip(flow, 0.55, 1.4, out=flow)
    img -= 1.0
    img *= flow[..., None]
    img += 1.0
    del flow

    if pen_shadow:
        pen_groove_shadow(img, ink_mask(rgb), k)

    # 0. Show-through: the reverse side's writing, diffused by the paper.
    if back is not None:
        ghost = back.astype(np.float32)
        if back.dtype == np.uint8:
            ghost *= 1.0 / 255.0
        if ghost.shape != (h, w):
            ghost = cv2.resize(ghost, (w, h), interpolation=cv2.INTER_LINEAR)
        strength, blur = THROUGH_LEVELS.get(through, THROUGH_LEVELS["medium"])
        if photo:
            strength *= 1.15  # thin paper under a phone's light
        cv2.GaussianBlur(ghost, (0, 0), sigmaX=blur * k, dst=ghost)
        plane = np.empty((h, w), np.float32)
        for c, tone in enumerate((0.055, 0.05, 0.035)):  # ink seen through paper: grey-blue
            np.multiply(ghost, -tone * strength, out=plane)
            plane += 1.0
            img[..., c] *= plane
        del ghost, plane

    # 1. Ink sits in the paper: soft edges, very slight spread.
    cv2.GaussianBlur(img, (0, 0), sigmaX=0.55 * k, dst=img)

    # 2. Scanners slightly desaturate colours.
    gray = img.mean(axis=2)
    gray *= 0.12
    img *= 0.88
    img += gray[..., None]

    # 3. Paper tone: warm off-white in a scanner, cool white under room light.
    base = [0.955, 0.957, 0.978] if photo else [0.985, 0.972, 0.938]
    tint = np.array(base, np.float32) + rng.normal(0, 0.006, 3).astype(np.float32)
    img *= tint

    # 4. Paper fibre (fine, faint) + sensor grain (high frequency).
    fib = rng.normal(0, 1, (h // int(3 * k) + 2, w // int(3 * k) + 2)).astype(np.float32)
    fib = cv2.resize(fib, (w, h), interpolation=cv2.INTER_LINEAR)
    cv2.GaussianBlur(fib, (0, 0), 1.2 * k, dst=fib)
    fib *= 0.012
    fib += 1.0
    img *= fib[..., None]
    grain = rng.standard_normal((h, w), dtype=np.float32)
    grain *= 0.008
    img += grain[..., None]
    del fib, grain

    # 5. Uneven lighting: vignette + light falling off across the sheet.
    # Separable (a function of x plus a function of y): one page-sized plane.
    xx = np.arange(w, dtype=np.float32) / w
    yy = np.arange(h, dtype=np.float32) / h
    cx, cy = rng.uniform(0.4, 0.6), rng.uniform(0.35, 0.55)
    angle = rng.uniform(0, 2 * np.pi)
    vig, fall = (0.17, 0.08) if photo else (0.09, 0.03)
    fx = 1.0 - vig * (xx - cx) ** 2 - fall * (xx - 0.5) * np.cos(angle)
    fy = -vig * (yy - cy) ** 2 - fall * (yy - 0.5) * np.sin(angle)
    if photo:
        # The sheet curves towards the binding / fold: a soft shadow on one side.
        edge = xx if rng.random() < 0.5 else xx[::-1]
        fx -= 0.10 * np.exp(-edge / 0.05)
    light = np.add.outer(fy.astype(np.float32), fx.astype(np.float32))
    img *= light[..., None]
    del light

    # 6. Page slightly tilted and shifted on the scanner bed.
    tilt = rng.normal(0, 0.35)
    tilt = float(np.clip(tilt * (1.6 if photo else 1.0), -1.3, 1.3))
    m = cv2.getRotationMatrix2D((w / 2, h / 2), tilt, 1.0)
    m[:, 2] += rng.normal(0, 3 * k, 2)
    bed = tuple(float(v) for v in (np.array([0.80, 0.80, 0.79]) + rng.normal(0, 0.01, 3)))
    img = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=bed)

    # 7. Scanner tone curve (slightly more contrast in the darks).
    np.clip(img, 0.0, 1.0, out=img)
    np.power(img, 1.06, out=img)

    # 8. A few dust specks.
    for _ in range(int(rng.integers(3, 12))):
        x, y = int(rng.uniform(0, w)), int(rng.uniform(0, h))
        r = max(1, int(rng.uniform(0.6, 1.8) * k))
        v = float(rng.uniform(0.35, 0.75))
        cv2.circle(img, (x, y), r, (v, v, v), -1, lineType=cv2.LINE_AA)

    np.clip(img, 0.0, 1.0, out=img)
    img *= 255.0
    return img.astype(np.uint8)


def _pixels(page, dpi: int) -> np.ndarray:
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[..., :3]


def scanned_pdf(visible_pdf: bytes, text_layer_pdf: bytes, seed_key: str, dpi: int = FINAL_DPI, jpeg_quality: int = 84, show_through: bool = False, look: str = "scanned", thin_px: int = 0, through: str = "medium", pen_shadow: bool = False) -> bytes:
    """Build the scanned-look PDF: one JPEG per page + invisible text layer."""
    out = fitz.open()
    with fitz.open(stream=visible_pdf, filetype="pdf") as src, fitz.open(stream=text_layer_pdf, filetype="pdf") as layer:
        # Reverse-side ink is blurred anyway: low-resolution masks keep memory
        # small for long documents (resized up in scan_effect).
        # Half resolution, stored as uint8: legible reverse-side writing at
        # ~1 MB per page.
        masks = [(ink_mask(_pixels(page, max(48, dpi // 2))) * 255).astype(np.uint8) for page in src] if show_through else []
        for i, page in enumerate(src):
            rgb = _pixels(page, dpi)
            scanned = scan_effect(rgb, _seed(seed_key, i), dpi, back_of_page(masks, i) if show_through else None, look, thin_px, through, pen_shadow)
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
