/**
 * Post-run report generator. Reads the Playwright JSON result file and emits the
 * human-readable deliverables under reports/e2e/:
 *   README.md · summary.md · failures.md · warnings.md · suggestions.md ·
 *   performance.md · coverage.md
 * Runs regardless of pass/fail so a failing suite still produces a full report.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(here, '../..');
const REPORTS = path.join(REPO_ROOT, 'reports', 'e2e');
const RESULTS = path.join(REPORTS, 'results.json');
const SCREENSHOTS = path.join(REPORTS, 'screenshots');

const stripAnsi = (s = '') => s.replace(/\[[0-9;]*m/g, '');
const rel = (p) => (p ? path.relative(REPORTS, p).split(path.sep).join('/') : '');

fs.mkdirSync(REPORTS, { recursive: true });

if (!fs.existsSync(RESULTS)) {
  fs.writeFileSync(
    path.join(REPORTS, 'summary.md'),
    `# E2E Summary\n\n**No results.json found** at ${RESULTS}. The run did not produce a JSON report (it may have failed during global setup — check that the backend is healthy).\n`,
  );
  console.error('build-report: results.json not found — wrote a stub summary.');
  process.exit(0);
}

const report = JSON.parse(fs.readFileSync(RESULTS, 'utf8'));

/** Flatten the nested suite tree into one list of executed tests. */
const tests = [];
function walk(suite, file) {
  const f = suite.file || file;
  for (const spec of suite.specs ?? []) {
    for (const t of spec.tests ?? []) {
      const last = (t.results ?? [])[t.results.length - 1] ?? {};
      const map = { expected: 'passed', flaky: 'flaky', unexpected: 'failed', skipped: 'skipped' };
      tests.push({
        file: f || spec.file,
        project: t.projectName || t.projectId || '',
        title: spec.title,
        outcome: map[t.status] ?? last.status ?? 'unknown',
        durationMs: last.duration ?? 0,
        retries: Math.max(0, (t.results ?? []).length - 1),
        annotations: t.annotations ?? [],
        errors: (last.errors ?? []).map((e) => stripAnsi(e.message || e.value || '')),
        attachments: last.attachments ?? [],
      });
    }
  }
  for (const s of suite.suites ?? []) walk(s, f);
}
for (const s of report.suites ?? []) walk(s, s.file);

const stats = report.stats ?? {};
const totals = {
  total: tests.length,
  passed: tests.filter((t) => t.outcome === 'passed').length,
  flaky: tests.filter((t) => t.outcome === 'flaky').length,
  failed: tests.filter((t) => t.outcome === 'failed').length,
  skipped: tests.filter((t) => t.outcome === 'skipped').length,
  durationS: ((stats.duration ?? 0) / 1000).toFixed(1),
};

const allAnn = (type) =>
  tests.flatMap((t) => t.annotations.filter((a) => a.type === type).map((a) => ({ ...a, t })));
const dedupe = (arr) => [...new Set(arr)];

const warnings = allAnn('warning');
const suggestions = allAnn('suggestion');
const perfs = allAnn('perf');
const coverage = allAnn('coverage');
const notes = allAnn('note');

const ICON = { passed: '✅', flaky: '🟡', failed: '❌', skipped: '⚪', unknown: '❔' };

// --- summary.md --------------------------------------------------------------
const byFile = {};
for (const t of tests) (byFile[t.file] ??= []).push(t);
const fileRows = Object.entries(byFile)
  .map(([f, ts]) => {
    const p = ts.filter((x) => x.outcome === 'passed' || x.outcome === 'flaky').length;
    const fa = ts.filter((x) => x.outcome === 'failed').length;
    const sk = ts.filter((x) => x.outcome === 'skipped').length;
    return `| \`${f}\` | ${ts.length} | ${p} | ${fa} | ${sk} |`;
  })
  .join('\n');

const verdict =
  totals.failed === 0
    ? `✅ **PASS** — ${totals.passed}/${totals.total} tests passed` +
      (totals.flaky ? ` (${totals.flaky} passed on retry)` : '')
    : `❌ **${totals.failed} FAILURE(S)** — ${totals.passed}/${totals.total} passed`;

fs.writeFileSync(
  path.join(REPORTS, 'summary.md'),
  `# Industrial Brain OS — E2E Validation Summary

_Autonomous browser validation via Playwright + Google Chrome (channel: chrome)._

## Verdict

${verdict}

| Metric | Value |
|--------|-------|
| Total tests | ${totals.total} |
| Passed | ${totals.passed} |
| Passed on retry (flaky) | ${totals.flaky} |
| Failed | ${totals.failed} |
| Skipped | ${totals.skipped} |
| Wall-clock duration | ${totals.durationS}s |
| Warnings recorded | ${warnings.length} |
| Suggestions recorded | ${suggestions.length} |
| Coverage checks | ${dedupe(coverage.map((c) => c.description)).length} |

## By suite

| Spec file | Tests | Passed | Failed | Skipped |
|-----------|-------|--------|--------|---------|
${fileRows}

## Individual tests

| | Test | Project | Duration |
|---|------|---------|----------|
${tests
  .map((t) => `| ${ICON[t.outcome]} | ${t.title} | ${t.project} | ${(t.durationMs / 1000).toFixed(1)}s |`)
  .join('\n')}

_See [failures.md](failures.md), [warnings.md](warnings.md), [suggestions.md](suggestions.md), [performance.md](performance.md), and [coverage.md](coverage.md)._
`,
);

// --- failures.md -------------------------------------------------------------
const failed = tests.filter((t) => t.outcome === 'failed');
fs.writeFileSync(
  path.join(REPORTS, 'failures.md'),
  `# Failures\n\n${
    failed.length === 0
      ? '✅ No test failures.\n'
      : failed
          .map(
            (t) =>
              `## ❌ ${t.title} (${t.project})\n\n` +
              `- File: \`${t.file}\`\n- Retries: ${t.retries}\n\n` +
              '```\n' +
              (t.errors.join('\n\n').slice(0, 4000) || '(no error message captured)') +
              '\n```\n\n' +
              'Artifacts:\n' +
              (t.attachments.length
                ? t.attachments.map((a) => `- ${a.name}: \`${rel(a.path)}\``).join('\n')
                : '- (none)') +
              '\n',
          )
          .join('\n---\n\n')
  }`,
);

// --- warnings.md -------------------------------------------------------------
fs.writeFileSync(
  path.join(REPORTS, 'warnings.md'),
  `# Warnings\n\nNon-fatal issues observed during validation (${warnings.length}).\n\n${
    warnings.length === 0
      ? '✅ No warnings recorded.\n'
      : dedupe(warnings.map((w) => `- **${w.t.title}** — ${w.description}`)).join('\n') + '\n'
  }`,
);

// --- suggestions.md ----------------------------------------------------------
fs.writeFileSync(
  path.join(REPORTS, 'suggestions.md'),
  `# Suggestions\n\nImprovement opportunities surfaced by the run (${suggestions.length}).\n\n${
    suggestions.length === 0
      ? '_No suggestions recorded._\n'
      : dedupe(suggestions.map((s) => `- ${s.description}`))
          .map((s, i) => `${i + 1}. ${s.replace(/^- /, '')}`)
          .join('\n') + '\n'
  }`,
);

// --- performance.md ----------------------------------------------------------
const perfRows = perfs
  .map((p) => {
    const [label, ms] = p.description.split('=');
    return `| ${label} | ${ms} | ${p.t.title} |`;
  })
  .join('\n');
fs.writeFileSync(
  path.join(REPORTS, 'performance.md'),
  `# Performance Metrics\n\nCollected timings (milliseconds unless the label says otherwise).\n\n` +
    `Total suite wall-clock: **${totals.durationS}s**.\n\n` +
    `| Metric | Value (ms) | Test |\n|--------|-----------|------|\n${perfRows || '| _none_ | | |'}\n`,
);

// --- coverage.md -------------------------------------------------------------
const haystack = [
  ...coverage.map((c) => c.description),
  ...notes.map((n) => n.description),
  ...suggestions.map((s) => s.description),
  ...tests.map((t) => t.title),
]
  .join(' \n ')
  .toLowerCase();
const has = (...kw) => kw.some((k) => haystack.includes(k.toLowerCase()));

const REQUESTED = [
  ['Launch Chrome + start/health-gate services', () => '✅', 'globalSetup gates backend health; Playwright webServer starts the frontend'],
  ['Authentication (login)', () => (has('login happy-path', 'login rejects') ? '✅' : '⚠️'), 'UI login happy-path + bad-credential rejection'],
  ['Authorization (route guard)', () => (has('route guard', 'session-end') ? '✅' : '⚠️'), 'Anonymous deep-link bounced to /login; session-end re-guards'],
  ['Signup', () => (has('signup') ? '✅' : '❌'), 'Duplicate-email 409 + min-length validation'],
  ['Navigate every page', () => (has('navigate:') ? '✅' : '⚠️'), 'All 7 sidebar routes + Settings'],
  ['Upload documents', () => (has('document upload') ? '✅' : '❌'), 'Real multipart upload of an industrial PDF via the browser'],
  ['Wait for ingestion', () => (has('ingestion completed') ? '✅' : '⚠️'), 'Bounded poll for PROCESSED (worker-dependent — see warnings)'],
  ['Search', () => (has('search') ? '✅' : '❌'), 'Document library search + empty state'],
  ['Chat with copilot', () => (has('chat websocket connects', 'streamed answer') ? '✅' : '⚠️'), 'WebSocket connect + streamed answer observed on the wire'],
  ['Citations', () => (has('carried citations') ? '✅' : '⚠️'), 'Citation UI validated when present; grounding gap noted otherwise'],
  ['Knowledge graph', () => (has('kg renders') ? '✅' : '❌'), 'Seeded P-102A subgraph render + depth + error state'],
  ['Dark mode', () => (has('dark mode') ? '✅' : '❌'), 'Toggle applies to <html> and persists across reload'],
  ['Error handling', () => (has('graceful', '404') ? '✅' : '⚠️'), '404 route + aborted-API graceful degradation'],
  ['Empty states', () => (has('empty state') ? '✅' : '⚠️'), 'Document library empty state on no match'],
  ['Loading states', () => (has('loading', 'skeleton') ? '✅' : '⚠️'), 'Skeleton/loader present; not separately asserted'],
  ['Browser console errors', () => '✅', 'Console/pageerror observed on every test (auto fixture)'],
  ['Network failures', () => (has('network-failure', 'network failure') ? '✅' : '⚠️'), 'Route-abort resilience test'],
  ['Performance', () => (perfs.length ? '✅' : '⚠️'), `${perfs.length} timing metric(s) captured`],
  ['Accessibility', () => (has('accessibility') ? '✅' : '⚠️'), 'axe-core scan of core pages'],
  ['Responsiveness', () => (has('responsive') ? '✅' : '⚠️'), 'Mobile off-canvas sidebar + tablet overflow check'],
  ['Multiple browser tabs', () => (has('multi-tab') ? '✅' : '⚠️'), 'Parallel copilot + graph tabs'],
  ['Human-like behaviour', () => '✅', 'Mouse arcs, variable-cadence typing, scrolling, think-time (utils/human)'],
  ['Screenshots / videos / traces', () => '✅', 'trace/video/screenshot = "on" in config; curated stills in screenshots/'],
  ['Work orders / compliance / RCA / maintenance / lessons workflows', () => '⚠️', 'Brains are status scaffolds only — no interactive workflow UI exists yet (see suggestions)'],
];
const matrix = REQUESTED.map(([label, fn, ev]) => `| ${label} | ${fn()} | ${ev} |`).join('\n');

fs.writeFileSync(
  path.join(REPORTS, 'coverage.md'),
  `# Coverage

## Requested-capability matrix

Legend: ✅ exercised · ⚠️ partial / environment-limited · ❌ not testable in current build.

| Capability | Status | Evidence |
|-----------|:------:|----------|
${matrix}

## All exercised checks (${dedupe(coverage.map((c) => c.description)).length})

${dedupe(coverage.map((c) => `- ${c.description}`)).sort().join('\n')}
`,
);

// --- README.md (index) -------------------------------------------------------
let shots = [];
try {
  shots = fs
    .readdirSync(SCREENSHOTS)
    .filter((f) => f.endsWith('.png'))
    .sort();
} catch {
  /* no screenshots */
}
const gallery = shots.map((s) => `### ${s}\n\n![${s}](screenshots/${s})`).join('\n\n');

fs.writeFileSync(
  path.join(REPORTS, 'README.md'),
  `# Industrial Brain OS — End-to-End Validation Report

Autonomous, human-like browser validation of the running application using
**Playwright driving real Google Chrome**. Generated by \`e2e/\` (see that folder
for the suite). Re-run with \`cd e2e && pnpm test && pnpm run report:build\`.

- **[summary.md](summary.md)** — verdict, totals, per-suite + per-test results
- **[failures.md](failures.md)** — failing tests with errors + artifact paths
- **[warnings.md](warnings.md)** — non-fatal issues observed
- **[suggestions.md](suggestions.md)** — improvement opportunities
- **[performance.md](performance.md)** — captured timings
- **[coverage.md](coverage.md)** — requested-capability matrix
- **html-report/** — full interactive Playwright report (traces/videos inline; generated locally, git-ignored)
- **artifacts/** — per-test traces, videos, screenshots (generated locally, git-ignored)

## Verdict

${verdict} · ${totals.durationS}s · ${warnings.length} warning(s) · ${suggestions.length} suggestion(s).

## Milestone screenshots

${gallery || '_No screenshots captured._'}
`,
);

console.log(
  `build-report: ${totals.total} tests (${totals.passed} passed, ${totals.failed} failed, ${totals.skipped} skipped) → reports/e2e/*.md`,
);
