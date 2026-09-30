import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { EditorContent, useEditor } from '@tiptap/react';
import { Link, useParams } from 'react-router-dom';
import Toolbar from '../editor/Toolbar.jsx';
import VersionHistory from '../editor/VersionHistory.jsx';
import { editorExtensions } from '../editor/extensions/index.js';
import { createAutosave } from '../editor/autosave.js';
import { fromWdm, toWdm } from '../editor/wdm/convert.js';
import PreviewPane from '../preview/PreviewPane.jsx';
import { DEFAULT_SETTINGS } from '../preview/SettingsPanel.jsx';
import { api, apiUrl, waitForJob } from '../services/api.js';
import { ErrorAlert, QualityReport, Spinner } from '../components/ui.jsx';

const STATUS_TEXT = {
  saved: '✓ Saved',
  saving: 'Saving…',
  unsaved: 'Unsaved changes',
  error: 'Offline — retrying…',
  conflict: 'Edited elsewhere',
};

export default function EditorPage() {
  const { id } = useParams();
  const [head, setHead] = useState(null);
  const [loadError, setLoadError] = useState(null);

  useEffect(() => {
    let alive = true;
    api
      .getContent(id)
      .then((h) => alive && setHead(h))
      .catch((e) => alive && setLoadError(e));
    return () => {
      alive = false;
    };
  }, [id]);

  if (loadError) {
    return (
      <div className="stack">
        <ErrorAlert error={loadError} />
        {loadError.code === 'NO_CONTENT' && (
          <p>
            Generate notes first on the <Link to={`/documents/${id}/analysis`}>Analysis</Link> tab.
          </p>
        )}
      </div>
    );
  }
  if (!head) return <Spinner label="Loading document…" />;
  return <DocumentEditor key={id} docId={id} head={head} />;
}

function DocumentEditor({ docId, head }) {
  const [title, setTitle] = useState(head.content.title || 'Untitled');
  const titleRef = useRef(title);
  const [saveState, setSaveState] = useState({ status: 'saved', revision: head.revision });
  const [mode, setMode] = useState('split'); // edit | split | preview
  const [showHistory, setShowHistory] = useState(false);
  const [historyKey, setHistoryKey] = useState(0);
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [render, setRender] = useState({ busy: false, result: null, error: null });
  const autosaveRef = useRef(null);

  const editor = useEditor({
    extensions: editorExtensions(),
    content: fromWdm(head.content),
    editorProps: { attributes: { 'aria-label': 'Document editor', 'data-testid': 'editor-content', spellcheck: 'true' } },
    onUpdate: () => autosaveRef.current?.change(),
    immediatelyRender: true,
  });

  // Autosave controller — the editor state is the source of truth.
  useEffect(() => {
    if (!editor) return;
    const ctl = createAutosave({
      save: (content, rev, force) => api.saveContent(docId, content, rev, force),
      getContent: () => toWdm(editor.getJSON(), titleRef.current),
      initialRevision: head.revision,
      onStatus: setSaveState,
      draftKey: `writeai-draft-${docId}`,
    });
    autosaveRef.current = ctl;
    return () => {
      ctl.flush().catch(() => {});
      ctl.destroy();
    };
  }, [editor, docId, head.revision]);

  useEffect(() => {
    api.getRenderSettings(docId).then(setSettings).catch(() => {});
  }, [docId]);

  // Warn before leaving with unsaved edits; Ctrl/Cmd+S saves immediately.
  useEffect(() => {
    const beforeUnload = (e) => {
      if (autosaveRef.current?.dirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        autosaveRef.current?.flush().catch(() => {});
      }
    };
    window.addEventListener('beforeunload', beforeUnload);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('beforeunload', beforeUnload);
      window.removeEventListener('keydown', onKey);
    };
  }, []);

  const flush = useCallback(() => autosaveRef.current.flush(), []);

  function onTitle(e) {
    setTitle(e.target.value);
    titleRef.current = e.target.value;
    autosaveRef.current?.change();
  }

  function onRestored(newHead) {
    editor.commands.setContent(fromWdm(newHead.content), { emitUpdate: false });
    setTitle(newHead.content.title || 'Untitled');
    titleRef.current = newHead.content.title || 'Untitled';
    autosaveRef.current.setRevision(newHead.revision);
    setHistoryKey((k) => k + 1);
  }

  async function reloadFromServer() {
    const h = await api.getContent(docId);
    onRestored(h);
  }

  async function generatePdf() {
    setRender({ busy: true, result: null, error: null });
    try {
      const revision = await flush();
      await api.saveRenderSettings(docId, settings).catch(() => {});
      const job = await api.render(docId, revision, settings);
      const done = await waitForJob(job);
      setRender({ busy: false, result: done.result, error: null });
      setHistoryKey((k) => k + 1);
    } catch (e) {
      setRender({ busy: false, result: null, error: e });
    }
  }

  const status = saveState.status;
  const layoutClass = useMemo(() => ['editor-layout', mode === 'split' ? 'split' : '', showHistory ? 'with-history' : ''].join(' '), [mode, showHistory]);

  return (
    <div className="stack">
      <div className="row">
        <div className="segmented" role="group" aria-label="View mode">
          {['edit', 'split', 'preview'].map((m) => (
            <button key={m} aria-pressed={mode === m} onClick={() => setMode(m)} data-testid={`mode-${m}`}>
              {m === 'edit' ? 'Edit' : m === 'split' ? 'Edit + Preview' : 'Preview'}
            </button>
          ))}
        </div>
        <span className={`save-status ${status}`} data-testid="save-status" aria-live="polite">
          {status === 'saving' && <span className="spinner" aria-hidden="true" />}
          {STATUS_TEXT[status]}
        </span>
        <span className="small muted" data-testid="revision">rev {saveState.revision}</span>
        <span className="grow" />
        <button className="btn" onClick={() => flush().catch(() => {})} data-testid="save-now">Save</button>
        <button className="btn" onClick={() => setShowHistory((v) => !v)} aria-pressed={showHistory}>History</button>
        <button className="btn btn-primary" onClick={generatePdf} disabled={render.busy} data-testid="generate-pdf">
          {render.busy ? <Spinner /> : '⬇'} Generate Final PDF
        </button>
      </div>

      {status === 'conflict' && (
        <div className="alert alert-danger row">
          This document was changed in another tab or window.
          <button className="btn btn-sm" onClick={reloadFromServer}>Load their version</button>
          <button className="btn btn-sm" onClick={() => autosaveRef.current.forceSave()}>Keep mine (overwrite)</button>
        </div>
      )}
      <ErrorAlert error={render.error} />
      {render.result && (
        <div className="card stack" data-testid="render-result">
          <div className="row">
            <b>Final PDF — revision {render.result.revision}</b>
            {render.result.download_url && (
              <a className="btn btn-primary btn-sm" href={apiUrl(render.result.download_url)} data-testid="download-pdf">
                Download PDF
              </a>
            )}
          </div>
          <QualityReport report={render.result.quality} />
        </div>
      )}

      <div className={layoutClass}>
        {mode !== 'preview' && (
          <div className="editor-shell" data-testid="editor">
            <input className="doc-title-input" value={title} onChange={onTitle} aria-label="Document title" data-testid="doc-title" />
            <Toolbar editor={editor} />
            <EditorContent editor={editor} />
          </div>
        )}
        {mode !== 'edit' && (
          <PreviewPane docId={docId} flush={flush} settings={settings} currentRevision={saveState.revision} dirty={status !== 'saved'} />
        )}
        {showHistory && <VersionHistory docId={docId} flush={flush} onRestored={onRestored} refreshKey={historyKey} />}
      </div>
    </div>
  );
}
