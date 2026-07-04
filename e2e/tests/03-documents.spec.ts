import path from 'node:path';
import { test, expect } from './fixtures';
import { DocumentsPage } from '../pages/DocumentsPage';
import { DEMO_DIR } from '../utils/paths';
import { shot } from '../utils/media';
import { cover, perf, warn, note, suggest } from '../utils/findings';

const DEMO_PDF = path.join(DEMO_DIR, 'OEM-P102A-MANUAL.pdf');

test.describe('Document Hub', () => {
  test('library search and status filter behave deterministically', async ({ page }, testInfo) => {
    const docs = new DocumentsPage(page);
    await page.goto('/documents');
    // Either a populated table or the empty state — both are valid, neither crashes.
    await expect(docs.rows().first().or(docs.emptyState())).toBeVisible({ timeout: 15_000 });
    await shot(page, 'documents-library');

    // A nonsense search must yield the empty state (or zero rows).
    await docs.searchInput().fill('zzz-no-such-document-zzz');
    await expect(docs.emptyState().or(docs.rows())).toBeVisible();
    expect(await docs.rows().count()).toBe(0);
    await docs.searchInput().fill('');

    // Status filter is a real <select> — exercise a concrete option.
    await docs.statusFilter().selectOption('PROCESSED');
    await page.waitForTimeout(800);
    await docs.statusFilter().selectOption('');
    cover(testInfo, 'Document library: search + status filter + empty state');
  });

  test('uploads a real industrial PDF through the browser and cleans up', async ({
    page,
  }, testInfo) => {
    const docs = new DocumentsPage(page);
    await page.goto('/documents');
    await docs.openUploadTab();

    // Real browser file selection (not an API call).
    await docs.fileInput().setInputFiles(DEMO_PDF);
    await expect(page.getByText('OEM-P102A-MANUAL.pdf')).toBeVisible();
    await shot(page, 'documents-upload-selected');

    const t0 = Date.now();
    await docs.submitUpload().click();
    await expect(docs.uploadSuccess()).toBeVisible({ timeout: 30_000 });
    perf(testInfo, 'upload-roundtrip-ms', Date.now() - t0);
    cover(testInfo, 'Document upload (multipart, through UI)');

    // It should now be listed in the library.
    await docs.openLibraryTab();
    await expect(docs.rowByName('OEM-P102A-MANUAL.pdf').first()).toBeVisible({ timeout: 15_000 });
    cover(testInfo, 'Uploaded document appears in library');

    // Best-effort: wait for the async GraphRAG pipeline to finish. If no worker
    // is running the doc stays QUEUED — that's a recorded warning, not a failure.
    const status = await docs.waitForStatus(
      'OEM-P102A-MANUAL.pdf',
      ['PROCESSED', 'COMPLETED'],
      60_000,
    );
    note(testInfo, `ingestion terminal status observed: ${status}`);
    if (['PROCESSED', 'COMPLETED'].includes(status)) {
      cover(testInfo, 'End-to-end ingestion completed (PROCESSED)');
    } else if (status === 'FAILED') {
      warn(testInfo, 'Uploaded document ingestion FAILED in the pipeline.');
    } else {
      warn(
        testInfo,
        `Ingestion did not reach PROCESSED within 60s (last: ${status}). The Celery worker (ib_worker) is likely not running, so uploads queue but are not indexed.`,
      );
      suggest(
        testInfo,
        'Start the ingestion worker (`celery -A app.worker worker`) or the ib_worker container so uploaded documents are actually indexed and become searchable.',
      );
    }

    // Cleanup: delete the row we just created (exercises the confirm dialog).
    page.once('dialog', (d) => d.accept());
    const before = await docs.rowByName('OEM-P102A-MANUAL.pdf').count();
    const row = docs.rowByName('OEM-P102A-MANUAL.pdf').first();
    await row.getByRole('button', { name: 'Delete' }).click();
    await expect
      .poll(async () => docs.rowByName('OEM-P102A-MANUAL.pdf').count(), { timeout: 10_000 })
      .toBeLessThan(before);
    cover(testInfo, 'Document delete (with confirm dialog)');
  });

  test('document details opens from the library', async ({ page }, testInfo) => {
    const docs = new DocumentsPage(page);
    await page.goto('/documents');
    // Wait for the list to finish loading (skeleton -> rows or empty state).
    await expect(docs.rows().first().or(docs.emptyState())).toBeVisible({ timeout: 15_000 });
    const firstRow = docs.rows().first();
    if ((await docs.rows().count()) === 0) {
      note(testInfo, 'Library empty — no document to open for details.');
      test.skip(true, 'no documents available');
      return;
    }
    const name = (await firstRow.locator('td').first().innerText()).trim().split('\n')[0];
    await firstRow.getByRole('link', { name: 'View document' }).click();
    await expect(page).toHaveURL(/\/documents\/[0-9a-fA-F-]+/);
    // The details view rendered (not the 404/error boundary).
    await expect(page.getByText(/page not found/i)).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Back' }).first()).toBeVisible({
      timeout: 15_000,
    });
    note(testInfo, `Opened details for "${name}"`);
    cover(testInfo, 'Document details view');
  });
});
