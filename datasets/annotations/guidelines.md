# Segment labelling guidelines

A *segment* is one logical block produced by `backend/nlp/preprocess.py`
(usually a paragraph, heading or list item). Assign exactly one label.

| Label | Use for | Boundary cases |
|---|---|---|
| TITLE | The document's main title (normally the first, largest line) | Only one per document |
| HEADING | Top-level section headings ("2. Types of Learning", "References") | Section titles like "Review Questions" are HEADING, not QUESTION |
| SUBHEADING | Headings nested under a heading ("2.1 Supervised Learning") | Unnumbered: decide by visual hierarchy |
| PARAGRAPH | Ordinary explanatory prose | Default when no other class applies |
| DEFINITION | States what a term means ("X is defined as…", "Definition: …", "Term: meaning") | A paragraph that merely *uses* a term is PARAGRAPH |
| EXAMPLE | Illustrations ("Example:", "For instance, …", worked examples) | |
| PROCEDURE | Ordered steps ("Step 1…", "First, … Then, … Finally, …") | A numbered list of facts is not a procedure |
| IMPORTANT_POINT | Explicit emphasis ("Important:", "Note:", "Remember:", "Key point:", "Exam tip:") | |
| FORMULA | Equations and formulas as standalone lines | A sentence that mentions a formula is PARAGRAPH |
| QUESTION | Review/exam questions, including imperatives ("Explain…", "Discuss…") | |
| ANSWER | Answers to questions ("Answer:", "Ans:", "Solution:") | |
| CONCLUSION | Concluding/summary paragraph ("In conclusion…", "To sum up…") | A heading "Conclusion" is HEADING |
| REFERENCE | Bibliography entries | |

The hand-written gold documents (`backend/ml/gold.py`) follow these rules and
are never used for training or model selection.
