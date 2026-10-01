/** Thin fetch wrapper around the WriteAI REST API. No secrets live here:
 * the browser only ever talks to our backend. */

const BASE = import.meta.env.VITE_API_BASE || '';

export class ApiError extends Error {
  constructor(status, code, message, details = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function request(method, path, body, { raw = false, signal } = {}) {
  const headers = {};
  const token = import.meta.env.VITE_API_TOKEN;
  if (token) headers['X-API-Token'] = token;
  let payload;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(BASE + path, { method, headers, body: payload, signal });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new ApiError(0, 'NETWORK', 'Cannot reach the WriteAI server.');
  }
  if (raw) return res;
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = data?.error || {};
    // Site password set and not (or no longer) logged in: show the login page.
    if (res.status === 401 && err.code === 'UNAUTHORIZED') window.dispatchEvent(new Event('writeai:unauthorized'));
    throw new ApiError(res.status, err.code || 'HTTP_' + res.status, err.message || res.statusText, err.details || {});
  }
  return data;
}

export const api = {
  health: () => request('GET', '/api/health'),
  authStatus: () => request('GET', '/api/auth/status'),
  login: (password) => request('POST', '/api/auth/login', { password }),
  logout: () => request('POST', '/api/auth/logout'),
  listDocuments: () => request('GET', '/api/documents'),
  getDocument: (id) => request('GET', `/api/documents/${id}`),
  deleteDocument: (id) => request('DELETE', `/api/documents/${id}`),
  upload: (file) => {
    const fd = new FormData();
    fd.append('file', file);
    return request('POST', '/api/documents/upload', fd);
  },
  extract: (id) => request('POST', `/api/documents/${id}/extract`),
  analyze: (id) => request('POST', `/api/documents/${id}/analyze`),
  analysis: (id) => request('GET', `/api/documents/${id}/analysis`),
  generate: (id, mode) => request('POST', `/api/documents/${id}/generate`, { mode }),
  getContent: (id) => request('GET', `/api/documents/${id}/content`),
  saveContent: (id, content, baseRevision, force = false) =>
    request('PUT', `/api/documents/${id}/content`, { content, base_revision: baseRevision, force }),
  versions: (id) => request('GET', `/api/documents/${id}/versions`),
  createVersion: (id, label) => request('POST', `/api/documents/${id}/versions`, { label }),
  getVersion: (id, n) => request('GET', `/api/documents/${id}/versions/${n}`),
  restoreVersion: (id, n) => request('POST', `/api/documents/${id}/versions/${n}/restore`),
  styles: () => request('GET', '/api/handwriting/styles'),
  getRenderSettings: (id) => request('GET', `/api/documents/${id}/render-settings`),
  saveRenderSettings: (id, s) => request('PUT', `/api/documents/${id}/render-settings`, s),
  preview: (id, expectedRevision, settings) => request('POST', `/api/documents/${id}/preview`, { expected_revision: expectedRevision, settings }),
  validate: (id, expectedRevision, settings) => request('POST', `/api/documents/${id}/validate`, { expected_revision: expectedRevision, settings }),
  render: (id, expectedRevision, settings) => request('POST', `/api/documents/${id}/render`, { expected_revision: expectedRevision, settings }),
  ask: (id, question) => request('POST', `/api/documents/${id}/ask`, { question }),
  flashcards: (id, count) => request('POST', `/api/documents/${id}/flashcards`, { count }),
  latestFlashcards: (id) => request('GET', `/api/documents/${id}/flashcards`),
  saveFlashcards: (id, setId, cards) => request('PUT', `/api/documents/${id}/flashcards/${setId}`, { cards }),
  quiz: (id, count) => request('POST', `/api/documents/${id}/quiz`, { count }),
  latestQuiz: (id) => request('GET', `/api/documents/${id}/quiz`),
  saveQuiz: (id, quizId, questions) => request('PUT', `/api/documents/${id}/quiz/${quizId}`, { questions }),
  job: (jobId) => request('GET', `/api/jobs/${jobId}`),
};

export const apiUrl = (path) => BASE + path;

/** Poll a background job until it finishes. */
export async function waitForJob(job, { interval = 600, timeout = 300000, onProgress } = {}) {
  const started = Date.now();
  let current = job;
  while (current.status === 'queued' || current.status === 'running') {
    if (Date.now() - started > timeout) throw new ApiError(0, 'TIMEOUT', 'The operation is taking too long.');
    await new Promise((r) => setTimeout(r, interval));
    current = await api.job(job.id);
    onProgress?.(current);
  }
  if (current.status === 'failed') throw new ApiError(0, 'JOB_FAILED', current.error || 'The operation failed.');
  return current;
}
