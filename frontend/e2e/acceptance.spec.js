/**
 * CRITICAL ACCEPTANCE TEST (design §12.4 / requirement §30), end to end in a
 * real browser against the real backend:
 *
 *  1 upload PDF · 2 Smart Notes · 3 open editor · 4 delete a paragraph ·
 *  5 Enter twice · 6 new paragraph · 7 heading · 8 modify sentences ·
 *  9 undo · 10 redo · 11 save · 12 preview · 13 final PDF · 14 verify PDF
 */
import path from 'node:path';
import { expect, test } from '@playwright/test';
import { MOD, inspectPdf, savedContent, selectText } from './helpers.js';

test('critical acceptance: edits in the editor are exactly what the handwritten PDF contains', async ({ page, request }) => {
  // 1. Upload a PDF
  await page.goto('/upload');
  await page.getByTestId('file-input').setInputFiles(path.join(import.meta.dirname, 'fixtures', 'ml_notes.pdf'));
  await page.waitForURL(/\/documents\/[0-9a-f-]+\/analysis/, { timeout: 60_000 });
  const id = page.url().match(/documents\/([0-9a-f-]+)\//)[1];

  // 2. Generate Smart Notes
  await page.getByTestId('mode-radio-smart').check();
  await page.getByTestId('generate').click();

  // 3. Open the editable document
  await page.waitForURL(/\/editor$/, { timeout: 60_000 });
  const ed = page.getByTestId('editor-content');
  await expect(ed).toBeVisible();
  await page.getByTestId('mode-edit').click();

  // 4. Delete an entire paragraph (the "Example: …" paragraph)
  const victim = ed.locator('p', { hasText: 'Example: Predicting whether an email is spam' });
  await expect(victim).toHaveCount(1);
  const deletedText = (await victim.innerText()).trim();
  await victim.click({ clickCount: 3 });
  await page.keyboard.press('Backspace'); // remove the text
  await page.keyboard.press('Backspace'); // remove the now-empty paragraph
  await expect(ed.locator('p', { hasText: 'Predicting whether an email' })).toHaveCount(0);

  // 5. Press Enter twice (at the end of the document)
  await ed.click();
  await page.keyboard.press(`${MOD}+End`);
  await page.keyboard.press('Enter');
  await page.keyboard.press('Enter');

  // 6. Add a new paragraph
  const NEW_PARA = 'This paragraph was typed by the student after pressing Enter twice.';
  await page.keyboard.type(NEW_PARA);

  // 7. Add a heading
  await page.keyboard.press('Enter');
  await page.getByTestId('tb-h2').click();
  await page.keyboard.type('My Own Heading');
  await page.keyboard.press('Enter');
  await page.keyboard.type('Text under my heading.');

  // 8. Modify several sentences
  await selectText(page, 'quantity');
  await page.keyboard.type('precision-edited');
  await selectText(page, 'used to train it.');
  await page.keyboard.press('ArrowRight'); // collapse the selection at the end of the sentence
  await page.keyboard.type(' Always keep a held-out test set.');
  await expect(ed).toContainText('Always keep a held-out test set.');

  // 9. Undo (removes the last typed sentence) …
  await page.keyboard.press(`${MOD}+z`);
  await expect(ed).not.toContainText('Always keep a held-out test set.');
  // 10. … and Redo (brings it back)
  await page.keyboard.press(`${MOD}+y`);
  await expect(ed).toContainText('Always keep a held-out test set.');

  // 11. Save
  await page.getByTestId('save-now').click();
  await expect(page.getByTestId('save-status')).toHaveText('✓ Saved');
  const head = await savedContent(request, id);

  // 12. Open Preview
  await page.getByTestId('mode-split').click();
  await page.getByTestId('update-preview').click();
  await expect(page.getByTestId('preview-page').first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId('preview-pane')).toContainText(`revision ${head.revision}`);

  // 13. Generate the handwritten PDF
  await page.getByTestId('generate-pdf').click();
  const link = page.getByTestId('download-pdf');
  await expect(link).toBeVisible({ timeout: 90_000 });
  await expect(page.getByTestId('render-result')).toContainText(`revision ${head.revision}`);
  const pdf = await (await request.get(await link.getAttribute('href'))).body();

  // 14. Verify the PDF
  const info = inspectPdf(pdf);
  const text = info.lines.map((l) => l.text).join(' ');
  expect(text, 'deleted paragraph is absent').not.toContain(deletedText.slice(0, 40));
  expect(text, 'new paragraph exists').toContain(NEW_PARA);
  expect(text, 'heading exists').toContain('My Own Heading');
  expect(text, 'modified sentence present').toContain('precision-edited');
  expect(text, 'redone edit present').toContain('Always keep a held-out test set.');
  const heading = info.lines.find((l) => l.text === 'My Own Heading');
  const body = info.lines.find((l) => l.text.startsWith('Text under my heading'));
  expect(heading.size, 'heading visually larger').toBeGreaterThan(body.size * 1.1);
  // extra line break preserved: blank grid line above the new paragraph
  const newLine = info.lines.find((l) => l.text.startsWith('This paragraph was typed'));
  const above = info.lines.filter((l) => l.page === newLine.page && l.y < newLine.y);
  if (above.length) {
    const gap = newLine.y - Math.max(...above.map((l) => l.y));
    expect(gap, 'blank line preserved').toBeGreaterThanOrEqual(2 * 16 * 1.6 - 1);
  }
  expect(info.underlines, 'no unexpected underline').toBe(0);
  expect(info.keywords, 'PDF rendered from the latest editor state').toContain(`writeai:content_hash=${head.content_hash}`);
  await expect(page.getByTestId('render-result').getByTestId('quality-report')).toContainText('Quality checks passed');
});
