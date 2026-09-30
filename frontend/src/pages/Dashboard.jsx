import { Link } from 'react-router-dom';
import { api } from '../services/api.js';
import { ErrorAlert, Spinner, StatusBadge, formatBytes, formatDate, useAsync } from '../components/ui.jsx';

export default function Dashboard() {
  const [{ loading, error, data }, setState] = useAsync(() => api.listDocuments(), []);

  async function remove(doc) {
    if (!window.confirm(`Delete “${doc.title}” and all its notes, versions and PDFs?`)) return;
    await api.deleteDocument(doc.id);
    setState((s) => ({ ...s, data: s.data.filter((d) => d.id !== doc.id) }));
  }

  return (
    <div className="page">
      <div className="page-title">
        <h1>Your documents</h1>
        <span className="grow" />
        <Link className="btn btn-primary" to="/upload">+ Upload</Link>
      </div>
      <ErrorAlert error={error} />
      {loading && <Spinner label="Loading…" />}
      {data && data.length === 0 && (
        <div className="card">
          <p>No documents yet.</p>
          <Link className="btn btn-primary" to="/upload">Upload your first document</Link>
        </div>
      )}
      {data && data.length > 0 && (
        <div className="card">
          <table className="table" data-testid="documents-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Pages</th>
                <th>Status</th>
                <th>Updated</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.id}>
                  <td>
                    <Link to={d.has_content ? `/documents/${d.id}/editor` : `/documents/${d.id}/analysis`}>{d.title}</Link>
                    <div className="small muted">{d.original_name} · {formatBytes(d.size_bytes)}</div>
                  </td>
                  <td>{d.kind.toUpperCase()}</td>
                  <td>{d.page_count}</td>
                  <td><StatusBadge status={d.status} /></td>
                  <td className="small">{formatDate(d.updated_at)}</td>
                  <td>
                    <button className="btn btn-sm btn-danger" onClick={() => remove(d)} aria-label={`Delete ${d.title}`}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
