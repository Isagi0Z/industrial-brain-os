import { test, expect } from './fixtures';
import { AppShell } from '../pages/AppShell';
import { shot } from '../utils/media';
import { cover, note, suggest } from '../utils/findings';

const BRAINS = [
  { nav: 'Maintenance', heading: /maintenance brain/i, endpoint: '/maintenance/status' },
  { nav: 'Compliance', heading: /compliance brain/i, endpoint: '/compliance/status' },
  { nav: 'Root Cause', heading: /root cause analysis brain/i, endpoint: '/rca/status' },
  { nav: 'Lessons Learned', heading: /lessons learned brain/i, endpoint: '/lessons-learned/status' },
];

test.describe('Intelligence Brains', () => {
  for (const b of BRAINS) {
    test(`${b.nav} brain panel reports live service health`, async ({ page }, testInfo) => {
      const shell = new AppShell(page);
      await page.goto('/knowledge');
      await shell.goto(b.nav);
      await expect(page.getByRole('heading', { name: b.heading }).first()).toBeVisible();
      await expect(page.getByText('Online').first()).toBeVisible({ timeout: 15_000 });
      await expect(page.getByText(`/api/v1${b.endpoint}`)).toBeVisible();
      await expect(page.getByText(/"scaffold": true/)).toBeVisible();
      cover(testInfo, `Brain panel online: ${b.nav}`);
      if (b.nav === 'Maintenance') await shot(page, 'brain-maintenance');
    });
  }

  test('brains are status scaffolds — interactive workflows not yet built', async ({}, testInfo) => {
    note(
      testInfo,
      'All four intelligence brains expose a live status endpoint and render an Online panel, but they are scaffolds: there is no interactive work-order generation, compliance analysis, RCA, or lessons-learned workflow UI behind them.',
    );
    suggest(
      testInfo,
      'Several requested validations (generate work orders, run compliance/RCA/maintenance/lessons analyses through the browser) cannot be exercised because those flows are status scaffolds only. Wiring at least one brain to a real interactive endpoint would make the vertical demonstrable end-to-end.',
    );
    cover(testInfo, 'Brains capability-gap documented');
  });
});
