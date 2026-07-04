import { Page, TestInfo } from '@playwright/test';

/**
 * Passive page observer — attaches to console, page errors, failed requests, and
 * 5xx responses the moment a page is created, so nothing is missed. Known,
 * harmless dev-time noise is filtered so the signal in the report stays real.
 */

const IGNORE_PATTERNS: RegExp[] = [
  /React Router Future Flag/i,
  /Download the React DevTools/i,
  /favicon\.ico/i,
  /\[vite\] connect/i,
  /Failed to load resource: the server responded with a status of 404.*favicon/i,
];

const isNoise = (text: string): boolean => IGNORE_PATTERNS.some((re) => re.test(text));

export interface Observed {
  consoleErrors: string[];
  consoleWarnings: string[];
  pageErrors: string[];
  failedRequests: string[];
  serverErrors: string[];
}

export function observe(page: Page): Observed {
  const o: Observed = {
    consoleErrors: [],
    consoleWarnings: [],
    pageErrors: [],
    failedRequests: [],
    serverErrors: [],
  };

  page.on('console', (msg) => {
    const text = msg.text();
    if (isNoise(text)) return;
    if (msg.type() === 'error') o.consoleErrors.push(text);
    else if (msg.type() === 'warning') o.consoleWarnings.push(text);
  });

  page.on('pageerror', (err) => {
    if (!isNoise(err.message)) o.pageErrors.push(err.message);
  });

  page.on('requestfailed', (req) => {
    const err = req.failure()?.errorText ?? 'unknown';
    // Aborted requests are usually intentional (test-driven route.abort) — skip.
    if (err.includes('ERR_ABORTED')) return;
    const line = `${req.method()} ${req.url()} — ${err}`;
    if (!isNoise(line)) o.failedRequests.push(line);
  });

  page.on('response', (res) => {
    if (res.status() >= 500) o.serverErrors.push(`${res.status()} ${res.request().method()} ${res.url()}`);
  });

  return o;
}

/** Attach the collected signals to the test result and return a compact digest. */
export async function attachObserved(testInfo: TestInfo, o: Observed): Promise<void> {
  const body =
    `CONSOLE ERRORS (${o.consoleErrors.length}):\n${o.consoleErrors.join('\n') || '(none)'}\n\n` +
    `PAGE ERRORS (${o.pageErrors.length}):\n${o.pageErrors.join('\n') || '(none)'}\n\n` +
    `FAILED REQUESTS (${o.failedRequests.length}):\n${o.failedRequests.join('\n') || '(none)'}\n\n` +
    `5xx RESPONSES (${o.serverErrors.length}):\n${o.serverErrors.join('\n') || '(none)'}\n`;
  await testInfo.attach('browser-signals', { body, contentType: 'text/plain' });
}
