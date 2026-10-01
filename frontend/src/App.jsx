import { Suspense, lazy, useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes, Link } from 'react-router-dom';
import Landing from './pages/Landing.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Upload from './pages/Upload.jsx';
import DocumentShell from './pages/DocumentShell.jsx';
import Analysis from './pages/Analysis.jsx';
import Study from './pages/Study.jsx';
import RenderPage from './pages/RenderPage.jsx';
import { Spinner } from './components/ui.jsx';
import { api } from './services/api.js';

// The editor (TipTap/ProseMirror) is the heaviest chunk: load it on demand.
const EditorPage = lazy(() => import('./pages/EditorPage.jsx'));

/** Shown when the site is published with a password (WRITEAI_API_TOKEN). */
function Login({ onDone }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(password);
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main>
      <form className="page card stack login" onSubmit={submit} data-testid="login">
        <h1>WriteAI</h1>
        <p className="muted">This site is private. Enter the password to continue.</p>
        <label className="field">
          <span>Password</span>
          <input className="input" type="password" autoFocus autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <div className="alert alert-danger" role="alert">{error}</div>}
        <button className="btn btn-primary" type="submit" disabled={busy || !password}>{busy ? <Spinner /> : 'Log in'}</button>
      </form>
    </main>
  );
}

export default function App() {
  const [auth, setAuth] = useState('checking'); // checking | login | ok
  useEffect(() => {
    api.authStatus()
      .then((s) => setAuth(s.password_required && !s.logged_in ? 'login' : 'ok'))
      .catch(() => setAuth('ok')); // older server without auth endpoints
    const onUnauthorized = () => setAuth('login');
    window.addEventListener('writeai:unauthorized', onUnauthorized);
    return () => window.removeEventListener('writeai:unauthorized', onUnauthorized);
  }, []);
  if (auth === 'checking') return <Spinner label="Loading…" />;
  if (auth === 'login') return <Login onDone={() => setAuth('ok')} />;
  return (
    <>
      <header className="app-header">
        <Link to="/" className="brand">
          <span className="brand-mark">W</span> WriteAI <span className="badge badge-primary">2.0</span>
        </Link>
        <nav className="app-nav" aria-label="Main">
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/upload">Upload</NavLink>
        </nav>
        <span className="header-spacer" />
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/documents/:id" element={<DocumentShell />}>
            <Route index element={<Navigate to="analysis" replace />} />
            <Route path="analysis" element={<Analysis />} />
            <Route path="editor" element={<Suspense fallback={<Spinner label="Loading editor…" />}><EditorPage /></Suspense>} />
            <Route path="study" element={<Study />} />
            <Route path="render" element={<RenderPage />} />
          </Route>
          <Route path="*" element={<div className="page"><h1>Not found</h1><Link to="/">Home</Link></div>} />
        </Routes>
      </main>
    </>
  );
}
