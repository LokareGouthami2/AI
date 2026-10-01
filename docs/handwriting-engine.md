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
| Student ballpoint | Nothing You Could Do (OFL) | Fast, slanted ballpoint print |
| Student print | Annie Use Your Telescope (OFL) | Thin upright print (+3° slant) |
| Real student hand | Mynerve (OFL) | Round, partly joined ballpoint hand; wide word gaps, rising lines, creeping margin |

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

## Per-letter realism

* Every letter gets a small bounded rotation (σ = 1.1°, clipped at 2σ) on
  top of the per-word slant. It's included in the collision bounds.
* Ink flow varies per letter (up to 7 % lighter), and pen pressure varies per
  word as a subtle extra stroke weight.

## Output look: Scanned (default) or Clean

**Scanned** (`backend/pdf/scan.py`) makes the page look like a real
handwritten sheet that went through a scanner or phone scan app. Every step is
seeded, so the output is deterministic:

1. Rasterise the vector page (200 DPI final, 130 DPI preview).
2. Soften ink edges and desaturate slightly.
3. Apply a warm paper tone, fine paper fibre and sensor grain.
4. Add uneven lighting (vignette plus fall-off across the sheet).
5. Tilt the page up to ±0.8° with a small shift on a grey scanner bed.
6. Apply a tone curve and a few dust specks.
7. Compress as JPEG.

Each page of the PDF is a scan image with an **invisible text layer**
(identical glyph positions, no rotation) on top. The PDF is still searchable,
and the quality audit reads that layer back: the text must match the document
exactly. The underline audit runs on the vector render before scanning.

**Clean** gives the original vector PDF.

The "Generated with WriteAI" footer is **off by default** and can be switched
on in the settings.

## Writer habits (style profile)

A font repeats the same glyph for every letter; a person doesn't. Styles can
switch on habits measured from a real handwritten assignment:

| Habit | Effect | Bounded by |
|---|---|---|
| `rise` | lines climb slightly to the right | added to the collision bound |
| `margin_creep` | the left edge drifts right line by line within a paragraph | room reserved when wrapping, so lines never overflow |
| `xscale_var` | each letter a little wider or narrower | 2σ clip |
| `pressure` | per-word pen-pressure weight (0 for a fine ballpoint) | — |

## Hand warp (scan and photo looks)

Before the scanner/camera effects, the page raster goes through a smooth,
seeded displacement field (`scan.hand_warp`): a short-wave part (≈2.6 px
features, ≈0.75 px amplitude) bends strokes so that no two copies of a letter
are identical, and a long-wave part makes lines gently wavy. Ballpoint ink
flow is uneven too: a fine noise field lightens and darkens strokes (not the
paper). The invisible text layer is unaffected, so search and the audit still
read the exact text.

## Photo look

`output: "photo"` looks like a phone photo of the sheets rather than a flatbed
scan: cool white paper under room light, a stronger light fall-off, a soft
shadow where the sheet curves towards the binding, slightly more tilt, and
stronger show-through.

## Shadows: show-through and pen grooves

* **Show-through** (`show_through`, `show_through_level`): the reverse side
  of each sheet is another page's writing (the next page, else the previous
  one), mirrored left↔right, blurred by the paper and multiplied in as
  grey-blue. Levels: *light* (faint, very soft), *medium* (as on ordinary
  70 gsm paper in a photo; the preset's default) and *strong* (thin paper).
  The reverse-side masks are kept at half resolution as uint8 (~1 MB a page).
* **Pen-groove shadow** (`pen_shadow`): a ballpoint presses a groove into the
  paper, and side light puts a faint shadow along one edge of each stroke.
  The ink mask is shifted ~1 px down-right, blurred and used to darken only
  the paper next to the strokes.

Neither touches the invisible text layer, so search and the PDF audit read
the exact text (tested).

## Line grid on unruled paper

On ruled and grid paper a line must sit on a printed rule, so the slot grid
is one line. On blank and assignment paper the grid is a third of a line:
when a tall letter would touch the line above, the line moves down by a
third of a line, not a whole one, so spacing stays even like real writing.

## Assignment sheet

Modelled on a real handwritten university assignment: loose unruled paper,
written in blue ballpoint, then scanned. The **Assignment sheet** preset in the
UI ("Handwritten assignment (real-photo look)") sets these options, plus the
Real student hand, bright ballpoint ink and the photo look (all of them can
also be used on their own):

| Setting | Effect |
|---|---|
| `paper: "assignment"` | No ruling; a thin header line across the top and a margin line down the left |
| `header_name`, `header_id` | Written top-left on every page, one under the other, in the same hand (one printable line each, max 80 characters) |
| `page_number_position: "top-right"` | Page number written at the top right instead of "– n –" at the bottom |
| `underline_headings` | A hand-drawn, slightly bowed pen line under every heading line |
| `plain_headings` | Headings at body size and not bold, as people write them by hand |
| `show_through` | Scanned look: faint, blurred, mirrored writing from the back of the sheet |

* **Header band** (`layout/engine.py: header_band`): computed by the layout
  engine, not the renderer, so the text box always starts below it. The
  header text never enters the body text, the content audit or the token
  coverage check.
* **Heading underlines stay opt-in.** The editor never adds underline marks
  automatically, and this doesn't change that: heading rules are a separate
  decoration kind (`heading_rule`), drawn only when the user enables the
  option. The checker rejects any heading rule when the option is off, or
  under a line that isn't a heading.
* **Show-through** uses the ink of the next page (else the previous one;
  a one-page document uses its own writing shifted down) as a low-resolution
  mask, mirrored, blurred and multiplied in at about 5 % strength before the
  scanner effects.

## PDF output

* Vector text via ReportLab (selectable and searchable). Each glyph is placed
  with its own text matrix: translation for jitter, shear for slant.
* Invisible real space characters are written between words, so copy/paste,
  search and the quality audit read words correctly.
* Paper (ruled with margin line, grid, or blank), page numbers, and an
  optional "Generated with WriteAI" footer (off by default).
* Metadata: `writeai:content_hash`, `writeai:revision`, `writeai:settings_hash`.
* **Preview = raster of the same PDF** (PyMuPDF, 110 DPI), cached under the
  content and settings hashes.
