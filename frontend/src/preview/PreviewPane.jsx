import { useState } from 'react';
import { api, apiUrl } from '../services/api.js';
import { ErrorAlert, QualityReport, Spinner } from '../components/ui.jsx';

/**
 * Handwritten preview. Rendering is explicit ("Update Preview"): the editor's
 * pending edits are flushed first and the preview is pinned to that exact
 * revision, so it can never show stale content.
 */
export default function PreviewPane({ docId, flush, settings, currentRevision, dirty }) {
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function update() {
    setLoading(true);
    setError(null);
    try {
      let revision = await flush();
      let res;
      try {
        res = await api.preview(docId, revision, settings);
      } catch (e) {
        if (e.code !== 'STALE_REVISION') throw e;
        revision = await flush(); // someone saved in between: flush and retry once
        res = await api.preview(docId, revision, settings);
      }
      setPreview(res);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }

  const stale = preview && (preview.revision !== currentRevision || dirty);
  return (
    <div className="preview-pane" data-testid="preview-pane">
      <div className="row">
        <button className="btn btn-primary" onClick={update} disabled={loading} data-testid="update-preview">
          {loading ? <Spinner /> : '⟳'} Update Preview
        </button>
        {preview && <span className="small muted">revision {preview.revision} · {preview.page_count} page(s)</span>}
      </div>
      {stale && <div className="stale-banner">The document changed since this preview — press Update Preview.</div>}
      <ErrorAlert error={error} />
      {preview && <QualityReport report={preview.quality} compact />}
      {!preview && !loading && <div className="preview-empty">Press <b>Update Preview</b> to see the handwritten pages.</div>}
      {preview && (
        <div className="preview-pages">
          {preview.pages.map((p) => (
            <img key={p.url} src={apiUrl(p.url)} alt={`Handwritten page ${p.number}`} loading="lazy" data-testid="preview-page" />
          ))}
        </div>
      )}
    </div>
  );
}
