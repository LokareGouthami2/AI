import { useEffect, useState } from 'react';

export function Spinner({ label }) {
  return (
    <span className="row small muted" role="status">
      <span className="spinner" aria-hidden="true" />
      {label}
    </span>
  );
}

export function ErrorAlert({ error }) {
  if (!error) return null;
  return (
    <div className="alert alert-danger" role="alert">
      {error.message || String(error)}
    </div>
  );
}

const STATUS_BADGE = {
  uploaded: 'badge',
  extracting: 'badge badge-primary',
  extracted: 'badge badge-primary',
  analyzing: 'badge badge-primary',
  analyzed: 'badge badge-primary',
  generating: 'badge badge-primary',
  ready: 'badge badge-success',
  failed: 'badge badge-danger',
};

export function StatusBadge({ status }) {
  return <span className={STATUS_BADGE[status] || 'badge'}>{status}</span>;
}

export function QualityReport({ report, compact = false }) {
  if (!report) return null;
  const audit = report.pdf_audit;
  const errors = [...(report.errors || []), ...((audit && audit.errors) || [])];
  const warnings = [...(report.warnings || []), ...((audit && audit.warnings) || [])];
  const passed = report.passed && (!audit || audit.passed);
  return (
    <div className="stack" data-testid="quality-report">
      <div className="row">
        <span className={passed ? 'badge badge-success' : 'badge badge-danger'}>{passed ? '✓ Quality checks passed' : '✗ Quality checks failed'}</span>
        {report.metrics && (
          <span className="small muted">
            {report.metrics.pages} page(s) · {report.metrics.lines} lines · {report.metrics.blank_lines} blank line(s) · min {report.metrics.min_font_size}pt · contrast {report.metrics.contrast_ratio}:1
          </span>
        )}
      </div>
      {errors.map((e, i) => (
        <div key={'e' + i} className="alert alert-danger small">
          <b>{e.code}</b> {e.message} {e.page ? `(page ${e.page})` : ''}
        </div>
      ))}
      {!compact &&
        warnings.map((w, i) => (
          <div key={'w' + i} className="alert alert-warning small">
            <b>{w.code}</b> {w.message}
          </div>
        ))}
      {!compact && report.checks && <div className="small muted">Checks: {report.checks.join(', ')}{audit ? ', ' + audit.checks.join(', ') : ''}</div>}
    </div>
  );
}

export function useAsync(fn, deps) {
  const [state, setState] = useState({ loading: true, error: null, data: null });
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    fn()
      .then((data) => alive && setState({ loading: false, error: null, data }))
      .catch((error) => alive && setState({ loading: false, error, data: null }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return [state, setState];
}

export function formatDate(s) {
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
}

export function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
