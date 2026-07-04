import { Page } from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs';
import { SCREENSHOTS_DIR } from './paths';

/**
 * Curated milestone screenshots for the human-readable report. Per-test videos,
 * traces, and failure screenshots are captured automatically by the Playwright
 * config; these named stills are the ones embedded in reports/e2e/*.md.
 */
let counter = 0;

export async function shot(page: Page, name: string, fullPage = false): Promise<string> {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  counter += 1;
  const slug = name.replace(/[^a-z0-9-]+/gi, '-').toLowerCase();
  const file = path.join(SCREENSHOTS_DIR, `${String(counter).padStart(2, '0')}-${slug}.png`);
  await page.screenshot({ path: file, fullPage });
  return file;
}
