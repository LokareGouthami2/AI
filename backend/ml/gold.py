"""Hand-written, hand-labelled gold documents.

These were written by hand, independently of the generator's templates, and
are NEVER used for training or model selection. They measure how well the
classifier transfers from synthetic training data to human-written notes.
"""

from backend.tests.fixtures.sample_content import ML_CHAPTER

BIOLOGY_NOTES: list[tuple[str, str]] = [
    ("TITLE", "Photosynthesis — Revision Notes"),
    ("HEADING", "Overview"),
    ("PARAGRAPH", "Plants capture light energy in their leaves and store it as chemical energy in sugar. Almost every food chain on the planet depends on this single process, which also releases the oxygen we breathe."),
    ("DEFINITION", "Chlorophyll: the green pigment inside chloroplasts that absorbs mostly red and blue light."),
    ("HEADING", "The Two Stages"),
    ("SUBHEADING", "Light-dependent reactions"),
    ("PARAGRAPH", "These take place on the thylakoid membranes. Water is split, oxygen is given off, and the energy carriers ATP and NADPH are produced for the next stage."),
    ("SUBHEADING", "The Calvin cycle"),
    ("PARAGRAPH", "In the stroma, carbon dioxide is fixed by the enzyme RuBisCO and, using ATP and NADPH, is turned into glucose over several turns of the cycle."),
    ("FORMULA", "6CO2 + 6H2O + light → C6H12O6 + 6O2"),
    ("IMPORTANT_POINT", "Remember: the oxygen released comes from water, not from carbon dioxide."),
    ("HEADING", "Limiting Factors"),
    ("PARAGRAPH", "The rate of photosynthesis is controlled by whichever factor is in shortest supply: light intensity, carbon dioxide concentration or temperature."),
    ("EXAMPLE", "For instance, a greenhouse farmer can burn paraffin to raise both the temperature and the CO2 level, which speeds up growth in winter."),
    ("PROCEDURE", "First, place a piece of pondweed in a beaker of water. Then, shine a lamp at set distances. Finally, count the bubbles of oxygen released per minute at each distance."),
    ("HEADING", "Exam Practice"),
    ("QUESTION", "1. Where in the chloroplast does the Calvin cycle happen?"),
    ("ANSWER", "Answer: In the stroma, the fluid that surrounds the thylakoids."),
    ("QUESTION", "Explain why increasing light intensity stops increasing the rate after a certain point."),
    ("ANSWER", "Ans: Another factor, such as carbon dioxide concentration, becomes limiting."),
    ("HEADING", "Summary"),
    ("CONCLUSION", "To sum up, photosynthesis converts light into chemical energy in two linked stages, and its rate is set by the most limiting factor."),
    ("HEADING", "Sources"),
    ("REFERENCE", "Campbell, N. A. & Reece, J. B. (2008). Biology (8th ed.). Pearson."),
]

HISTORY_NOTES: list[tuple[str, str]] = [
    ("TITLE", "The French Revolution (1789–1799)"),
    ("HEADING", "1. Causes"),
    ("PARAGRAPH", "By the late 1780s France was nearly bankrupt after expensive wars, and a series of poor harvests pushed the price of bread beyond the reach of ordinary families."),
    ("PARAGRAPH", "At the same time, Enlightenment writers were questioning the idea that kings ruled by divine right, and many members of the Third Estate resented paying most of the taxes."),
    ("DEFINITION", "The Estates-General was an assembly representing the clergy, the nobility and the common people, which had not met since 1614."),
    ("HEADING", "2. Key Events"),
    ("SUBHEADING", "2.1 The storming of the Bastille"),
    ("PARAGRAPH", "On 14 July 1789 crowds in Paris attacked the Bastille fortress, a symbol of royal authority, looking for gunpowder and weapons."),
    ("SUBHEADING", "2.2 The Reign of Terror"),
    ("PARAGRAPH", "Between 1793 and 1794 the Committee of Public Safety, led by Robespierre, executed thousands of people accused of opposing the revolution."),
    ("EXAMPLE", "Example: Queen Marie Antoinette was tried and guillotined in October 1793."),
    ("IMPORTANT_POINT", "Key point: the revolution replaced an absolute monarchy with, at least in theory, government based on the rights of citizens."),
    ("HEADING", "3. Questions for Discussion"),
    ("QUESTION", "Q1. Which cause of the revolution do you think was the most important, and why?"),
    ("QUESTION", "Q2. How did the Terror change public opinion about the revolution?"),
    ("ANSWER", "Answer: Many moderates turned against the radicals, which led to Robespierre's fall in July 1794."),
    ("HEADING", "4. Conclusion"),
    ("CONCLUSION", "In conclusion, financial crisis and new political ideas combined to overturn the old order, and the revolution's ideals shaped European politics for the next century."),
    ("HEADING", "Bibliography"),
    ("REFERENCE", "Doyle, W. (2002). The Oxford History of the French Revolution. Oxford University Press."),
    ("REFERENCE", "Schama, S. (1989). Citizens: A Chronicle of the French Revolution. Knopf."),
]

GOLD_DOCS = {"ml_chapter": ML_CHAPTER, "biology_notes": BIOLOGY_NOTES, "history_notes": HISTORY_NOTES}


def gold_samples() -> list[dict]:
    """Render each gold doc as PDF and TXT, extract, and align labels."""
    from backend.documents.extract import extract
    from backend.ml.dataset import DocSpec, Style, align
    from backend.ml.features import segment_samples
    from backend.nlp.preprocess import preprocess
    from backend.tests.fixtures.builders import build_pdf, build_txt

    out: list[dict] = []
    for name, blocks in GOLD_DOCS.items():
        for fmt, data in (("pdf", build_pdf(blocks)), ("txt", build_txt(blocks))):
            spec = DocSpec(doc_id=f"gold-{name}-{fmt}", subject=name, style=Style("sans", 11, 22, 16, 13, True, True, "arabic", True, "apa", fmt), blocks=blocks)
            segments = preprocess(extract(fmt, data, allow_ocr=False))
            aligned = align(spec, segments)
            samples = segment_samples([s for s, _ in aligned])
            for s, (_, label) in zip(samples, aligned):
                s.update(label=label, doc_id=spec.doc_id, subject=name, fmt=fmt)
            out.extend(samples)
    return out
