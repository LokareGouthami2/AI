/**
 * Autosave controller (framework-free so it can be unit-tested with fake timers).
 *
 *   change() ─► status "unsaved" ─► debounce (1.5 s, max wait 10 s) ─► save
 *   flush()  ─► cancel debounce, save now, resolve with the saved revision
 *
 * Only one request is in flight at a time; edits made during a save trigger
 * another save afterwards. A 409 (edited elsewhere) stops autosave and asks
 * the user to reload or overwrite. Network errors retry with backoff and the
 * latest draft is kept in localStorage.
 */

export const DEBOUNCE_MS = 1500;
export const MAX_WAIT_MS = 10000;

export function createAutosave({ save, getContent, initialRevision, onStatus = () => {}, draftKey = null, debounceMs = DEBOUNCE_MS, maxWaitMs = MAX_WAIT_MS }) {
  let revision = initialRevision;
  let status = 'saved';
  let dirty = false;
  let timer = null;
  let firstChangeAt = null;
  let inFlight = null;
  let retryDelay = 1000;
  let conflict = null;
  let destroyed = false;
  const waiters = [];

  const setStatus = (s, extra = {}) => {
    status = s;
    onStatus({ status: s, revision, ...extra });
  };

  const storeDraft = (content) => {
    if (!draftKey) return;
    try {
      localStorage.setItem(draftKey, JSON.stringify({ content, baseRevision: revision, at: Date.now() }));
    } catch {
      /* storage may be unavailable */
    }
  };
  const clearDraft = () => {
    if (!draftKey) return;
    try {
      localStorage.removeItem(draftKey);
    } catch {
      /* ignore */
    }
  };

  function schedule() {
    clearTimeout(timer);
    const now = Date.now();
    const waitedLong = firstChangeAt !== null && now - firstChangeAt >= maxWaitMs;
    timer = setTimeout(run, waitedLong ? 0 : debounceMs);
  }

  async function run() {
    clearTimeout(timer);
    timer = null;
    if (destroyed || conflict) return;
    if (inFlight) {
      await inFlight; // never two saves at once: chain after the current one
      return run();
    }
    if (!dirty) {
      resolveWaiters();
      return;
    }
    dirty = false;
    firstChangeAt = null;
    const content = getContent();
    setStatus('saving');
    let failed = false;
    inFlight = save(content, revision).then(
      (res) => {
        revision = res.revision;
        retryDelay = 1000;
        clearDraft();
        if (!dirty) setStatus('saved', { contentHash: res.content_hash });
      },
      (e) => {
        failed = true;
        dirty = true;
        if (e.status === 409) {
          conflict = e;
          setStatus('conflict', { error: e });
        } else {
          storeDraft(content);
          setStatus('error', { error: e });
          timer = setTimeout(run, retryDelay);
          retryDelay = Math.min(retryDelay * 2, 30000);
        }
        rejectWaiters(e);
      },
    );
    await inFlight;
    inFlight = null;
    if (failed) return;
    if (dirty) {
      // Edits arrived during the save: honour a pending flush right away,
      // otherwise let the debounce timer (already scheduled) handle it.
      if (waiters.length) return run();
      return;
    }
    resolveWaiters();
  }

  function resolveWaiters() {
    while (waiters.length) waiters.shift().resolve(revision);
  }
  function rejectWaiters(e) {
    while (waiters.length) waiters.shift().reject(e);
  }

  return {
    change() {
      if (destroyed) return;
      dirty = true;
      if (firstChangeAt === null) firstChangeAt = Date.now();
      if (!conflict) setStatus('unsaved');
      schedule();
    },
    /** Save immediately; resolves with the server revision once everything is saved. */
    flush() {
      if (conflict) return Promise.reject(conflict);
      if (!dirty && !inFlight) return Promise.resolve(revision);
      const p = new Promise((resolve, reject) => waiters.push({ resolve, reject }));
      run();
      return p;
    },
    /** After a conflict: overwrite the server copy with ours. */
    async forceSave() {
      conflict = null;
      const content = getContent();
      setStatus('saving');
      const res = await save(content, revision, true);
      revision = res.revision;
      dirty = false;
      setStatus('saved');
      resolveWaiters();
      return revision;
    },
    setRevision(r) {
      revision = r;
      conflict = null;
      dirty = false;
      clearTimeout(timer);
      setStatus('saved');
    },
    get revision() {
      return revision;
    },
    get status() {
      return status;
    },
    get dirty() {
      return dirty || !!inFlight;
    },
    destroy() {
      destroyed = true;
      clearTimeout(timer);
    },
  };
}
