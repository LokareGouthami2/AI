import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api, waitForJob } from '../services/api.js';
import { ErrorAlert, Spinner, useAsync } from '../components/ui.jsx';

const MODES = [
  ['preserve', 'Preserve', 'Keep the source text and structure exactly (no AI rewriting).'],
  ['clean', 'Clean Notes', 'Fix formatting and extraction artefacts.'],
  ['smart', 'Smart Notes', 'Structured study notes: key points, definitions, examples.'],
  ['assignment', 'Assignment', 'Title, introduction, objectives, content, examples, conclusion, references.'],
  ['exam', 'Exam Revision', 'Definitions, formulas, key concepts and likely questions.'],
  ['simple', 'Simple Explanation', 'Plain-language explanation of difficult content.'],
];

const LABEL_COLORS = {
  TITLE: 'badge-primary',
  HEADING: 'badge-primary',
  SUBHEADING: 'badge-primary',
  DEFINITION: 'badge-success',
  FORMULA: 'badge-warning',
  QUESTION: 'badge-warning',
  ANSWER: 'badge-success',
  IMPORTANT_POINT: 'badge-danger',
};

export default function Analysis() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [{ data, error, loading }] = useAsync(() => api.analysis(id), [id]);
  const [mode, setMode] = useState('smart');
  const [gen, setGen] = useState({ busy: false, error: null });

  async function generate() {
    setGen({ busy: true, error: null });
    try {
      const doc = await api.getDocument(id);
      if (doc.has_content && !window.confirm('Replace the current editable document? It will be kept in version history.')) {
        setGen({ busy: false, error: null });
        return;
      }
      await waitForJob(await api.generate(id, mode), { timeout: 600000 });
      navigate(`/documents/${id}/editor`);
    } catch (e) {
      setGen({ busy: false, error: e });
    }
  }

  if (loading) return <Spinner label="Loading analysis…" />;
  if (error) return <ErrorAlert error={error} />;
  const st = data.stats;
  return (
    <div className="stack">
      <div className="card">
        <div className="card-header"><h2>Generate an editable document</h2></div>
        <div className="grid-3" role="radiogroup" aria-label="AI mode">
          {MODES.map(([value, label, desc]) => (
            <label key={value} className="card" style={{ cursor: 'pointer', borderColor: mode === value ? 'var(--primary)' : undefined }}>
              <div className="row">
                <input type="radio" name="mode" value={value} checked={mode === value} onChange={() => setMode(value)} data-testid={`mode-radio-${value}`} />
                <b>{label}</b>
              </div>
              <div className="small muted">{desc}</div>
            </label>
          ))}
        </div>
        <div className="row" style={{ marginTop: 14 }}>
          <button className="btn btn-primary" onClick={generate} disabled={gen.busy} data-testid="generate">
            {gen.busy ? <Spinner /> : null} Generate & open editor
          </button>
          <span className="small muted">Nothing is rendered until you review and edit the result.</span>
        </div>
        <ErrorAlert error={gen.error} />
      </div>

      <div className="grid-3">
        <div className="card stat"><b>{st.words}</b><span>words</span></div>
        <div className="card stat"><b>{st.sentences}</b><span>sentences</span></div>
        <div className="card stat"><b>{st.reading_time_min} min</b><span>reading time</span></div>
        <div className="card stat"><b>{st.readability?.flesch_reading_ease ?? '–'}</b><span>Flesch reading ease</span></div>
        <div className="card stat"><b>{st.segments}</b><span>segments classified ({st.low_confidence_segments} by rules)</span></div>
        <div className="card stat"><b>{st.chunks}</b><span>RAG chunks indexed</span></div>
      </div>

      {st.injection_flags?.length > 0 && (
        <div className="alert alert-warning">
          <b>Heads-up:</b> this document contains text that looks like instructions to an AI. It is treated purely as document
          content and never followed.
        </div>
      )}
      {st.ocr_pages?.length > 0 && <div className="alert">OCR was used on page(s) {st.ocr_pages.join(', ')}.</div>}

      <div className="grid-2">
        <div className="card">
          <div className="card-header"><h2>Structure (ML classifier)</h2><span className="small muted">{st.classifier_version}</span></div>
          <div className="row">
            {Object.entries(st.label_distribution || {}).map(([k, v]) => (
              <span key={k} className={`badge ${LABEL_COLORS[k] || ''}`}>{k} · {v}</span>
            ))}
          </div>
        </div>
        <div className="card">
          <div className="card-header"><h2>Key phrases</h2></div>
          <div className="row">
            {(st.keyphrases || []).map((k) => <span key={k} className="badge">{k}</span>)}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h2>Classified segments</h2></div>
        <table className="table" data-testid="segments-table">
          <thead><tr><th>Page</th><th>Label</th><th>Confidence</th><th>Text</th></tr></thead>
          <tbody>
            {data.segments.slice(0, 300).map((s, i) => (
              <tr key={i}>
                <td>{s.page}</td>
                <td><span className={`badge ${LABEL_COLORS[s.label] || ''}`}>{s.label}</span>{s.source === 'rules' && <span className="small muted"> rule</span>}</td>
                <td>{(s.confidence * 100).toFixed(0)}%</td>
                <td className="small">{s.text}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
