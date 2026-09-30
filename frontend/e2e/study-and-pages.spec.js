/** Study mode, dashboard and handwriting page — plus README screenshots. */
import path from 'node:path';
import { expect, test } from '@playwright/test';

const SHOTS = path.resolve(import.meta.dirname, '..', '..', 'screenshots');

test('upload → analysis → study (ask, flashcards, quiz) → handwriting page', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Understand. Edit. Learn. Create.')).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, '01-landing.png') });

  await page.goto('/upload');
  await page.getByTestId('file-input').setInputFiles(path.join(import.meta.dirname, 'fixtures', 'ml_notes.pdf'));
  await page.waitForURL(/\/analysis$/, { timeout: 60_000 });
  await expect(page.getByTestId('segments-table')).toContainText('TITLE');
  await page.screenshot({ path: path.join(SHOTS, '02-analysis.png'), fullPage: false });
  const id = page.url().match(/documents\/([0-9a-f-]+)\//)[1];

  // Generate Smart Notes and show the editor with preview.
  await page.getByTestId('mode-radio-smart').check();
  await page.getByTestId('generate').click();
  await page.waitForURL(/\/editor$/);
  await page.getByTestId('update-preview').click();
  await expect(page.getByTestId('preview-page').first()).toBeVisible({ timeout: 60_000 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SHOTS, '03-editor-preview.png') });

  // Study: Ask your document (grounded answer with page citation)
  await page.goto(`/documents/${id}/study`);
  await page.getByTestId('ask-input').fill('What does unsupervised learning find?');
  await page.getByTestId('ask-submit').click();
  await expect(page.getByTestId('answer')).toContainText('unlabelled data');
  await expect(page.getByTestId('answer')).toContainText('Page');
  await page.getByTestId('ask-input').fill('Who won the 1966 World Cup?');
  await page.getByTestId('ask-submit').click();
  await expect(page.getByTestId('answer').nth(1)).toContainText("couldn't find this in the document");
  await page.screenshot({ path: path.join(SHOTS, '04-ask-your-document.png') });

  // Flashcards: generate, edit, save
  await page.getByRole('button', { name: 'Flashcards' }).click();
  await page.getByTestId('gen-flashcards').click();
  await expect(page.getByRole('button', { name: 'Flashcard 1' })).toBeVisible();
  await page.getByRole('button', { name: 'Flashcard 1' }).click();
  await page.screenshot({ path: path.join(SHOTS, '05-flashcards.png') });
  await page.getByTestId('edit-flashcards').click();
  await page.getByLabel('Answer').first().fill('My own edited answer.');
  await page.getByTestId('save-flashcards').click();
  await expect(page.getByText('✓ Saved')).toBeVisible();
  await expect(page.getByTestId('flashcards')).toContainText('My own edited answer.');

  // Quiz: generate, answer, edit
  await page.getByRole('button', { name: 'Quiz' }).click();
  await page.getByTestId('gen-quiz').click();
  const firstQuestion = page.getByTestId('quiz').locator('.card').first();
  await expect(firstQuestion).toBeVisible();
  await firstQuestion.locator('.quiz-option').first().click();
  await expect(page.getByText(/Score \d+ \/ 1/)).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, '06-quiz.png') });
  await page.getByTestId('edit-quiz').click();
  await page.getByLabel('Question 1').fill('An edited question?');
  await page.getByTestId('save-quiz').click();
  await expect(page.getByTestId('quiz')).toContainText('An edited question?');

  // Handwriting settings page: change style and ink, preview, generate
  await page.goto(`/documents/${id}/render`);
  await page.getByLabel('Handwriting style').selectOption('cursive');
  await page.getByLabel('Ink').selectOption('black');
  await page.getByTestId('update-preview').click();
  await expect(page.getByTestId('preview-page').first()).toBeVisible({ timeout: 60_000 });
  await page.getByTestId('render-generate').click();
  await expect(page.getByTestId('render-download')).toBeVisible({ timeout: 90_000 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SHOTS, '07-handwriting-settings.png') });

  // Dashboard lists the document
  await page.goto('/dashboard');
  await expect(page.getByTestId('documents-table')).toContainText('Introduction to Machine Learning');
  await page.screenshot({ path: path.join(SHOTS, '08-dashboard.png') });
});
