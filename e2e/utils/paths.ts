import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url)); // e2e/utils

export const E2E_DIR = path.resolve(here, '..');
export const REPO_ROOT = path.resolve(E2E_DIR, '..');
export const REPORTS_DIR = path.join(REPO_ROOT, 'reports', 'e2e');
export const SCREENSHOTS_DIR = path.join(REPORTS_DIR, 'screenshots');
export const ARTIFACTS_DIR = path.join(REPORTS_DIR, 'artifacts');
export const HTML_REPORT_DIR = path.join(REPORTS_DIR, 'html-report');
export const RESULTS_JSON = path.join(REPORTS_DIR, 'results.json');
export const AUTH_FILE = path.join(E2E_DIR, '.auth', 'user.json');
export const DEMO_DIR = path.join(REPO_ROOT, 'demo_data');

export function ensureDirs(): void {
  for (const d of [REPORTS_DIR, SCREENSHOTS_DIR, path.dirname(AUTH_FILE)]) {
    fs.mkdirSync(d, { recursive: true });
  }
}
