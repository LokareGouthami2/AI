from backend.nlp.structure import build_tree
from backend.rag.chunker import chunk_tree
from backend.rag.embedder import HashingEmbedder
from backend.rag.retriever import retrieve, rrf
from backend.rag.store import InMemoryStore
from backend.tests.fixtures.sample_content import ML_CHAPTER


def _setup(target=60):
    tree = build_tree([t for _, t in ML_CHAPTER], [lbl for lbl, _ in ML_CHAPTER], [1 + i // 13 for i in range(len(ML_CHAPTER))], "ML")
    specs = chunk_tree(tree, target=target, overlap=15)
    chunks = [{"id": f"c{c.order_index}", "text": c.text, "page_start": c.page_start, "page_end": c.page_end, "section_path": c.section_path} for c in specs]
    emb = HashingEmbedder()
    store = InMemoryStore()
    store.add("d", [c["id"] for c in chunks], emb.embed([c["text"] for c in chunks]), [{} for _ in chunks])
    return specs, chunks, emb, store


def test_chunks_respect_sections_and_size():
    specs, *_ = _setup()
    assert specs
    for c in specs:
        assert c.token_count <= 60 + 40  # one sentence may overflow the target
        assert c.page_start <= c.page_end
    # no chunk spans two different section paths
    assert len({c.section_path for c in specs}) > 3


def test_embedder_is_normalised_and_deterministic():
    e = HashingEmbedder()
    a, b = e.embed(["hello world"]), e.embed(["hello world"])
    assert (a == b).all()
    assert abs(float((a[0] ** 2).sum()) - 1.0) < 1e-5


def test_rrf_prefers_items_ranked_high_in_both():
    s = rrf([["a", "b", "c"], ["b", "a", "d"]])
    assert max(s, key=s.get) in ("a", "b") and s["a"] > s["c"] and s["b"] > s["d"]


def test_retrieval_finds_relevant_chunk():
    _, chunks, emb, store = _setup()
    hits = retrieve("What does unsupervised learning find?", "d", chunks, emb, store)
    assert hits and "unlabelled data" in hits[0].text


def test_retrieval_gate_returns_nothing_for_gibberish():
    _, chunks, emb, store = _setup()
    assert retrieve("zzqx vvkp", "d", chunks, emb, store) == []
