import { useEffect, useState } from 'react';
import { api } from '../services/api.js';
import { ErrorAlert, Spinner } from '../components/ui.jsx';

export default function Flashcards({ docId }) {
  const [set, setSet] = useState(null);
  const [cards, setCards] = useState([]);
  const [editing, setEditing] = useState(false);
  const [flipped, setFlipped] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.latestFlashcards(docId).then((s) => s && (setSet(s), setCards(s.cards))).catch(() => {});
  }, [docId]);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const s = await api.flashcards(docId, 12);
      setSet(s);
      setCards(s.cards);
      setFlipped({});
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    try {
      const s = await api.saveFlashcards(docId, set.id, cards.filter((c) => c.question.trim() && c.answer.trim()));
      setCards(s.cards);
      setEditing(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const update = (i, k, v) => setCards((cs) => cs.map((c, j) => (j === i ? { ...c, [k]: v } : c)));

  return (
    <div className="stack" data-testid="flashcards">
      <div className="row">
        <button className="btn btn-primary" onClick={generate} disabled={busy} data-testid="gen-flashcards">
          {busy && !editing ? <Spinner /> : null} {set ? 'Regenerate' : 'Generate'} flashcards
        </button>
        {set && !editing && <button className="btn" onClick={() => setEditing(true)} data-testid="edit-flashcards">Edit cards</button>}
        {editing && (
          <>
            <button className="btn btn-primary" onClick={save} disabled={busy} data-testid="save-flashcards">Save cards</button>
            <button className="btn" onClick={() => setCards((cs) => [...cs, { question: '', answer: '', difficulty: 'medium', source_pages: [] }])}>+ Add card</button>
            <button className="btn btn-ghost" onClick={() => (setCards(set.cards), setEditing(false))}>Cancel</button>
          </>
        )}
        {saved && <span className="badge badge-success">✓ Saved</span>}
        {set?.status === 'fallback' && <span className="small muted">AI unavailable — offline engine used.</span>}
      </div>
      <ErrorAlert error={error} />
      {set && cards.length === 0 && <p className="muted">No flashcards could be generated from this document.</p>}
      {editing ? (
        <div className="stack">
          {cards.map((c, i) => (
            <div key={i} className="card grid-2">
              <label className="field"><span>Question</span><textarea className="textarea" value={c.question} onChange={(e) => update(i, 'question', e.target.value)} /></label>
              <label className="field"><span>Answer</span><textarea className="textarea" value={c.answer} onChange={(e) => update(i, 'answer', e.target.value)} /></label>
              <div className="row">
                <select className="select" style={{ width: 140 }} value={c.difficulty} onChange={(e) => update(i, 'difficulty', e.target.value)} aria-label="Difficulty">
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
                <button className="btn btn-sm btn-danger" onClick={() => setCards((cs) => cs.filter((_, j) => j !== i))}>Remove</button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="grid-3">
          {cards.map((c, i) => (
            <div key={i} className={`flashcard ${flipped[i] ? 'flipped' : ''}`} onClick={() => setFlipped((f) => ({ ...f, [i]: !f[i] }))} role="button" tabIndex={0} aria-label={`Flashcard ${i + 1}`} onKeyDown={(e) => e.key === 'Enter' && setFlipped((f) => ({ ...f, [i]: !f[i] }))}>
              <div className="flashcard-inner">
                <div className="flashcard-face">{c.question}</div>
                <div className="flashcard-face flashcard-back">
                  <div>
                    {c.answer}
                    <div className="small muted" style={{ marginTop: 8 }}>
                      {c.difficulty}{c.source_pages?.length ? ` · page ${c.source_pages.join(', ')}` : ''}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
