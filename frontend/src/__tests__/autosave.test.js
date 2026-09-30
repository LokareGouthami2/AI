import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createAutosave } from '../editor/autosave.js';

function setup(saveImpl) {
  const statuses = [];
  let content = { v: 0 };
  const save = vi.fn(saveImpl || (async (c, rev) => ({ revision: rev + 1, content_hash: 'h' + c.v })));
  const ctl = createAutosave({ save, getContent: () => content, initialRevision: 1, onStatus: (s) => statuses.push(s.status) });
  return { ctl, save, statuses, setContent: (c) => (content = c) };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('autosave', () => {
  it('debounces keystrokes into one request', async () => {
    const { ctl, save, setContent } = setup();
    for (let i = 1; i <= 20; i++) {
      setContent({ v: i });
      ctl.change();
      await vi.advanceTimersByTimeAsync(100);
    }
    expect(save).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1600);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0][0]).toEqual({ v: 20 });
    expect(ctl.revision).toBe(2);
    expect(ctl.status).toBe('saved');
  });

  it('saves at least every max-wait interval during continuous typing', async () => {
    const { ctl, save } = setup();
    for (let i = 0; i < 120; i++) {
      ctl.change();
      await vi.advanceTimersByTimeAsync(100);
    }
    expect(save.mock.calls.length).toBeGreaterThanOrEqual(1);
  });

  it('flush saves immediately and resolves with the new revision', async () => {
    const { ctl, save, setContent } = setup();
    setContent({ v: 7 });
    ctl.change();
    const rev = await ctl.flush();
    expect(rev).toBe(2);
    expect(save).toHaveBeenCalledTimes(1);
    expect(await ctl.flush()).toBe(2); // nothing pending → no request
    expect(save).toHaveBeenCalledTimes(1);
  });

  it('edits made during a save are saved afterwards (latest content wins)', async () => {
    let release;
    const { ctl, save, setContent } = setup(
      (c, rev) => new Promise((r) => (release = () => r({ revision: rev + 1 }))),
    );
    setContent({ v: 1 });
    ctl.change();
    const p = ctl.flush();
    await vi.advanceTimersByTimeAsync(0);
    setContent({ v: 2 });
    ctl.change();
    release();
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(0);
    release?.();
    const rev = await p;
    expect(save.mock.calls.map((c) => c[0].v)).toEqual([1, 2]);
    expect(rev).toBe(3);
  });

  it('conflict (409) stops autosave and rejects flush', async () => {
    const err = Object.assign(new Error('stale'), { status: 409 });
    const { ctl, statuses } = setup(async () => {
      throw err;
    });
    ctl.change();
    await expect(ctl.flush()).rejects.toBe(err);
    expect(statuses.at(-1)).toBe('conflict');
    await expect(ctl.flush()).rejects.toBe(err);
  });

  it('network errors retry with backoff', async () => {
    let fail = true;
    const { ctl, save, statuses } = setup(async (c, rev) => {
      if (fail) throw Object.assign(new Error('offline'), { status: 0 });
      return { revision: rev + 1 };
    });
    ctl.change();
    await expect(ctl.flush()).rejects.toThrow('offline');
    expect(statuses).toContain('error');
    fail = false;
    await vi.advanceTimersByTimeAsync(1100);
    expect(save).toHaveBeenCalledTimes(2);
    expect(ctl.status).toBe('saved');
  });
});
