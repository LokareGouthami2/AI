"""Retrieval + grounded-answer evaluation on the hand-written gold documents.

    python -m backend.rag.evaluate

Each question has an ``evidence`` string that must appear in a retrieved chunk
(retrieval hit) and, for answerable questions, in the final answer.
Unanswerable questions must be refused (answer = None).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from backend.config import REPO_ROOT
from backend.ml.gold import GOLD_DOCS
from backend.rag.chunker import chunk_tree
from backend.rag.embedder import get_embedder
from backend.rag.retriever import retrieve
from backend.rag.store import InMemoryStore

QA_SET = {
    "ml_chapter": [
        ("What is a training set?", "collection of labelled examples"),
        ("What does unsupervised learning do?", "finds structure in unlabelled data"),
        ("How does an agent learn in reinforcement learning?", "trial and error"),
        ("What is the difference between classification and regression?", "discrete category"),
        ("Why should a model not be evaluated on its training data?", "Never evaluate a model on the same data"),
        ("What is regression?", "target is a number"),
        ("What reduces the accuracy of a model?", "Noisy labels"),
        ("Who wrote Pattern Recognition and Machine Learning?", "Bishop"),
        ("What is the capital city of Australia?", None),
        ("How do you bake sourdough bread?", None),
    ],
    "biology_notes": [
        ("What is chlorophyll?", "green pigment"),
        ("Where does the Calvin cycle happen?", "stroma"),
        ("Where does the oxygen released in photosynthesis come from?", "comes from water"),
        ("What controls the rate of photosynthesis?", "shortest supply"),
        ("Which enzyme fixes carbon dioxide?", "RuBisCO"),
        ("Why do greenhouse farmers burn paraffin?", "raise both the temperature"),
        ("What is the boiling point of mercury?", None),
    ],
    "history_notes": [
        ("When was the Bastille stormed?", "14 July 1789"),
        ("Who led the Committee of Public Safety?", "Robespierre"),
        ("What was the Estates-General?", "assembly representing the clergy"),
        ("Why was France nearly bankrupt?", "expensive wars"),
        ("What happened to Marie Antoinette?", "guillotined"),
        ("Who invented the telephone?", None),
        ("What is photosynthesis?", None),
    ],
}


def _tree(blocks):
    from backend.nlp.structure import build_tree

    # Gold docs are already labelled: build the tree directly from labels (page 1..n by position).
    n = len(blocks)
    pages = [1 + (i * 3) // max(n, 1) for i in range(n)]
    return build_tree([t for _, t in blocks], [lbl for lbl, _ in blocks], pages, "Document")


def run() -> dict:
    from backend.llm.extractive import task_rag

    embedder = get_embedder()
    rows = []
    for doc_id, qas in QA_SET.items():
        tree = _tree(GOLD_DOCS[doc_id])
        specs = chunk_tree(tree, target=60, overlap=15)  # small docs → small chunks
        chunks = [{"id": f"{doc_id}-c{c.order_index}", "text": c.text, "page_start": c.page_start, "page_end": c.page_end, "section_path": c.section_path} for c in specs]
        store = InMemoryStore()
        store.add(doc_id, [c["id"] for c in chunks], embedder.embed([c["text"] for c in chunks]), [{} for _ in chunks])
        for q, evidence in qas:
            hits = retrieve(q, doc_id, chunks, embedder, store, top_k=5)
            rank = next((i + 1 for i, h in enumerate(hits) if evidence and evidence.lower() in h.text.lower()), None)
            ans = task_rag(q, [{"id": h.id, "text": h.text} for h in hits])
            rows.append(
                {
                    "doc": doc_id,
                    "question": q,
                    "answerable": evidence is not None,
                    "rank": rank,
                    "answer": ans.answer,
                    "answer_has_evidence": bool(evidence and ans.answer and evidence.lower() in ans.answer.lower()),
                    "refused": ans.answer is None,
                }
            )
    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]
    metrics = {
        "generated_at": datetime.now(UTC).isoformat(),
        "embedder": embedder.name,
        "answer_engine": "offline extractive (LLM answers are not scored here)",
        "n_questions": len(rows),
        "n_answerable": len(answerable),
        "n_unanswerable": len(unanswerable),
        "recall_at_1": round(sum(1 for r in answerable if r["rank"] == 1) / len(answerable), 4),
        "recall_at_5": round(sum(1 for r in answerable if r["rank"]) / len(answerable), 4),
        "mrr": round(sum(1 / r["rank"] for r in answerable if r["rank"]) / len(answerable), 4),
        "answer_contains_evidence": round(sum(r["answer_has_evidence"] for r in answerable) / len(answerable), 4),
        "refusal_accuracy_unanswerable": round(sum(r["refused"] for r in unanswerable) / len(unanswerable), 4),
        "false_refusals_answerable": sum(r["refused"] for r in answerable),
        "rows": rows,
    }
    out = REPO_ROOT / "ml_models" / "rag_metrics.json"
    out.write_text(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    m = run()
    print(json.dumps({k: v for k, v in m.items() if k != "rows"}, indent=2))
    for r in m["rows"]:
        flag = "OK " if (r["answer_has_evidence"] if r["answerable"] else r["refused"]) else "XX "
        print(flag, r["doc"], "|", r["question"], "| rank", r["rank"], "|", (r["answer"] or "<refused>")[:90])
