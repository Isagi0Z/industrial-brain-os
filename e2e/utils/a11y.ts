import { Page, TestInfo } from '@playwright/test';
import { warn, note } from './findings';

/**
 * Accessibility scan via axe-core. Imported dynamically so a missing/failed
 * install degrades to a recorded warning instead of breaking the whole suite.
 * Returns the number of critical/serious violations (0 when axe is unavailable).
 */
export async function scanA11y(page: Page, testInfo: TestInfo, label: string): Promise<number> {
  let AxeBuilder: typeof import('@axe-core/playwright').default;
  try {
    ({ default: AxeBuilder } = await import('@axe-core/playwright'));
  } catch {
    note(testInfo, `a11y[${label}]: axe-core unavailable — scan skipped`);
    return 0;
  }

  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();

  const serious = results.violations.filter(
    (v) => v.impact === 'critical' || v.impact === 'serious',
  );

  const digest = results.violations
    .map((v) => `[${v.impact}] ${v.id}: ${v.help} (${v.nodes.length} node(s))`)
    .join('\n');
  await testInfo.attach(`a11y-${label}`, {
    body: digest || '(no violations)',
    contentType: 'text/plain',
  });

  if (serious.length > 0) {
    warn(
      testInfo,
      `a11y[${label}]: ${serious.length} serious/critical violation(s) — ${serious
        .map((v) => v.id)
        .join(', ')}`,
    );
  }
  note(testInfo, `a11y[${label}]: ${results.violations.length} total violation(s), ${serious.length} serious+`);
  return serious.length;
}
