import { Link } from 'react-router-dom';

const FEATURES = [
  ['Document AI', 'PDF, DOCX and TXT extraction with OCR for scanned pages, cleaned by an NLP pipeline.'],
  ['ML structure detection', 'A trained classifier labels titles, headings, definitions, formulas, questions and more.'],
  ['Six AI modes', 'Preserve, Clean Notes, Smart Notes, Assignment, Exam Revision and Simple Explanation.'],
  ['A real editor', 'Rich-text editing with undo/redo, lists, headings and autosave. You control every word.'],
  ['Ask your document', 'Hybrid retrieval (BM25 + embeddings) with answers grounded in cited pages.'],
  ['Handwritten PDFs', 'A deterministic layout engine and handwriting renderer with automatic quality checks.'],
];

export default function Landing() {
  return (
    <div>
      <section className="hero">
        <div className="tagline">Understand. Edit. Learn. Create.</div>
        <h1>Turn study documents into notes you can edit — and write out by hand.</h1>
        <p>
          WriteAI reads your documents, structures them with machine learning, drafts study notes with an LLM, and lets you
          edit everything before rendering a handwriting-style PDF that exactly matches your final text.
        </p>
        <div className="row" style={{ justifyContent: 'center' }}>
          <Link className="btn btn-primary" to="/upload">Upload a document</Link>
          <Link className="btn" to="/dashboard">Open dashboard</Link>
        </div>
        <div className="pipeline" aria-label="Pipeline">
          {['Upload', 'Extract / OCR', 'NLP', 'ML classification', 'LLM notes', 'Your edits', 'Layout engine', 'Quality check', 'PDF'].map((s) => (
            <span key={s}>{s}</span>
          ))}
        </div>
      </section>
      <section className="page">
        <div className="grid-3">
          {FEATURES.map(([t, d]) => (
            <div key={t} className="card feature">
              <h3>{t}</h3>
              <p className="muted">{d}</p>
            </div>
          ))}
        </div>
        <p className="small muted" style={{ marginTop: 24 }}>
          Intended for personal study notes. Generated pages carry a small “Generated with WriteAI” footer by default —
          please don't submit computer-generated handwriting as your own.
        </p>
      </section>
    </div>
  );
}
