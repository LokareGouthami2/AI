"""Offline extractive engine: produces the same output schemas as the LLM
using deterministic NLP (sentence scoring, pattern-based definition parsing,
distractor selection). Quality is lower than an LLM, but it is fully grounded
in the document — it only ever reuses sentences that exist in the source.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from backend.llm.schemas import (
    AssignmentOutput,
    ExamDefinition,
    ExamFormula,
    ExamOutput,
    Flashcard,
    FlashcardsOutput,
    NoteBlock,
    NoteSection,
    NotesOutput,
    QuizOutput,
    QuizQuestion,
    RagAnswer,
)
from backend.nlp.stats import _EN_STOP, split_sentences, tokenize_words
from backend.nlp.structure import DocumentTree, Section

_DEF_PATTERNS = [
    re.compile(r"^(?:definition\s*[:\-–]\s*)?(?P<term>[^:.;]{2,60}?)\s+(?:is defined as|refers to|is called|is known as|means)\s+(?P<def>.+)$", re.I),
    re.compile(r"^(?:definition|key term)\s*[:\-–]\s*(?P<term>[^:]{2,60}?)\s*[:\-–]\s*(?P<def>.+)$", re.I),
    re.compile(r"^(?:definition\s*[:\-–]\s*)(?P<term>[^:.;]{2,60}?)\s+(?:is|are)\s+(?P<def>.+)$", re.I),
    re.compile(r"^(?P<term>[A-Z][^:.;]{1,50}?)\s*[:\-–]\s*(?P<def>(?:a|an|the)\s.+)$"),
    re.compile(r"^(?P<term>(?:the |an |a )?[^:.;,]{2,50}?)\s+(?:is|are)\s+(?P<def>(?:a|an|the)\s.+)$", re.I),
]
_PREFIX = re.compile(r"^\s*(definition|example|e\.g\.|for example|for instance|important|note|remember|key point|nb|answer|ans|solution|model answer|a\d+\.|q\d+[.:]?|question\s*\d*[.:]?|\d+[.)])\s*[:.\-–]?\s*", re.I)
_STEP_SPLIT = re.compile(r"(?:step\s*\d+\s*[:.)-]\s*|\b\d\)\s*|(?<=[.;])\s*(?:first|then|next|finally|after that)\s*,\s*|^\s*(?:first|procedure:|method:)\s*,?\s*)", re.I)


def _strip_number(heading: str) -> str:
    return re.sub(r"^(chapter\s*)?[0-9.]+\s*[:.]?\s*", "", heading, flags=re.I)


def strip_prefix(text: str) -> str:
    return _PREFIX.sub("", text, count=1).strip()


def _content_words(text: str) -> list[str]:
    return [w.lower() for w in tokenize_words(text) if w.lower() not in _EN_STOP and len(w) > 2]


def _score_sentences(sentences: list[str], doc_freq: Counter) -> list[float]:
    scores = []
    for s in sentences:
        words = _content_words(s)
        if not words:
            scores.append(0.0)
            continue
        scores.append(sum(math.log1p(doc_freq[w]) for w in set(words)) / math.sqrt(len(words)))
    return scores


def _doc_freq(tree: DocumentTree) -> Counter:
    c: Counter = Counter()
    for sec, _ in tree.walk():
        for it in sec.items:
            c.update(set(_content_words(it.text)))
    return c


def parse_definition(text: str) -> tuple[str, str] | None:
    t = text.strip().rstrip(".")
    for pat in _DEF_PATTERNS:
        m = pat.match(t)
        if m:
            term = re.sub(r"^(the|an|a)\s+", "", m.group("term").strip(), flags=re.I)
            term = re.sub(r"^(definition|key term)\s*[:\-–]\s*", "", term, flags=re.I)
            d = m.group("def").strip()
            if 1 <= len(term.split()) <= 6 and len(d.split()) >= 3:
                return term[:1].upper() + term[1:], d[:1].upper() + d[1:] + "."
    return None


def split_steps(text: str) -> list[str]:
    parts = [p.strip(" ;.,") for p in _STEP_SPLIT.split(text) if p and p.strip(" ;.,")]
    parts = [p[:1].upper() + p[1:] for p in parts]
    return parts if len(parts) >= 2 else [text]


def _key_sentences(text: str, doc_freq: Counter, k: int) -> list[str]:
    sents = split_sentences(text)
    if len(sents) <= k:
        return sents
    scores = _score_sentences(sents, doc_freq)
    keep = sorted(sorted(range(len(sents)), key=lambda i: -scores[i])[:k])
    return [sents[i] for i in keep]


def _section_pages(sec: Section) -> list[int]:
    return sorted(sec.pages)


def _sections(tree: DocumentTree):
    for sec, _ in tree.walk():
        if sec.level == 0 and not sec.items:
            continue
        yield sec


def _notes_blocks(sec: Section, doc_freq: Counter, mode: str) -> list[NoteBlock]:
    blocks: list[NoteBlock] = []
    bullets: list[str] = []

    def flush():
        if bullets:
            blocks.append(NoteBlock(type="bullets", items=list(bullets)))
            bullets.clear()

    for it in sec.items:
        text = it.text.strip()
        if it.label == "DEFINITION":
            flush()
            d = parse_definition(strip_prefix(text)) or parse_definition(text)
            if d:
                blocks.append(NoteBlock(type="definition", term=d[0], text=d[1]))
            else:
                blocks.append(NoteBlock(type="definition", text=strip_prefix(text)))
        elif it.label == "EXAMPLE":
            flush()
            blocks.append(NoteBlock(type="example", text=strip_prefix(text)))
        elif it.label == "FORMULA":
            flush()
            blocks.append(NoteBlock(type="formula", text=text))
        elif it.label == "IMPORTANT_POINT":
            flush()
            blocks.append(NoteBlock(type="key_point", text=strip_prefix(text)))
        elif it.label == "PROCEDURE":
            flush()
            blocks.append(NoteBlock(type="numbered", items=split_steps(text)))
        elif it.label in ("QUESTION", "ANSWER", "REFERENCE"):
            flush()
            blocks.append(NoteBlock(type="paragraph", text=text))
        elif mode == "simple":
            sents = sorted(split_sentences(text), key=lambda s: len(s.split()))[:2]
            bullets.extend(s for s in split_sentences(text) if s in sents)
        else:  # PARAGRAPH / CONCLUSION / other → key sentences as bullets
            k = 2 if len(text.split()) > 40 else 1
            if mode == "clean":
                flush()
                blocks.append(NoteBlock(type="paragraph", text=text))
            else:
                bullets.extend(_key_sentences(text, doc_freq, k))
    flush()
    return blocks


def _notes(tree: DocumentTree, mode: str) -> NotesOutput:
    df = _doc_freq(tree)
    sections = []
    for sec in _sections(tree):
        blocks = _notes_blocks(sec, df, mode)
        heading = sec.heading or ("Introduction" if sec.level == 0 else "Notes")
        if not blocks and not sec.children:
            continue
        if not blocks:
            blocks = []
        sections.append(NoteSection(heading=heading, level=2 if sec.level == 2 else 1, blocks=blocks, source_pages=_section_pages(sec)))
    # Keep the document's own title (no "— Smart Notes" style suffixes).
    return NotesOutput(title=tree.title, sections=sections)


def task_clean(tree: DocumentTree, **_) -> NotesOutput:
    return _notes(tree, "clean")


def task_smart(tree: DocumentTree, **_) -> NotesOutput:
    return _notes(tree, "smart")


def task_simple(tree: DocumentTree, **_) -> NotesOutput:
    return _notes(tree, "simple")


def _items(tree: DocumentTree, label: str):
    for sec, _ in tree.walk():
        for it in sec.items:
            if it.label == label:
                yield it


def task_assignment(tree: DocumentTree, **_) -> AssignmentOutput:
    df = _doc_freq(tree)
    paragraphs = list(_items(tree, "PARAGRAPH"))
    intro = " ".join(_key_sentences(paragraphs[0].text, df, 2)) if paragraphs else f"This assignment discusses {tree.title}."
    headings = [s.heading for s in _sections(tree) if s.heading and s.level == 1]
    skip = re.compile(r"question|exercise|reference|bibliograph|source|conclusion|summary|self-test", re.I)
    content_headings = [h for h in headings if not skip.search(h)]
    objectives = [f"Explain {_strip_number(h).lower()}" for h in content_headings[:5]] or [f"Understand {tree.title}"]
    notes = _notes(tree, "smart")
    main = [s for s in notes.sections if not skip.search(s.heading)]
    conclusions = [it.text for it in _items(tree, "CONCLUSION")]
    conclusion = conclusions[0] if conclusions else (" ".join(_key_sentences(paragraphs[-1].text, df, 1)) if paragraphs else "")
    return AssignmentOutput(
        title=tree.title,
        introduction=intro,
        objectives=objectives,
        main_sections=main,
        examples=[strip_prefix(it.text) for it in _items(tree, "EXAMPLE")],
        conclusion=conclusion,
        references=[it.text for it in _items(tree, "REFERENCE")],
    )


def _definitions(tree: DocumentTree) -> list[ExamDefinition]:
    out: list[ExamDefinition] = []
    seen = set()
    for sec, _ in tree.walk():
        for it in sec.items:
            if it.label not in ("DEFINITION", "PARAGRAPH", "IMPORTANT_POINT"):
                continue
            candidates = [strip_prefix(it.text)] if it.label == "DEFINITION" else split_sentences(it.text)
            for c in candidates:
                d = parse_definition(c)
                if d and d[0].lower() not in seen:
                    seen.add(d[0].lower())
                    out.append(ExamDefinition(term=d[0], definition=d[1], source_pages=[it.page]))
    return out


def task_exam(tree: DocumentTree, keyphrases: list[str] | None = None, **_) -> ExamOutput:
    formulas = []
    for it in _items(tree, "FORMULA"):
        name = it.text.split("=")[0].strip() if "=" in it.text else "Formula"
        formulas.append(ExamFormula(name=name[:60], expression=it.text, meaning=f"Formula from page {it.page}."))
    questions = [strip_prefix(it.text) for it in _items(tree, "QUESTION")]
    for sec in _sections(tree):
        if sec.heading and len(questions) < 8 and not re.search(r"question|reference|bibliograph|conclusion|summary", sec.heading, re.I):
            questions.append(f"Explain the key ideas of '{_strip_number(sec.heading)}'.")
    return ExamOutput(
        title=f"{tree.title} — Exam Revision",
        definitions=_definitions(tree),
        formulas=formulas,
        key_concepts=(keyphrases or [])[:12],
        important_questions=questions[:10],
    )


def _difficulty(answer: str) -> str:
    n = len(answer.split())
    return "easy" if n <= 12 else "medium" if n <= 30 else "hard"


def task_flashcards(tree: DocumentTree, count: int = 10, **_) -> FlashcardsOutput:
    cards: list[Flashcard] = []
    for d in _definitions(tree):
        cards.append(Flashcard(question=f"What is {d.term.lower() if d.term[1:2].islower() else d.term}?", answer=d.definition, difficulty=_difficulty(d.definition), source_pages=d.source_pages))
    # Question → following answer pairs
    for sec, _ in tree.walk():
        for a, b in zip(sec.items, sec.items[1:]):
            if a.label == "QUESTION" and b.label == "ANSWER":
                ans = strip_prefix(b.text)
                cards.append(Flashcard(question=strip_prefix(a.text), answer=ans, difficulty=_difficulty(ans), source_pages=sorted({a.page, b.page})))
    for it in _items(tree, "FORMULA"):
        lhs = it.text.split("=")[0].strip() if "=" in it.text else None
        if lhs:
            cards.append(Flashcard(question=f"Write the formula for {lhs}.", answer=it.text, difficulty="medium", source_pages=[it.page]))
    for it in _items(tree, "IMPORTANT_POINT"):
        cards.append(Flashcard(question="What is an important point to remember from this topic?", answer=strip_prefix(it.text), difficulty="easy", source_pages=[it.page]))
    # Dedupe on question text, keep order.
    seen, unique = set(), []
    for c in cards:
        if c.question.lower() not in seen:
            seen.add(c.question.lower())
            unique.append(c)
    return FlashcardsOutput(cards=unique[:count])


def task_quiz(tree: DocumentTree, count: int = 5, keyphrases: list[str] | None = None, **_) -> QuizOutput:
    defs = _definitions(tree)
    questions: list[QuizQuestion] = []
    n = len(defs)
    if n >= 4:
        for i, d in enumerate(defs):
            distractors = [defs[(i + k) % n].definition for k in (1, 2, 3)]
            correct = i % 4
            options = distractors[:]
            options.insert(correct, d.definition)
            questions.append(
                QuizQuestion(
                    question=f"Which statement best describes {d.term}?",
                    options=options,
                    correct_index=correct,
                    explanation=f"The document defines {d.term} as: {d.definition}",
                    difficulty="medium",
                    source_pages=d.source_pages,
                )
            )
    # Cloze questions from key sentences using keyphrases as answers/distractors.
    phrases = [p for p in (keyphrases or []) if 1 <= len(p.split()) <= 3]
    if len(phrases) >= 4:
        df = _doc_freq(tree)
        used = set()
        for sec, _ in tree.walk():
            for it in sec.items:
                if it.label not in ("PARAGRAPH", "CONCLUSION") or len(questions) >= count * 2:
                    continue
                for sent in _key_sentences(it.text, df, 1):
                    hit = next((p for p in phrases if p.lower() in sent.lower() and p.lower() not in used), None)
                    if not hit:
                        continue
                    used.add(hit.lower())
                    blanked = re.sub(re.escape(hit), "_____", sent, count=1, flags=re.I)
                    others = [p for p in phrases if p.lower() != hit.lower() and p.lower() not in sent.lower()][:3]
                    if len(others) < 3:
                        continue
                    correct = len(questions) % 4
                    options = others[:]
                    options.insert(correct, hit)
                    questions.append(
                        QuizQuestion(
                            question=f"Fill in the blank: {blanked}",
                            options=options,
                            correct_index=correct,
                            explanation=f"The original sentence reads: {sent}",
                            difficulty="hard",
                            source_pages=[it.page],
                        )
                    )
    return QuizOutput(questions=questions[:count])


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s", "e"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def _answer_units(text: str) -> list[str]:
    """Sentences, with tiny fragments (e.g. 'C. M.' in a citation) re-attached."""
    units: list[str] = []
    for s in split_sentences(text):
        if units and (len(s.split()) < 5 or len(units[-1].split()) < 5):
            units[-1] = units[-1] + " " + s
        else:
            units.append(s)
    return units


def task_rag(question: str, chunks: list[dict], min_overlap: float = 0.34, **_) -> RagAnswer:
    """Extractive answer: the best-supported sentences from retrieved chunks,
    scored by IDF-weighted overlap of (stemmed) content words."""
    q_words = {_stem(w) for w in _content_words(question)}
    if not q_words or not chunks:
        return RagAnswer(answer=None, citations=[], confidence="low")
    cands = []
    for ch in chunks:
        for s in _answer_units(ch["text"]):
            if s.rstrip().endswith("?"):
                continue  # a question is never an answer
            words = {_stem(w) for w in _content_words(s)}
            if words:
                cands.append((s, ch["id"], words))
    if not cands:
        return RagAnswer(answer=None, citations=[], confidence="low")
    n = len(cands)
    idf = {w: math.log(1 + n / (1 + sum(1 for _, _, ws in cands if w in ws))) for w in q_words}
    total = sum(idf.values())
    scored = []
    for i, (s, cid, words) in enumerate(cands):
        overlap = sum(idf[w] for w in q_words & words) / total
        scored.append((overlap, i, s, cid))
    scored.sort(key=lambda t: (-t[0], t[1]))
    top = scored[0][0]
    if top < min_overlap:
        return RagAnswer(answer=None, citations=[], confidence="low")
    best = [t for t in scored[:3] if t[0] >= max(min_overlap, top * 0.75)][:2]
    return RagAnswer(
        answer=" ".join(t[2] for t in best),
        citations=list(dict.fromkeys(t[3] for t in best)),
        confidence="high" if top >= 0.6 else "medium" if top >= 0.45 else "low",
    )
