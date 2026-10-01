import { expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export const MOD = process.platform === 'darwin' ? 'Meta' : 'Control';

async function waitJob(request, job) {
  let j = job;
  for (let i = 0; i < 300 && (j.status === 'queued' || j.status === 'running'); i++) {
    await new Promise((r) => setTimeout(r, 300));
    j = await (await request.get(`/api/jobs/${job.id}`)).json();
  }
  expect(j.status, JSON.stringify(j)).toBe('succeeded');
  return j;
}

/** Create a document with known editable content through the API. */
export async function createDocWithContent(request, blocks, title = 'E2E document') {
  const res = await request.post('/api/documents/upload', {
    multipart: { file: { name: 'seed.txt', mimeType: 'text/plain', buffer: Buffer.from('Seed heading\n\nSeed paragraph with enough words to analyse.\n') } },
  });
  expect(res.status()).toBe(201);
  const doc = await res.json();
  await waitJob(request, await (await request.post(`/api/documents/${doc.id}/extract`)).json());
  await waitJob(request, await (await request.post(`/api/documents/${doc.id}/analyze`)).json());
  await waitJob(request, await (await request.post(`/api/documents/${doc.id}/generate`, { data: { mode: 'preserve' } })).json());
  const head = await (await request.get(`/api/documents/${doc.id}/content`)).json();
  const put = await request.put(`/api/documents/${doc.id}/content`, { data: { content: { schema_version: 1, title, blocks }, base_revision: head.revision } });
  expect(put.status()).toBe(200);
  return doc.id;
}

export const P = (text) => ({ type: 'paragraph', content: text ? [{ type: 'text', text }] : [] });
export const H = (level, text) => ({ type: 'heading', level, content: [{ type: 'text', text }] });

export async function openEditor(page, id) {
  await page.goto(`/documents/${id}/editor`);
  const editor = page.getByTestId('editor-content');
  await expect(editor).toBeVisible();
  await page.getByTestId('mode-edit').click();
  return editor;
}

/**
 * Click into a piece of editor text and make sure the cursor really landed in
 * that block. Right after the editor mounts, its content can still be loading,
 * and a click then would leave the cursor at the start of the document.
 */
export async function clickInto(page, ed, text) {
  await expect(async () => {
    await ed.getByText(text).first().click();
    const block = await page.evaluate(() => {
      const n = window.getSelection()?.anchorNode;
      const el = n?.nodeType === 3 ? n.parentElement : n;
      return el?.closest('p, h1, h2, h3, li, blockquote')?.textContent ?? '';
    });
    expect(block).toContain(text);
  }).toPass({ timeout: 10_000 });
}

export async function waitSaved(page) {
  // Wait for the save request itself: right after typing, the status label
  // can still show the previous "✓ Saved" for a render.
  const put = page
    .waitForResponse((r) => r.request().method() === 'PUT' && new URL(r.url()).pathname.endsWith('/content'), { timeout: 5_000 })
    .catch(() => null); // nothing pending (autosave already saved it)
  await page.getByTestId('save-now').click();
  await put;
  await expect(page.getByTestId('save-status')).toHaveText('✓ Saved');
}

export async function savedContent(request, id) {
  return (await request.get(`/api/documents/${id}/content`)).json();
}

export function paragraphTexts(content) {
  const out = [];
  const walk = (blocks) => {
    for (const b of blocks) {
      if (b.type === 'paragraph' || b.type === 'heading') out.push((b.content || []).map((n) => (n.type === 'hard_break' ? '\n' : n.text)).join(''));
      else if (b.items) b.items.forEach((it) => walk(it.blocks));
      else if (b.blocks) walk(b.blocks);
    }
  };
  walk(content.blocks);
  return out;
}

/** Inspect a PDF with the backend's own inspector (python -m backend.quality.pdf_inspect). */
export function inspectPdf(buffer) {
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'writeai-pdf-')), 'out.pdf');
  fs.writeFileSync(file, buffer);
  const out = execFileSync(process.env.WRITEAI_E2E_PYTHON, ['-m', 'backend.quality.pdf_inspect', file], { cwd: process.env.WRITEAI_E2E_ROOT });
  return JSON.parse(out.toString());
}

/** Select an exact piece of text in the editor (like a precise mouse drag). */
export async function selectText(page, text, occurrence = 0) {
  const ok = await page.evaluate(
    ([t, occ]) => {
      const root = document.querySelector('.ProseMirror');
      root.focus();
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      let n;
      let seen = 0;
      while ((n = walker.nextNode())) {
        let i = n.data.indexOf(t);
        while (i >= 0) {
          if (seen++ === occ) {
            const r = document.createRange();
            r.setStart(n, i);
            r.setEnd(n, i + t.length);
            const s = window.getSelection();
            s.removeAllRanges();
            s.addRange(r);
            return true;
          }
          i = n.data.indexOf(t, i + 1);
        }
      }
      return false;
    },
    [text, occurrence],
  );
  if (!ok) throw new Error(`text not found in editor: ${text}`);
  await page.waitForTimeout(50); // let ProseMirror read the DOM selection
}
