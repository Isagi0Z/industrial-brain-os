import { TestInfo } from '@playwright/test';

/**
 * Structured findings are pushed onto the test's annotations and later harvested
 * by scripts/build-report.mjs from results.json into the markdown reports. Using
 * annotations (rather than console logs) keeps findings machine-readable and
 * attached to the exact test that produced them.
 */

export const warn = (t: TestInfo, message: string): void => {
  t.annotations.push({ type: 'warning', description: message });
};

export const suggest = (t: TestInfo, message: string): void => {
  t.annotations.push({ type: 'suggestion', description: message });
};

export const perf = (t: TestInfo, label: string, ms: number): void => {
  t.annotations.push({ type: 'perf', description: `${label}=${Math.round(ms)}` });
};

export const cover = (t: TestInfo, feature: string): void => {
  t.annotations.push({ type: 'coverage', description: feature });
};

export const note = (t: TestInfo, message: string): void => {
  t.annotations.push({ type: 'note', description: message });
};
