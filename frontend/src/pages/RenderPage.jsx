import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import SettingsPanel, { DEFAULT_SETTINGS } from '../preview/SettingsPanel.jsx';
import PreviewPane from '../preview/PreviewPane.jsx';
import { api, apiUrl, waitForJob } from '../services/api.js';
import { ErrorAlert, QualityReport, Spinner } from '../components/ui.jsx';

/** Handwriting settings, preview and final download for the saved document. */
export default function RenderPage() {
  const { id } = useParams();
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [head, setHead] = useState(null);
  const [error, setError] = useState(null);
  const [render, setRender] = useState({ busy: false, result: null, error: null });

  useEffect(() => {
    api.getRenderSettings(id).then(setSettings).catch(() => {});
    api.getContent(id).then(setHead).catch(setError);
  }, [id]);

  // The editor autosaves; here the latest saved revision is the source of truth.
  const latestRevision = async () => {
    const h = await api.getContent(id);
    setHead(h);
    return h.revision;
  };

  async function saveSettings(next) {
    setSettings(next);
    api.saveRenderSettings(id, next).catch(() => {});
  }

  async function generate() {
    setRender({ busy: true, result: null, error: null });
    try {
      const rev = await latestRevision();
      const done = await waitForJob(await api.render(id, rev, settings));
      setRender({ busy: false, result: done.result, error: null });
    } catch (e) {
      setRender({ busy: false, result: null, error: e });
    }
  }

  if (error?.code === 'NO_CONTENT') {
    return <p>Generate notes first on the <Link to={`/documents/${id}/analysis`}>Analysis</Link> tab.</p>;
  }
  return (
    <div className="stack">
      <ErrorAlert error={error} />
      <div className="card">
        <div className="card-header"><h2>Handwriting settings</h2></div>
        <SettingsPanel settings={settings} onChange={saveSettings} />
      </div>
      <div className="card stack">
        <div className="row">
          <button className="btn btn-primary" onClick={generate} disabled={render.busy} data-testid="render-generate">
            {render.busy ? <Spinner /> : '⬇'} Generate Final PDF
          </button>
          {head && <span className="small muted">Uses the latest saved edits (revision {head.revision}).</span>}
        </div>
        <ErrorAlert error={render.error} />
        {render.result && (
          <>
            {render.result.download_url ? (
              <a className="btn btn-primary" href={apiUrl(render.result.download_url)} data-testid="render-download">
                Download handwritten PDF ({render.result.page_count} pages)
              </a>
            ) : (
              <div className="alert alert-danger">The PDF was not produced because quality checks failed.</div>
            )}
            <QualityReport report={render.result.quality} />
          </>
        )}
      </div>
      <PreviewPane docId={id} flush={latestRevision} settings={settings} currentRevision={head?.revision} dirty={false} />
    </div>
  );
}
