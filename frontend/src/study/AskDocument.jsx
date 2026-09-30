import { useState } from 'react';
import { api } from '../services/api.js';
import { ErrorAlert, Spinner } from '../components/ui.jsx';

export default function AskDocument({ docId }) {
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function ask(e) {
    e.preventDefault();
    const q = question.trim();
    if (q.length < 2) return;
    setBusy(true);
    setError(null);
    setMessages((m) => [...m, { role: 'user', text: q }]);
    setQuestion('');
    try {
      const res = await api.ask(docId, q);
      setMessages((m) => [...m, { role: 'bot', ...res }]);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack" data-testid="ask">
      <p className="small muted">Answers come only from this document, with the pages they were taken from. If the document doesn't say, WriteAI tells you so.</p>
      <div className="chat">
        {messages.map((m, i) =>
          m.role === 'user' ? (
            <div key={i} className="chat-msg user">{m.text}</div>
          ) : (
            <div key={i} className="chat-msg bot" data-testid="answer">
              {m.answer ? m.answer : <i>I couldn't find this in the document.</i>}
              {m.citations?.map((c) => (
                <div key={c.chunk_id} className="citation">
                  <b>Page {c.pages.join('–')}</b> {c.section && <span className="muted">· {c.section}</span>}
                  <div className="muted">“{c.excerpt.slice(0, 180)}{c.excerpt.length > 180 ? '…' : ''}”</div>
                </div>
              ))}
            </div>
          ),
        )}
        {busy && <Spinner label="Searching the document…" />}
      </div>
      <ErrorAlert error={error} />
      <form className="row" onSubmit={ask}>
        <input className="input grow" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask a question about this document…" maxLength={1000} aria-label="Question" data-testid="ask-input" />
        <button className="btn btn-primary" disabled={busy || question.trim().length < 2} data-testid="ask-submit">Ask</button>
      </form>
    </div>
  );
}
