import { Page, Locator } from '@playwright/test';

/** Document Hub — Library (list/search/filter) + Upload (drag-drop / browse). */
export class DocumentsPage {
  constructor(private readonly page: Page) {}

  libraryTab(): Locator {
    return this.page.getByRole('button', { name: 'Library' });
  }
  uploadTab(): Locator {
    return this.page.getByRole('button', { name: 'Upload' }).first();
  }

  // --- Library ---------------------------------------------------------------
  searchInput(): Locator {
    return this.page.getByLabel('Search documents');
  }
  statusFilter(): Locator {
    return this.page.getByLabel('Filter by status');
  }
  refreshButton(): Locator {
    return this.page.getByRole('button', { name: 'Refresh' });
  }
  emptyState(): Locator {
    return this.page.getByText('No documents found');
  }
  rows(): Locator {
    return this.page.locator('table tbody tr');
  }
  rowByName(name: string): Locator {
    return this.page.locator('tbody tr', { hasText: name });
  }
  viewButton(): Locator {
    return this.page.getByRole('link', { name: 'View document' });
  }

  // --- Upload ----------------------------------------------------------------
  fileInput(): Locator {
    return this.page.locator('input[type="file"]');
  }
  /** The gradient submit button (last "Upload" in DOM — the tab is first). */
  submitUpload(): Locator {
    return this.page.getByRole('button', { name: /^Upload$|^Uploading/ }).last();
  }
  uploadSuccess(): Locator {
    return this.page.getByText(/uploaded and queued for processing/i);
  }

  async openUploadTab(): Promise<void> {
    await this.uploadTab().click();
  }
  async openLibraryTab(): Promise<void> {
    await this.libraryTab().click();
  }

  /**
   * Poll the library (via the app's own list endpoint through the page context)
   * for a document reaching a terminal-processed state. Returns the last observed
   * status; caller decides whether a non-processed result is a warning.
   */
  async waitForStatus(
    name: string,
    target: string[],
    timeoutMs: number,
  ): Promise<string> {
    const deadline = Date.now() + timeoutMs;
    let last = 'UNKNOWN';
    while (Date.now() < deadline) {
      await this.refreshButton().click().catch(() => {});
      const row = this.rowByName(name).first();
      if (await row.count()) {
        const text = (await row.innerText()).toUpperCase();
        for (const t of [...target, 'FAILED']) {
          if (text.includes(t)) {
            last = t;
            if (target.includes(t) || t === 'FAILED') return t;
          }
        }
      }
      await this.page.waitForTimeout(3000);
    }
    return last;
  }
}
