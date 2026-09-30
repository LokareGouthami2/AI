# Handwriting engine

`backend/handwriting/styles.py` · `backend/layout/fonts.py` · `backend/pdf/render.py`

The goal is **controlled imperfection**: text that reads as handwritten, stays
perfectly legible, and is reproducible.

## Styles

| Style | Font (licence) | Character |
|---|---|---|
| Neat | Kalam 400/700 (OFL) | Real bold cut, slight right slant |
| Casual | Patrick Hand (OFL) | Rounded print |
| Cursive | Homemade Apple (Apache 2.0) | Joined script (scaled 0.78) |
| Playful | Indie Flower (OFL) | Loose, bouncy |
| Quick notes | Caveat 400/700 (OFL) | Fast note-taking hand |
| Light | Shadows Into Light (OFL) | Thin, airy |

The fonts are the Latin subsets from the `@fontsource/*` npm packages,
converted WOFF → TTF with fontTools; licences are in `backend/assets/fonts/`.
Characters a handwriting font lacks (Σ, →, ≤ …) fall back glyph by glyph to
bundled **DejaVu Sans**.

## Variation model

Each style profile sets bounded amplitudes, scaled by the user's *variation*
setting (0–2):

| Effect | Scope | Bound |
|---|---|---|
| Baseline drift | per line (offset + slope) | 2σ clipping |
| Vertical jitter | per glyph | 2σ clipping |
| Size variation | per glyph | ±2σ (a few %) |
| Letter spacing | per glyph | never below 95 % of the nominal advance |
| Word spacing | per space | ±24 % |
| Slant | per word (+10° for italic) | shear only, baseline stays horizontal |
| Ink density | per word | 84–100 % ink mixed with paper colour |

* **Deterministic:** the RNG is seeded from `(seed, style, block id, text)`,
  so the same document and settings always give byte-identical PDFs (tested).
  Editing one paragraph leaves the others' handwriting unchanged (tested).
* **Measured before wrapping:** advances include the variation, so line
  breaking and drawing use identical numbers.
* **Bounded:** `bounded_gauss` clips at 2σ. The layout engine adds the
  worst-case displacement to each line's ink extent, so collisions are
  prevented rather than hoped against.
* **Bold:** the real bold cut where the font has one; otherwise PDF text
  render mode 2 (fill + thin stroke). Each line's text object sits in its own
  graphics state, because a bold state leaking into the next line was a real
  bug caught during development.

## PDF output

* Vector text via ReportLab (selectable and searchable). Each glyph is placed
  with its own text matrix: translation for jitter, shear for slant.
* Invisible real space characters are written between words, so copy/paste,
  search and the quality audit read words correctly.
* Paper (ruled with margin line, grid, or blank), page numbers, and an
  optional "Generated with WriteAI" footer (on by default).
* Metadata: `writeai:content_hash`, `writeai:revision`, `writeai:settings_hash`.
* **Preview = raster of the same PDF** (PyMuPDF, 110 DPI), cached under the
  content and settings hashes.
