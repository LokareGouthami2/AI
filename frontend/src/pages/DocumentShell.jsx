import { NavLink, Outlet, useParams } from 'react-router-dom';
import { api } from '../services/api.js';
import { ErrorAlert, StatusBadge, useAsync } from '../components/ui.jsx';

export default function DocumentShell() {
  const { id } = useParams();
  const [{ data: doc, error }] = useAsync(() => api.getDocument(id), [id]);
  const tab = (to, label) => (
    <NavLink to={`/documents/${id}/${to}`} className={({ isActive }) => (isActive ? 'active' : '')}>
      {label}
    </NavLink>
  );
  return (
    <div className="page page-wide">
      <ErrorAlert error={error} />
      <div className="page-title">
        <h1 data-testid="doc-heading">{doc ? doc.title : '…'}</h1>
        {doc && <StatusBadge status={doc.status} />}
        {doc && <span className="small muted">{doc.original_name} · {doc.page_count} page(s)</span>}
      </div>
      <nav className="tabs" aria-label="Document sections">
        {tab('analysis', 'Analysis & Generate')}
        {tab('editor', 'Editor')}
        {tab('study', 'Study')}
        {tab('render', 'Handwriting & Download')}
      </nav>
      <Outlet />
    </div>
  );
}
