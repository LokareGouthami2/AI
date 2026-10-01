// The "Assignment sheet" preset: unruled paper with header + margin line,
// name and ID on every page, page number top-right, hand-underlined headings.
import path from 'node:path';
import { expect, test } from '@playwright/test';
import { H, P, createDocWithContent } from './helpers.js';

const SHOTS = path.resolve(import.meta.dirname, '..', '..', 'screenshots');

test('assignment sheet preset renders header, top-right page numbers and heading rules', async ({ page, request }) => {
  const body = 'Globalization connects markets through trade, investment, technology and the movement of people across borders.';
  const blocks = [H(1, 'Assignment Answers'), H(2, 'Introduction'), P(body), P(''), H(2, 'Meaning of Globalization'), P(body)];
  const id = await createDocWithContent(request, blocks, 'Assignment');

  await page.goto(`/documents/${id}/render`);
  await page.getByTestId('preset-assignment').click();
  await page.getByTestId('header-name').fill('Test Student');
  await page.getByTestId('header-id').fill('ROLL-123');
  await expect(page.getByTestId('paper')).toHaveValue('assignment');
  await expect(page.getByTestId('page-numbers')).toHaveValue('top-right');
  await expect(page.getByTestId('underline-headings')).toHaveValue('yes');
  await expect(page.getByTestId('show-through')).toHaveValue('medium');

  // Settings are saved per document (the preset + typed header).
  await expect
    .poll(async () => (await (await request.get(`/api/documents/${id}/render-settings`)).json()).header_id, { timeout: 10_000 })
    .toBe('ROLL-123');
  const saved = await (await request.get(`/api/documents/${id}/render-settings`)).json();
  expect(saved).toMatchObject({ paper: 'assignment', style: 'student', ink: 'ballpoint', output: 'photo', header_name: 'Test Student', underline_headings: true, plain_headings: true, show_through: true, show_through_level: 'medium', pen_shadow: true });

  await page.getByTestId('update-preview').click();
  await expect(page.getByTestId('preview-page').first()).toBeVisible({ timeout: 60_000 });
  await page.getByTestId('render-generate').click();
  const link = page.getByTestId('render-download');
  await expect(link).toBeVisible({ timeout: 90_000 });
  const pdf = await (await request.get(await link.getAttribute('href'))).body();
  expect(pdf.subarray(0, 5).toString()).toBe('%PDF-');
  await page.screenshot({ path: path.join(SHOTS, '09-assignment-sheet.png'), fullPage: true });

  // Notebook preset puts the defaults back but keeps the typed name/ID.
  await page.getByTestId('preset-notes').click();
  await expect(page.getByTestId('paper')).toHaveValue('ruled');
  await expect(page.getByTestId('underline-headings')).toHaveValue('no');
  await expect(page.getByTestId('header-name')).toHaveValue('Test Student');
});
