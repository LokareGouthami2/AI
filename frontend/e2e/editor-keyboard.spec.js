/**
 * Real-browser editor behaviour: keyboard, clipboard, undo/redo, formatting,
 * autosave. Every test verifies the *saved server content*, i.e. what the
 * handwriting renderer will receive.
 */
import { expect, test } from '@playwright/test';
import { H, MOD, P, clickInto, createDocWithContent, openEditor, paragraphTexts, savedContent, selectText, waitSaved } from './helpers.js';

const BASE = [H(1, 'Machine Learning'), P('Machine learning is a branch of AI.'), P('It allows computers to learn from data.'), P('There are three major types.')];

test.describe('editor keyboard & clipboard', () => {
  let id;
  test.beforeEach(async ({ request }) => {
    id = await createDocWithContent(request, BASE);
  });

  test('Enter creates new paragraphs; Enter twice leaves a blank line', async ({ page, request }) => {
    const ed = await openEditor(page, id);
    await clickInto(page, ed, 'Machine learning is a branch of AI.');
    await page.keyboard.press('End');
    await page.keyboard.press('Enter');
    await page.keyboard.press('Enter');
    await page.keyboard.type('Typed after a blank line.');
    await waitSaved(page);
    const texts = paragraphTexts((await savedContent(request, id)).content);
    expect(texts).toEqual(['Machine Learning', 'Machine learning is a branch of AI.', '', 'Typed after a blank line.', 'It allows computers to learn from data.', 'There are three major types.']);
  });

  test('Ctrl+End / Ctrl+Home work in the Edit + Preview layout', async ({ page, request }) => {
    await page.goto(`/documents/${id}/editor`);
    const ed = page.getByTestId('editor-content');
    await page.getByTestId('mode-split').click();
    await clickInto(page, ed, 'It allows computers');
    await page.keyboard.press(`${MOD}+End`);
    await page.keyboard.type(' END');
    await page.keyboard.press(`${MOD}+Home`);
    await page.keyboard.type('START ');
    await waitSaved(page);
    const texts = paragraphTexts((await savedContent(request, id)).content);
    expect(texts[0]).toBe('START Machine Learning');
    expect(texts.at(-1)).toBe('There are three major types. END');
  });

  test('Shift+Enter inserts a line break inside the paragraph', async ({ page, request }) => {
    const ed = await openEditor(page, id);
    await clickInto(page, ed, 'There are three major types.');
    await page.keyboard.press('End');
    await page.keyboard.press('Shift+Enter');
    await page.keyboard.type('Same paragraph, new line.');
    await waitSaved(page);
    const content = (await savedContent(request, id)).content;
    const last = content.blocks.at(-1);
    expect(last.content.map((n) => n.type)).toEqual(['text', 'hard_break', 'text']);
  });

  test('Backspace and Delete merge paragraphs; Home/End/arrows move the cursor', async ({ page, request }) => {
    const ed = await openEditor(page, id);
    await clickInto(page, ed, 'It allows computers to learn from data.');
    await page.keyboard.press('Home');
    await page.keyboard.press('Backspace'); // merge into previous paragraph
    await page.keyboard.type(' ');
    await clickInto(page, ed, 'There are three major types.');
    await page.keyboard.press('End');
    await page.keyboard.press('ArrowLeft');
    await page.keyboard.type('!'); // before the final period
    await page.keyboard.press('Home');
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('Delete'); // deletes "h"
    await waitSaved(page);
    const texts = paragraphTexts((await savedContent(request, id)).content);
    expect(texts).toEqual(['Machine Learning', 'Machine learning is a branch of AI. It allows computers to learn from data.', 'Tere are three major types!.']);
  });

  test('Ctrl+A then typing replaces the whole document', async ({ page, request }) => {
    const ed = await openEditor(page, id);
    await ed.click();
    await page.keyboard.press(`${MOD}+a`);
    await page.keyboard.type('Completely new document.');
    await waitSaved(page);
    expect(paragraphTexts((await savedContent(request, id)).content)).toEqual(['Completely new document.']);
  });

  test('copy, cut and paste', async ({ page, request }) => {
    const ed = await openEditor(page, id);
    await selectText(page, 'three');
    await page.keyboard.press(`${MOD}+c`);
    await clickInto(page, ed, 'It allows computers to learn from data.');
    await page.keyboard.press('End');
    await page.keyboard.type(' ');
    await page.keyboard.press(`${MOD}+v`);
    // cut the first paragraph's text
    await ed.getByText('Machine learning is a branch of AI.').click({ clickCount: 3 });
    await page.keyboard.press(`${MOD}+x`);
    await waitSaved(page);
    const texts = paragraphTexts((await savedContent(request, id)).content);
    expect(texts).toContain('It allows computers to learn from data. three');
    expect(texts.join('|')).not.toContain('branch of AI');
  });

  test('undo and redo (keyboard and toolbar)', async ({ page, request }) => {
    const ed = await openEditor(page, id);
    await clickInto(page, ed, 'There are three major types.');
    await page.keyboard.press('End');
    await page.keyboard.type(' Extra sentence.');
    await expect(ed).toContainText('Extra sentence.');
    await page.keyboard.press(`${MOD}+z`);
    await expect(ed).not.toContainText('Extra sentence.');
    await page.keyboard.press(`${MOD}+y`);
    await expect(ed).toContainText('Extra sentence.');
    await page.getByTestId('tb-undo').click();
    await expect(ed).not.toContainText('Extra sentence.');
    await page.getByTestId('tb-redo').click();
    await expect(ed).toContainText('Extra sentence.');
    await page.keyboard.press(`${MOD}+Shift+z`); // nothing more to redo: no change
    await waitSaved(page);
    expect(paragraphTexts((await savedContent(request, id)).content).at(-1)).toBe('There are three major types. Extra sentence.');
  });

  test('toolbar formatting; underline only when chosen', async ({ page, request }) => {
    const ed = await openEditor(page, id);
    // Headings via toolbar
    await clickInto(page, ed, 'There are three major types.');
    await page.getByTestId('tb-h2').click();
    // Bold on one word, underline on another
    await selectText(page, 'branch');
    await page.getByTestId('tb-bold').click();
    await clickInto(page, ed, 'It allows computers to learn from data.');
    await page.keyboard.press('End');
    await page.keyboard.press('Shift+ArrowLeft');
    await page.keyboard.press('Shift+ArrowLeft');
    await page.keyboard.press('Shift+ArrowLeft');
    await page.keyboard.press('Shift+ArrowLeft');
    await page.keyboard.press('Shift+ArrowLeft');
    await page.getByTestId('tb-underline').click();
    // Lists and alignment
    await clickInto(page, ed, 'Machine learning is a branch of AI.');
    await page.getByTestId('tb-bullet').click();
    await clickInto(page, ed, 'It allows computers to learn from');
    await page.getByTestId('tb-center').click();
    await waitSaved(page);
    const c = (await savedContent(request, id)).content;
    expect(c.blocks[3]).toMatchObject({ type: 'heading', level: 2 });
    expect(c.blocks[1].type).toBe('bullet_list');
    expect(c.blocks[2].align).toBe('center');
    const all = JSON.stringify(c);
    const underlined = c.blocks[2].content.filter((n) => n.marks?.includes('underline')).map((n) => n.text);
    expect(underlined).toEqual(['data.']);
    expect((all.match(/underline/g) || []).length).toBe(1);
    expect(JSON.stringify(c.blocks[1])).toContain('"bold"');
  });

  test('pasting underlined web content does not bring underline in', async ({ page, request }) => {
    const ed = await openEditor(page, id);
    await clickInto(page, ed, 'There are three major types.');
    await page.keyboard.press('End');
    await page.evaluate(() => {
      const dt = new DataTransfer();
      dt.setData('text/html', '<p><u>Pasted underlined</u> and <mark>highlighted</mark> text</p>');
      dt.setData('text/plain', 'Pasted underlined and highlighted text');
      document.querySelector('.ProseMirror').dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
    });
    await expect(ed).toContainText('Pasted underlined');
    await waitSaved(page);
    const c = JSON.stringify((await savedContent(request, id)).content);
    expect(c).toContain('Pasted underlined');
    expect(c).not.toContain('underline"');
  });

  test('move blocks with Alt+Arrow', async ({ page, request }) => {
    const ed = await openEditor(page, id);
    await clickInto(page, ed, 'There are three major types.');
    await page.keyboard.press('Alt+ArrowUp');
    await waitSaved(page);
    // Poll: under load "✓ Saved" can still be showing from before the move.
    await expect
      .poll(async () => paragraphTexts((await savedContent(request, id)).content).slice(1))
      .toEqual(['Machine learning is a branch of AI.', 'There are three major types.', 'It allows computers to learn from data.']);
  });

  test('autosave debounces typing (no request per keystroke)', async ({ page }) => {
    const ed = await openEditor(page, id);
    let puts = 0;
    page.on('request', (r) => r.method() === 'PUT' && r.url().includes('/content') && puts++);
    await clickInto(page, ed, 'There are three major types.');
    await page.keyboard.press('End');
    await page.keyboard.type(' A fairly long sentence typed quickly.', { delay: 20 });
    await expect(page.getByTestId('save-status')).toHaveText('✓ Saved', { timeout: 10000 });
    expect(puts).toBeGreaterThanOrEqual(1);
    expect(puts).toBeLessThanOrEqual(2);
  });

  test('large edits: paste several paragraphs of text', async ({ page, request }) => {
    const ed = await openEditor(page, id);
    await clickInto(page, ed, 'There are three major types.');
    await page.keyboard.press('End');
    const html = Array.from({ length: 40 }, (_, i) => `<p>Pasted paragraph number ${i + 1} with some words.</p>`).join('');
    await page.evaluate((h) => {
      const dt = new DataTransfer();
      dt.setData('text/html', h);
      document.querySelector('.ProseMirror').dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
    }, html);
    await waitSaved(page);
    const texts = paragraphTexts((await savedContent(request, id)).content);
    // The first pasted paragraph joins the paragraph at the cursor (standard
    // editor behaviour); the other 39 become paragraphs of their own.
    expect(texts.filter((t) => t.includes('Pasted paragraph number')).length).toBe(40);
    expect(texts).toContain('There are three major types.Pasted paragraph number 1 with some words.');
  });
});
