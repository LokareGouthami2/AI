"""Deterministic page layout: WDM + RenderSettings → DisplayList.

The engine works on a *line grid* ("slots"): line_height = font_size ×
line_spacing, and every baseline sits on a grid line (a ruled line on ruled
paper). Stages:

  1. flatten   – WDM tree → flat list of Flow items (text or empty paragraph)
  2. measure   – per-character advances *including* seeded handwriting
                 variation, so wrapping and drawing use identical numbers
  3. wrap      – greedy first-fit on word boundaries; hard breaks force lines;
                 over-long words are force-broken
  4. paginate  – slot allocation with keep-with-next for headings and
                 widow/orphan control for paragraphs
  5. place     – absolute glyph positions, decorations (underline, bullets,
                 quote bars), page furniture (rules, numbers)

Pure function: same (document, settings) ⇒ same DisplayList.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from backend.editor.wdm import (
    Blockquote,
    BulletList,
    HardBreakNode,
    Heading,
    OrderedList,
    Paragraph,
    TextNode,
    WDMDocument,
)
from backend.handwriting.styles import STYLES, bounded_gauss, seeded_rng
from backend.layout import fonts
from backend.layout.settings import RenderSettings

MM = 72.0 / 25.4
PAGE_SIZES = {"A4": (595.28, 841.89), "Letter": (612.0, 792.0)}
HEADING_SCALE = {1: 1.5, 2: 1.28, 3: 1.12}
SIZE_MULT = {None: 1.0, "normal": 1.0, "small": 0.85, "large": 1.2, "xlarge": 1.4}
INDENT_EM = 1.6  # list / quote indent per level, in font-size units
MIN_READABLE_PT = 9.0
ROT_SIGMA = 1.1  # degrees; per-letter rotation (bounded at 2 sigma)


# ---------------------------------------------------------------------------
# Display list
# ---------------------------------------------------------------------------


@dataclass
class Glyph:
    ch: str
    x: float
    y: float  # baseline, PDF coordinates (origin bottom-left)
    size: float
    font: str
    skew: float  # degrees
    shade: float  # 0.8-1.0 ink density
    fake_bold: bool
    underline: bool
    marker: bool
    line_id: int
    advance: float
    word_start: bool = False
    rot: float = 0.0  # small per-letter rotation in degrees (hand movement)
    weight: float = 0.0  # extra stroke width in pt (pen pressure)
    cont: bool = False  # first glyph of a line that continues a force-broken word


@dataclass
class Decoration:
    kind: str  # underline | quote_bar
    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    line_id: int


@dataclass
class LineBox:
    id: int
    page: int
    slot: int
    slots: int
    baseline: float
    x0: float
    x1: float
    ink_top: float
    ink_bottom: float
    block_id: str
    kind: str  # text | heading | blank
    text: str
    hard_break_end: bool = False


@dataclass
class PageOut:
    number: int
    glyphs: list[Glyph] = field(default_factory=list)
    decorations: list[Decoration] = field(default_factory=list)
    lines: list[LineBox] = field(default_factory=list)
    markers: list[tuple[float, float, float, float]] = field(default_factory=list)


@dataclass
class DisplayList:
    settings: RenderSettings
    width: float
    height: float
    box: tuple[float, float, float, float]  # x0, y0 (bottom), x1, y1 (top)
    line_height: float
    slots_per_page: int
    pages: list[PageOut]
    stats: dict = field(default_factory=dict)

    def all_lines(self) -> list[LineBox]:
        return [ln for p in self.pages for ln in p.lines]


# ---------------------------------------------------------------------------
# 1. Flatten
# ---------------------------------------------------------------------------


@dataclass
class Flow:
    kind: str  # text | empty
    block_id: str
    heading_level: int | None
    content: list
    align: str
    indent_em: float
    marker: str | None
    quote: bool
    group_end: bool = False


def flatten(doc: WDMDocument) -> list[Flow]:
    flows: list[Flow] = []

    def walk(blocks, indent: float, quote: bool) -> None:
        for b in blocks:
            if isinstance(b, (Heading, Paragraph)):
                empty = not b.content
                flows.append(
                    Flow(
                        kind="empty" if empty else "text",
                        block_id=b.id,
                        heading_level=b.level if isinstance(b, Heading) else None,
                        content=list(b.content),
                        align=b.align,
                        indent_em=indent,
                        marker=None,
                        quote=quote,
                    )
                )
            elif isinstance(b, (BulletList, OrderedList)):
                for n, item in enumerate(b.items):
                    marker = "•" if isinstance(b, BulletList) else f"{b.start + n}."
                    first = len(flows)
                    walk(item.blocks, indent + INDENT_EM, quote)
                    if len(flows) > first:
                        if flows[first].kind == "empty":
                            # an empty list item still shows its marker
                            flows[first].kind = "text"
                        flows[first].marker = marker
            elif isinstance(b, Blockquote):
                walk(b.blocks, indent + INDENT_EM, True)

    for top in doc.blocks:
        start = len(flows)
        walk([top], 0.0, False)
        if len(flows) > start:
            flows[-1].group_end = True
    return flows


# ---------------------------------------------------------------------------
# 2-3. Measure & wrap
# ---------------------------------------------------------------------------


@dataclass
class Char:
    ch: str
    font: str
    size: float
    adv: float
    bold: bool
    fake_bold: bool
    italic: bool
    underline: bool


@dataclass
class WrappedLine:
    words: list[list[Char]]
    spaces: list[float]  # space advance *before* each word (0 for first)
    width: float
    hard_break_end: bool
    max_size: float
    asc: float = 0.0  # max ink height above baseline, incl. variation bounds
    desc: float = 0.0  # max ink depth below baseline, incl. variation bounds
    continues: bool = False  # last word was force-broken and continues on the next line


class _Measurer:
    def __init__(self, settings: RenderSettings):
        self.s = settings
        self.style = STYLES[settings.style]
        # Never scale a style below a readable size (the checker enforces 9pt).
        self.base = max(settings.font_size * self.style.size_scale, MIN_READABLE_PT * 1.1)
        self.v = settings.variation

    def chars(self, flow: Flow, rng) -> list[Char | None]:
        """Chars with variation applied; ``None`` marks a hard break."""
        st = self.style
        hscale = HEADING_SCALE.get(flow.heading_level or 0, 1.0)
        out: list[Char | None] = []
        for node in flow.content:
            if isinstance(node, HardBreakNode):
                out.append(None)
                continue
            assert isinstance(node, TextNode)
            bold = "bold" in node.marks or flow.heading_level is not None
            italic = "italic" in node.marks
            underline = "underline" in node.marks
            mult = SIZE_MULT.get(node.font_size, 1.0) * hscale
            preferred = st.bold_font if (bold and st.bold_font) else st.font
            for ch in node.text.replace("\t", "    "):
                fname = fonts.font_for(ch, preferred)
                size = self.base * mult * (1 + bounded_gauss(rng, st.size_var * self.v))
                nominal = fonts.advance(ch, fname, size)
                if ch == " ":
                    adv = nominal * st.word_space * (1 + bounded_gauss(rng, 0.12 * self.v))
                else:
                    adv = max(nominal * 0.95, nominal + bounded_gauss(rng, st.spacing_var * self.v) * self.base)
                out.append(Char(ch, fname, size, adv, bold, bold and not st.bold_font, italic, underline))
        return out

    def variation_bound(self, size: float, width: float) -> float:
        """Upper bound on vertical displacement from drift, slope and jitter."""
        st, v = self.style, self.v
        rot = math.sin(math.radians(2 * ROT_SIGMA * v)) * size  # per-letter rotation
        return 2 * st.drift * v * self.s.font_size + 2 * 0.003 * v * width + 2 * st.baseline_var * v * size + rot

    def typical_extent(self, size: float) -> tuple[float, float]:
        """Typical ascender height / descender depth of the style's typeface."""
        f = fonts.font(self.style.font)
        his = sorted(f.ink_bounds(ch)[1] for ch in "bdhklABDEHKLT" if f.has(ch))
        los = sorted(-f.ink_bounds(ch)[0] for ch in "gjpqy" if f.has(ch))
        asc = (his[len(his) // 2] if his else 0.75) * size
        desc = (los[len(los) // 2] if los else 0.25) * size
        b = self.variation_bound(size, 0.0)
        return asc + b, desc + b

    def ink_extent(self, words: list[list[Char]], max_size: float, width: float) -> tuple[float, float]:
        asc, desc = 0.55 * max_size, 0.15 * max_size  # x-height / baseline minimum
        for w in words:
            for c in w:
                lo, hi = fonts.font(c.font).ink_bounds(c.ch)
                asc = max(asc, hi * c.size)
                desc = max(desc, -lo * c.size)
        b = self.variation_bound(max_size, width)
        return asc + b, desc + b

    def wrap(self, chars: list[Char | None], width: float) -> list[WrappedLine]:
        # Split into words (runs of non-space chars), spaces and breaks.
        tokens: list[tuple[str, object]] = []
        word: list[Char] = []
        for c in chars:
            if c is None:
                if word:
                    tokens.append(("word", word))
                    word = []
                tokens.append(("break", None))
            elif c.ch == " ":
                if word:
                    tokens.append(("word", word))
                    word = []
                tokens.append(("space", c))
            else:
                word.append(c)
        if word:
            tokens.append(("word", word))

        lines: list[WrappedLine] = []
        cur_words: list[list[Char]] = []
        cur_spaces: list[float] = []
        cur_w = 0.0
        pending_space = 0.0

        def finish(hard: bool) -> None:
            nonlocal cur_words, cur_spaces, cur_w, pending_space
            max_size = max((c.size for w in cur_words for c in w), default=self.base)
            asc, desc = self.ink_extent(cur_words, max_size, width)
            lines.append(WrappedLine(cur_words, cur_spaces, cur_w, hard, max_size, asc, desc))
            cur_words, cur_spaces, cur_w, pending_space = [], [], 0.0, 0.0

        for kind, val in tokens:
            if kind == "break":
                finish(True)
            elif kind == "space":
                pending_space += val.adv  # type: ignore[union-attr]
            else:
                w: list[Char] = val  # type: ignore[assignment]
                ww = sum(c.adv for c in w)
                space = pending_space if cur_words else 0.0
                if cur_words and cur_w + space + ww > width:
                    finish(False)
                    space = 0.0
                # Force-break a word that is wider than a whole line.
                while ww > width and not cur_words:
                    part: list[Char] = []
                    pw = 0.0
                    for c in w:
                        if part and pw + c.adv > width:
                            break
                        part.append(c)
                        pw += c.adv
                    cur_words, cur_spaces, cur_w = [part], [0.0], pw
                    finish(False)
                    w = w[len(part):]
                    lines[-1].continues = bool(w)
                    ww = sum(c.adv for c in w)
                if not w:
                    pending_space = 0.0
                    continue
                cur_words.append(w)
                cur_spaces.append(space)
                cur_w += space + ww
                pending_space = 0.0
        if cur_words or not lines or (tokens and tokens[-1][0] == "break"):
            finish(False)
        return lines


# ---------------------------------------------------------------------------
# 4-5. Paginate & place
# ---------------------------------------------------------------------------


def layout(doc: WDMDocument, settings: RenderSettings, content_hash: str = "") -> DisplayList:
    s = settings
    style = STYLES[s.style]
    W, H = PAGE_SIZES[s.page_size]
    x0, x1 = s.margin_left_mm * MM, W - s.margin_right_mm * MM
    y_top, y_bottom = H - s.margin_top_mm * MM, s.margin_bottom_mm * MM
    m = _Measurer(s)
    lh = s.font_size * s.line_spacing
    box_w = x1 - x0

    flows = flatten(doc)
    wrapped: list[list[WrappedLine]] = []
    for f in flows:
        if f.kind == "empty":
            wrapped.append([])
            continue
        rng = seeded_rng("chars", s.seed, s.style, f.block_id, _flow_text(f))
        indent = f.indent_em * s.font_size
        wrapped.append(m.wrap(m.chars(f, rng), box_w - indent))

    # Reserve room below the last grid line for the deepest descender.
    max_desc = max((wl.desc for lines in wrapped for wl in lines), default=0.35 * m.base)
    slots_per_page = max(3, int((y_top - y_bottom - max_desc - 1.0) // lh))

    def line_slots(wl: WrappedLine) -> int:
        """Uniform grid pitch for a line: typical ascender of this line's size
        plus a typical descender of body text above it. Using typeface metrics
        (not the line's actual letters) keeps spacing consistent."""
        asc_t, _ = m.typical_extent(wl.max_size)
        _, desc_t = m.typical_extent(m.base)
        return max(1, math.ceil((asc_t + desc_t) / lh))

    # Trailing empty paragraphs would only produce blank space / an empty page.
    last_content = max((i for i, f in enumerate(flows) if f.kind != "empty"), default=-1)
    trimmed = len(flows) - 1 - last_content
    flows, wrapped = flows[: last_content + 1], wrapped[: last_content + 1]

    pages: list[PageOut] = [PageOut(1)]
    slot = 0
    line_id = 0
    stats = {"blank_lines": 0, "hard_breaks": 0, "trimmed_trailing_blank": trimmed, "orphan_headings_avoided": 0, "widow_orphan_adjustments": 0, "collision_slots": 0}
    tokens: list[str] = []
    underlined_chars: list[str] = []
    prev_line_glyphs: list[Glyph] = []
    continued_word = False

    def new_page():
        nonlocal slot, prev_line_glyphs
        pages.append(PageOut(len(pages) + 1))
        slot = 0
        prev_line_glyphs = []

    def baseline_for(end_slot: int) -> float:
        return y_top - (end_slot + 1) * lh + 1.0

    def place(f: Flow, wl: WrappedLine, per: int, first: bool, last: bool) -> None:
        """Place one line at the current slot, moving it down a slot at a time
        if its glyphs would touch the previous line's ink or the top edge."""
        nonlocal slot, line_id, prev_line_glyphs, continued_word
        page = pages[-1]
        end_slot = slot + per - 1
        while True:
            if end_slot >= slots_per_page and slot > 0:
                # No room left on this page (possibly after collision retries).
                new_page()
                page = pages[-1]
                end_slot = per - 1
            snap = (len(page.glyphs), len(page.decorations), len(page.lines), len(page.markers))
            bl = baseline_for(end_slot)
            lb, words = _place_line(page, f, wl, bl, x0, box_w, line_id, s, first, last)
            mine = page.glyphs[snap[0]:]
            too_high = any(g.y + fonts.font(g.font).ink_bounds(g.ch)[1] * g.size > y_top for g in mine)
            if (too_high or glyphs_collide(prev_line_glyphs, mine)) and end_slot - slot < 6:
                del page.glyphs[snap[0]:], page.decorations[snap[1]:], page.lines[snap[2]:], page.markers[snap[3]:]
                end_slot += 1
                stats["collision_slots"] += 1
                continue
            break
        lb.slot, lb.slots = slot, end_slot - slot + 1
        if continued_word:
            first = next((g for g in mine if not g.marker), None)
            if first is not None:
                first.cont = True
        if continued_word and words:
            tokens[-1] += words[0]  # rejoin a force-broken word
            words = words[1:]
        tokens.extend(words)
        continued_word = wl.continues
        underlined_chars.extend(c.ch for w in wl.words for c in w if c.underline)
        stats["hard_breaks"] += int(wl.hard_break_end)
        prev_line_glyphs = [g for g in mine if not g.marker] + [g for g in mine if g.marker]
        line_id += 1
        slot = end_slot + 1

    def snapshot() -> dict:
        last = pages[-1]
        return {
            "n_pages": len(pages),
            "lens": (len(last.glyphs), len(last.decorations), len(last.lines), len(last.markers)),
            "tokens": len(tokens),
            "ul": len(underlined_chars),
            "stats": dict(stats),
            "slot": slot,
            "line_id": line_id,
            "prev": prev_line_glyphs,
            "cont": continued_word,
        }

    def restore(snap: dict) -> None:
        nonlocal slot, line_id, prev_line_glyphs, continued_word
        del pages[snap["n_pages"]:]
        last = pages[-1]
        g, d, ln, mk = snap["lens"]
        del last.glyphs[g:], last.decorations[d:], last.lines[ln:], last.markers[mk:]
        del tokens[snap["tokens"]:], underlined_chars[snap["ul"]:]
        stats.clear()
        stats.update(snap["stats"])
        slot, line_id = snap["slot"], snap["line_id"]
        prev_line_glyphs, continued_word = snap["prev"], snap["cont"]

    def place_flow(i: int) -> None:
        nonlocal slot, line_id, prev_line_glyphs
        f, lines = flows[i], wrapped[i]
        if f.kind == "empty":
            if slot + 1 > slots_per_page:
                new_page()
            bl = baseline_for(slot)
            pages[-1].lines.append(LineBox(line_id, pages[-1].number, slot, 1, bl, x0, x0, bl, bl, f.block_id, "blank", ""))
            line_id += 1
            slot += 1
            stats["blank_lines"] += 1
            prev_line_glyphs = []
        else:
            per = [line_slots(wl) for wl in lines]
            if f.heading_level is not None:
                # keep-with-next: the heading, any headings/blank lines that
                # directly follow it, and the first 2 lines of the next text.
                need = sum(per) + (s.paragraph_spacing if f.group_end else 0)
                for j in range(i + 1, len(flows)):
                    fj, wj = flows[j], wrapped[j]
                    if fj.kind == "empty":
                        need += 1
                        continue
                    need += sum(line_slots(wl) for wl in wj[:2])
                    if fj.heading_level is None:
                        break
                    need += s.paragraph_spacing if fj.group_end else 0
                heading_fits = sum(per) <= slots_per_page
                if slot > 0 and slot + need > slots_per_page and (need <= slots_per_page or heading_fits):
                    stats["orphan_headings_avoided"] += 1
                    new_page()
            idx = 0
            n = len(lines)
            while idx < n:
                room = slots_per_page - slot
                fit = 0
                used = 0
                for p in per[idx:]:
                    if used + p > room:
                        break
                    used += p
                    fit += 1
                remaining = n - idx
                if fit < remaining and f.heading_level is not None and slot > 0 and sum(per[idx:]) <= slots_per_page:
                    fit = 0  # never split a heading across pages when it fits on one
                elif fit < remaining and f.heading_level is None and n >= 3:
                    if fit == 1 and idx == 0:  # orphan: lone first line at page bottom
                        fit = 0
                        stats["widow_orphan_adjustments"] += 1
                    elif remaining - fit == 1 and fit >= 2:  # widow: lone last line on next page
                        fit -= 1
                        stats["widow_orphan_adjustments"] += 1
                if fit == 0:
                    if slot == 0:
                        fit = 1  # a single line taller than a page: place anyway
                    else:
                        new_page()
                        continue
                page_before = len(pages)
                for k in range(idx, idx + fit):
                    place(f, lines[k], per[k], k == 0, k == n - 1)
                idx += fit
                if idx < n and len(pages) == page_before:
                    new_page()
        if f.group_end and f.kind != "empty" and i < len(flows) - 1 and s.paragraph_spacing:
            if slot > 0:
                slot = min(slot + s.paragraph_spacing, slots_per_page)
                prev_line_glyphs = []
        if slot >= slots_per_page and i < len(flows) - 1:
            new_page()

    def heading_orphaned(first: int, last: int) -> bool:
        """After placing flows first..last (a heading chain + following text),
        is any heading in the chain the last content line of its page?"""
        chain_ids = {flows[k].block_id for k in range(first, last) if flows[k].heading_level is not None}
        for p in pages[:-1]:
            content = [ln for ln in p.lines if ln.kind != "blank"]
            if content and content[-1].block_id in chain_ids:
                return True
        return False

    i = 0
    while i < len(flows):
        if flows[i].heading_level is None:
            place_flow(i)
            i += 1
            continue
        # A heading chain: headings/blank lines up to and including the next text flow.
        j = i
        while j < len(flows) and (flows[j].heading_level is not None or flows[j].kind == "empty"):
            j += 1
        end = min(j + 1, len(flows))
        snap = snapshot()
        for k in range(i, end):
            place_flow(k)
        if heading_orphaned(i, end) and snap["slot"] > 0:
            # Backtrack: start the whole chain on a fresh page.
            restore(snap)
            new_page()
            stats["orphan_headings_avoided"] += 1
            for k in range(i, end):
                place_flow(k)
        i = end

    # Drop a trailing page left empty by spacing.
    if len(pages) > 1 and not pages[-1].lines:
        pages.pop()

    stats.update(
        tokens=tokens,
        underlined_chars="".join(underlined_chars),
        pages=len(pages),
        lines=sum(len(p.lines) for p in pages),
        min_font_size=min((g.size for p in pages for g in p.glyphs), default=s.font_size),
        style=style.name,
        content_hash=content_hash,
    )
    return DisplayList(s, W, H, (x0, y_bottom, x1, y_top), lh, slots_per_page, pages, stats)


def glyphs_collide(upper: list[Glyph], lower: list[Glyph], tol: float = 0.3) -> bool:
    """True if any glyph of ``lower`` overlaps (in x) a glyph of ``upper`` whose
    descender reaches below the lower glyph's ascender (ink-level check)."""
    if not upper or not lower:
        return False
    bins: dict[int, list[tuple[float, float, float]]] = {}
    for g in upper:
        lo = fonts.font(g.font).ink_bounds(g.ch)[0]
        bottom = g.y + lo * g.size
        for b in range(int(g.x // 8), int((g.x + g.advance) // 8) + 1):
            bins.setdefault(b, []).append((g.x, g.x + g.advance, bottom))
    for g in lower:
        hi = fonts.font(g.font).ink_bounds(g.ch)[1]
        top = g.y + hi * g.size
        for b in range(int(g.x // 8), int((g.x + g.advance) // 8) + 1):
            for ux0, ux1, bottom in bins.get(b, ()):
                if ux0 < g.x + g.advance and g.x < ux1 and bottom < top - tol:
                    return True
    return False


def _flow_text(f: Flow) -> str:
    return "".join(n.text if isinstance(n, TextNode) else "\n" for n in f.content)


def _place_line(page: PageOut, f: Flow, wl: WrappedLine, baseline: float, x0: float, box_w: float, line_id: int, s: RenderSettings, first: bool, last: bool) -> tuple[LineBox, list[str]]:
    style = STYLES[s.style]
    v = s.variation
    indent = f.indent_em * s.font_size
    avail = box_w - indent
    rng = seeded_rng("line", s.seed, s.style, f.block_id, line_id, "".join(c.ch for w in wl.words for c in w))

    # Alignment
    gap_extra = 0.0
    if f.align == "center":
        start = x0 + indent + (avail - wl.width) / 2
    elif f.align == "right":
        start = x0 + indent + (avail - wl.width)
    else:
        start = x0 + indent
        if f.align == "justify" and not last and not wl.hard_break_end and len(wl.words) > 1:
            gap_extra = (avail - wl.width) / (len(wl.words) - 1)

    # Per-line drift: offset + gentle slope, both bounded.
    drift = bounded_gauss(rng, style.drift * v * s.font_size)
    slope = bounded_gauss(rng, 0.003 * v)

    # Marker (bullet / number) in the hanging indent.
    if first and f.marker:
        mfont = style.font
        msize = s.font_size * style.size_scale * (1.35 if f.marker == "•" else 1.0)
        mw = sum(fonts.advance(ch, fonts.font_for(ch, mfont), msize) for ch in f.marker)
        mx = x0 + indent - mw - 0.45 * s.font_size
        cx = mx
        for ch in f.marker:
            fn = fonts.font_for(ch, mfont)
            adv = fonts.advance(ch, fn, msize)
            page.glyphs.append(Glyph(ch, cx, baseline + drift, msize, fn, style.slant_deg, 1.0, False, False, True, line_id, adv))
            cx += adv
        page.markers.append((mx - 1, baseline - 0.4 * msize, cx + 1, baseline + msize))

    x = start
    words_out: list[str] = []
    ink_top, ink_bottom = baseline, baseline
    underline_run: list[float] | None = None
    ul_width = max(0.6, 0.055 * s.font_size)
    for wi, (word, space) in enumerate(zip(wl.words, wl.spaces)):
        if wi:
            gap = space + gap_extra
            if underline_run is not None and not (word[0].underline and wl.words[wi - 1][-1].underline):
                _close_underline(page, underline_run, baseline, drift, slope, start, ul_width, line_id, s)
                underline_run = None
            x += gap
        skew = style.slant_deg + bounded_gauss(rng, style.slant_var * v)
        shade = 0.84 + rng.random() * 0.16
        # Pen pressure: a subtle, continuous variation in stroke weight.
        weight = rng.uniform(0.0, 0.011) * s.font_size * min(v, 1.5)
        words_out.append("".join(c.ch for c in word))
        for ci, c in enumerate(word):
            dy = drift + slope * (x - start) + bounded_gauss(rng, style.baseline_var * v * c.size)
            y = baseline + dy
            rot = bounded_gauss(rng, ROT_SIGMA * v)
            letter_shade = shade * (1.0 - rng.uniform(0.0, 0.07 * min(v, 1.5)))  # ink flow varies per letter
            page.glyphs.append(Glyph(c.ch, x, y, c.size, c.font, skew + (10.0 if c.italic else 0.0), letter_shade, c.fake_bold, c.underline, False, line_id, c.adv, ci == 0 and wi > 0, rot, weight))
            lo, hi = fonts.font(c.font).ink_bounds(c.ch)
            ink_top = max(ink_top, y + hi * c.size)
            ink_bottom = min(ink_bottom, y + lo * c.size)
            if c.underline:
                if underline_run is None:
                    underline_run = [x, x + c.adv]
                else:
                    underline_run[1] = x + c.adv
            elif underline_run is not None:
                _close_underline(page, underline_run, baseline, drift, slope, start, ul_width, line_id, s)
                underline_run = None
            x += c.adv
    if underline_run is not None:
        _close_underline(page, underline_run, baseline, drift, slope, start, ul_width, line_id, s)

    if f.quote:
        top = baseline + 0.95 * s.font_size
        page.decorations.append(Decoration("quote_bar", x0 + indent - 0.7 * s.font_size, baseline - 0.35 * s.font_size, x0 + indent - 0.7 * s.font_size, top, 1.2, line_id))

    lb = LineBox(line_id, page.number, 0, 1, baseline, start, x, ink_top, ink_bottom, f.block_id, "heading" if f.heading_level else "text", " ".join(words_out), wl.hard_break_end)
    page.lines.append(lb)
    return lb, words_out


def _close_underline(page: PageOut, run: list[float], baseline: float, drift: float, slope: float, start: float, width: float, line_id: int, s: RenderSettings) -> None:
    y1 = baseline + drift + slope * (run[0] - start) - 0.13 * s.font_size
    y2 = baseline + drift + slope * (run[1] - start) - 0.13 * s.font_size
    page.decorations.append(Decoration("underline", run[0], y1, run[1], y2, width, line_id))
