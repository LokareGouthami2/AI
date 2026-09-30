import { useEffect, useState } from 'react';
import { api } from '../services/api.js';
import { ErrorAlert, Spinner } from '../components/ui.jsx';

export default function Quiz({ docId }) {
  const [quiz, setQuiz] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.latestQuiz(docId).then((q) => q && (setQuiz(q), setQuestions(q.questions))).catch(() => {});
  }, [docId]);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const q = await api.quiz(docId, 8);
      setQuiz(q);
      setQuestions(q.questions);
      setAnswers({});
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const q = await api.saveQuiz(docId, quiz.id, questions);
      setQuestions(q.questions);
      setEditing(false);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const upd = (i, patch) => setQuestions((qs) => qs.map((q, j) => (j === i ? { ...q, ...patch } : q)));
  const score = Object.entries(answers).filter(([i, a]) => questions[i]?.correct_index === a).length;

  return (
    <div className="stack" data-testid="quiz">
      <div className="row">
        <button className="btn btn-primary" onClick={generate} disabled={busy} data-testid="gen-quiz">
          {busy && !editing ? <Spinner /> : null} {quiz ? 'Regenerate' : 'Generate'} quiz
        </button>
        {quiz && !editing && <button className="btn" onClick={() => setEditing(true)} data-testid="edit-quiz">Edit questions</button>}
        {editing && (
          <>
            <button className="btn btn-primary" onClick={save} disabled={busy} data-testid="save-quiz">Save questions</button>
            <button className="btn btn-ghost" onClick={() => (setQuestions(quiz.questions), setEditing(false))}>Cancel</button>
          </>
        )}
        {!editing && Object.keys(answers).length > 0 && (
          <span className="badge badge-primary">Score {score} / {Object.keys(answers).length}</span>
        )}
      </div>
      <ErrorAlert error={error} />
      {quiz && questions.length === 0 && <p className="muted">No quiz questions could be generated (the document needs more definitions or key terms).</p>}
      {questions.map((q, i) => (
        <div key={i} className="card">
          {editing ? (
            <div className="stack">
              <label className="field"><span>Question {i + 1}</span><textarea className="textarea" value={q.question} onChange={(e) => upd(i, { question: e.target.value })} /></label>
              {q.options.map((o, k) => (
                <div key={k} className="row">
                  <input type="radio" name={`correct-${i}`} checked={q.correct_index === k} onChange={() => upd(i, { correct_index: k })} aria-label={`Option ${k + 1} is correct`} />
                  <input className="input grow" value={o} onChange={(e) => upd(i, { options: q.options.map((x, m) => (m === k ? e.target.value : x)) })} aria-label={`Option ${k + 1}`} />
                </div>
              ))}
              <label className="field"><span>Explanation</span><input className="input" value={q.explanation} onChange={(e) => upd(i, { explanation: e.target.value })} /></label>
              <button className="btn btn-sm btn-danger" onClick={() => setQuestions((qs) => qs.filter((_, j) => j !== i))}>Remove question</button>
            </div>
          ) : (
            <>
              <p><b>{i + 1}. {q.question}</b></p>
              {q.options.map((o, k) => {
                const chosen = answers[i];
                const cls = chosen === undefined ? '' : k === q.correct_index ? 'correct' : k === chosen ? 'wrong' : '';
                return (
                  <label key={k} className={`quiz-option ${cls}`}>
                    <input type="radio" name={`q-${i}`} disabled={chosen !== undefined} checked={chosen === k} onChange={() => setAnswers((a) => ({ ...a, [i]: k }))} />
                    <span>{o}</span>
                  </label>
                );
              })}
              {answers[i] !== undefined && (
                <p className="small muted">{q.explanation} {q.source_pages?.length ? `(page ${q.source_pages.join(', ')})` : ''} · {q.difficulty}</p>
              )}
            </>
          )}
        </div>
      ))}
    </div>
  );
}
