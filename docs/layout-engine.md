# Layout engine

`backend/layout/engine.py` — a pure function: `layout(WDM, RenderSettings) → DisplayList`.

## Geometry

* Page A4 / Letter; margins in mm; text box = page minus margins.
* **Line grid:** `line_height = font_size × line_spacing`. Every baseline sits
  on a grid line (a ruled line on ruled paper).
* `slots_per_page = ⌊(box height − deepest descender) / line_height⌋`.

## Pipeline

1. **Flatten** WDM into flows: text lines or *empty* paragraphs. Lists and
   quotes add indentation (1.6 em per level); list items get a marker (`•`,
   `1.`).
2. **Measure** every glyph's advance, including the seeded variation.
3. **Wrap:** greedy first-fit on word boundaries. Hard breaks force a line.
   Words wider than the line are force-broken and re-joined as one token
   for the quality check. Alignment: left, centre, right, or justify (not on
   last lines).
4. **Line pitch:** uniform per style and size, from the typeface's typical
   ascender and descender (`ceil((asc + desc) / line_height)` slots). Spacing
   is therefore consistent and doesn't depend on the letters in a line.
5. **Placement with ink-level collision avoidance:** after placing a line, its
   glyph ink boxes are compared with the line above, using only glyphs that
   overlap horizontally. On collision, or if the line would poke above the
   top margin, the line moves down one slot. At the page bottom it moves to
   the next page.
6. **Pagination rules**
   * *Keep-with-next:* a heading, any headings and blank lines directly
     following it, and the first 2 lines of the next text must share a page.
   * *Backtracking:* if a heading chain still ends a page (for example because
     collision slots pushed text down), the layout state is restored to a
     snapshot and the chain restarts on a new page.
   * *Orphans/widows:* no lone first line at the bottom, and no lone last line
     at the top, for paragraphs of 3 or more lines.
   * Headings are never split across pages when they fit on one.
7. **Spacing:** `paragraph_spacing` blank grid lines after each top-level
   block (default 1). Each empty paragraph adds exactly **one** line. So
   "Enter twice" is always visibly different from a normal paragraph break.
   Trailing empty paragraphs are trimmed and reported, so they never create
   an empty page.

## Output: DisplayList

`pages[] → glyphs (char, x, y, size, font, skew, shade, underline, marker)`,
`decorations (underline, quote bar)`, `lines (slot, baseline, ink extent, block id, kind)`,
plus `stats` (tokens in reading order, underlined characters, blank lines,
hard breaks, adjustments).

## How it's tested

* Golden behaviours: blank lines, hard breaks, alignment, markers, long words,
  orphan headings, determinism, per-block stability.
* **Property-based (Hypothesis):** random documents (unicode, lists, quotes,
  headings, marks, alignments) × 6 styles × font sizes 12–28 × line spacing
  1.2–3.0. Every layout must have no overflow, no ink overlap, no orphan
  headings, and **exactly** the document's token sequence. A 1,500-example
  stress run passes. This process found and fixed four real bugs:
  - collisions at the page bottom;
  - force-broken words counted as two tokens;
  - orphaned headings after collision shifts;
  - a checker false positive for headings taller than a page.
