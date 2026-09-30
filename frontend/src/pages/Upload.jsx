import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, waitForJob } from '../services/api.js';
import { ErrorAlert } from '../components/ui.jsx';

const MAX_MB = 20;
const ACCEPT = '.pdf,.docx,.txt';

export default function Upload() {
  const [drag, setDrag] = useState(false);
  const [steps, setSteps] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const input = useRef(null);
  const navigate = useNavigate();

  const mark = (name, state, note = '') => setSteps((s) => [...s.filter((x) => x.name !== name), { name, state, note }]);

  async function handle(file) {
    setError(null);
    setSteps([]);
    if (!file) return;
    if (!/\.(pdf|docx|txt)$/i.test(file.name)) return setError(new Error('Only PDF, DOCX and TXT files are supported.'));
    if (file.size > MAX_MB * 1024 * 1024) return setError(new Error(`Files must be under ${MAX_MB} MB.`));
    setBusy(true);
    try {
      mark('Upload', 'running');
      const doc = await api.upload(file);
      mark('Upload', 'done', `${doc.page_count} page(s)`);
      mark('Extract text / OCR', 'running');
      const ex = await waitForJob(await api.extract(doc.id));
      mark('Extract text / OCR', 'done', ex.result.ocr_pages?.length ? `OCR on ${ex.result.ocr_pages.length} page(s)` : `${ex.result.characters} characters`);
      mark('NLP + ML classification + index', 'running');
      const an = await waitForJob(await api.analyze(doc.id));
      mark('NLP + ML classification + index', 'done', `${an.result.segments} segments, ${an.result.chunks} chunks`);
      navigate(`/documents/${doc.id}/analysis`);
    } catch (e) {
      setError(e);
      setSteps((s) => s.map((x) => (x.state === 'running' ? { ...x, state: 'failed' } : x)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <div className="page-title">
        <h1>Upload a document</h1>
      </div>
      <div
        className={`dropzone ${drag ? 'drag' : ''}`}
        role="button"
        tabIndex={0}
        aria-label="Choose or drop a file"
        onClick={() => !busy && input.current?.click()}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          if (!busy) handle(e.dataTransfer.files[0]);
        }}
      >
        <p style={{ fontSize: 18, margin: 0 }}><b>Drop a PDF, DOCX or TXT file here</b></p>
        <p className="muted">or click to browse · up to {MAX_MB} MB · scanned PDFs are OCR'd</p>
        <input ref={input} type="file" accept={ACCEPT} hidden data-testid="file-input" onChange={(e) => handle(e.target.files[0])} />
      </div>
      <div style={{ marginTop: 20 }}>
        <ErrorAlert error={error} />
        <ul className="steps" data-testid="upload-steps">
          {steps.map((s) => (
            <li key={s.name}>
              {s.state === 'running' ? <span className="spinner" /> : s.state === 'done' ? <span className="badge badge-success">✓</span> : <span className="badge badge-danger">✗</span>}
              <span>{s.name}</span>
              <span className="small muted">{s.note}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
