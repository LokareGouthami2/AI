import { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api.js';
import { ErrorAlert, formatDate } from '../components/ui.jsx';

const SOURCE_LABEL = {
  ai_generated: 'AI generated',
  manual_save: 'Saved version',
  checkpoint: 'Autosave checkpoint',
  pre_restore: 'Before restore',
  restored: 'Restored',
  pre_render: 'Rendered to PDF',
};

export default function VersionHistory({ docId, flush, onRestored, refreshKey }) {
  const [versions, setVersions] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [label, setLabel] = useState('');
  const [diff, setDiff] = useState(null);

  const load = useCallback(() => api.versions(docId).then(setVersions).catch(setError), [docId]);
  useEffect(() => {
    load();
  }, [load, refreshKey]);

  async function saveVersion() {
    setBusy(true);
    try {
      await flush();
      await api.createVersion(docId, label || 'Saved version');
      setLabel('');
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function restore(n) {
    if (!window.confirm(`Restore version ${n}? Your current text is kept as a version first.`)) return;
    setBusy(true);
    try {
      await flush().catch(() => {});
      const head = await api.restoreVersion(docId, n);
      onRestored(head);
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function compare(n) {
    try {
      await flush().catch(() => {});
      const v = await api.getVersion(docId, n);
      setDiff({ n, ...v.diff_to_current });
    } catch (e) {
      setError(e);
    }
  }

  return (
    <aside className="card" data-testid="version-history">
      <div className="card-header">
        <h2>Version history</h2>
      </div>
      <div className="row" style={{ marginBottom: 10 }}>
        <input className="input grow" placeholder="Version label (optional)" value={label} onChange={(e) => setLabel(e.target.value)} />
        <button className="btn btn-sm" onClick={saveVersion} disabled={busy} data-testid="save-version">Save version</button>
      </div>
      <ErrorAlert error={error} />
      <ul className="version-list">
        {versions.map((v) => (
          <li key={v.version_number}>
            <div className="row">
              <b>Version {v.version_number}</b>
              <span className="badge">{SOURCE_LABEL[v.source] || v.source}</span>
            </div>
            <div className="muted">{v.label} · {formatDate(v.created_at)}</div>
            <div className="row" style={{ marginTop: 4 }}>
              <button className="btn btn-sm" onClick={() => compare(v.version_number)}>Compare</button>
              <button className="btn btn-sm" onClick={() => restore(v.version_number)} disabled={busy} data-testid={`restore-${v.version_number}`}>Restore</button>
            </div>
            {diff && diff.n === v.version_number && (
              <div className="small muted" style={{ marginTop: 4 }}>
                vs current: +{diff.added} / −{diff.removed} block(s)
                {diff.changes.slice(0, 4).map((c, i) => (
                  <div key={i}>
                    {c.op}: {(c.old[0] || c.new[0] || '').slice(0, 60)}
                  </div>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </aside>
  );
}
