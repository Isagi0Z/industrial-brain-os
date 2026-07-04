import { defineConfig } from '@playwright/test';
import { BASE_URL, PORT } from './utils/config';
import {
  ARTIFACTS_DIR,
  AUTH_FILE,
  HTML_REPORT_DIR,
  RESULTS_JSON,
  REPO_ROOT,
} from './utils/paths';
import path from 'node:path';

/**
 * Autonomous E2E validation — real Google Chrome (channel: 'chrome'), single
 * worker so the run behaves like one human operator, full trace/video/screenshot
 * capture, and one retry so a flaky step is retried before being recorded as a
 * failure. The frontend is started on a deterministic port via `webServer`
 * (reused if already running); backend health is gated in global-setup.
 */
export default defineConfig({
  testDir: './tests',
  outputDir: ARTIFACTS_DIR,
  fullyParallel: false,
  workers: 1,
  forbidOnly: false,
  retries: 1,
  timeout: 90_000,
  expect: { timeout: 12_000 },
  globalSetup: './global-setup.ts',

  reporter: [
    ['list'],
    ['html', { outputFolder: HTML_REPORT_DIR, open: 'never' }],
    ['json', { outputFile: RESULTS_JSON }],
  ],

  use: {
    baseURL: BASE_URL,
    channel: 'chrome',
    headless: process.env.E2E_HEADED ? false : true,
    viewport: { width: 1440, height: 900 },
    trace: 'on',
    video: 'on',
    screenshot: 'on',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },

  projects: [
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    {
      name: 'guest',
      testMatch: /01-auth\.spec\.ts/,
      use: { storageState: { cookies: [], origins: [] } },
    },
    {
      name: 'app',
      testMatch: /\.spec\.ts$/,
      testIgnore: /01-auth\.spec\.ts/,
      dependencies: ['setup'],
      use: { storageState: AUTH_FILE },
    },
  ],

  webServer: {
    command: `pnpm exec vite --port ${PORT} --strictPort --host 127.0.0.1`,
    cwd: path.join(REPO_ROOT, 'frontend'),
    url: BASE_URL,
    reuseExistingServer: true,
    timeout: 180_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
});
