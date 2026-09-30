import { NavLink, Navigate, Route, Routes, Link } from 'react-router-dom';
import Landing from './pages/Landing.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Upload from './pages/Upload.jsx';
import DocumentShell from './pages/DocumentShell.jsx';
import Analysis from './pages/Analysis.jsx';
import EditorPage from './pages/EditorPage.jsx';
import Study from './pages/Study.jsx';
import RenderPage from './pages/RenderPage.jsx';

export default function App() {
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
            <Route path="editor" element={<EditorPage />} />
            <Route path="study" element={<Study />} />
            <Route path="render" element={<RenderPage />} />
          </Route>
          <Route path="*" element={<div className="page"><h1>Not found</h1><Link to="/">Home</Link></div>} />
        </Routes>
      </main>
    </>
  );
}
