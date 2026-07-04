import { test, expect } from './fixtures';
import { AppShell, NAV } from '../pages/AppShell';
import * as human from '../utils/human';
import { cover, perf, warn, note } from '../utils/findings';

/** Expected page heading for each sidebar destination. */
const HEADING: Record<string, RegExp> = {
  'Document Hub': /document hub/i,
  'Knowledge Copilot': /knowledge copilot/i,
  'Knowledge Graph': /knowledge graph/i,
  Maintenance: /maintenance brain/i,
  Compliance: /compliance brain/i,
  'Root Cause': /root cause analysis brain/i,
  'Lessons Learned': /lessons learned brain/i,
};

test.describe('Navigation & App Shell', () => {
  test('every sidebar route loads its page', async ({ page }, testInfo) => {
    const shell = new AppShell(page);
    await page.goto('/knowledge');
    await expect(shell.themeToggle()).toBeVisible();

    for (const name of Object.keys(NAV)) {
      const t0 = Date.now();
      await shell.goto(name);
      await expect(page).toHaveURL(new RegExp(NAV[name].replace(/\//g, '\\/')));
      await expect(page.getByRole('heading', { name: HEADING[name] }).first()).toBeVisible({
        timeout: 15_000,
      });
      perf(testInfo, `nav:${name}-ms`, Date.now() - t0);
      cover(testInfo, `Navigate: ${name}`);
      await human.browse(page);
    }

    // Settings lives below the nav groups.
    await human.click(page, shell.settingsLink());
    await expect(page).toHaveURL(/\/settings/);
    await expect(page.getByRole('heading', { name: /settings/i }).first()).toBeVisible();
    cover(testInfo, 'Navigate: Settings');
  });

  test('infra health widget reports all five datastores', async ({ page }, testInfo) => {
    const shell = new AppShell(page);
    await page.goto('/knowledge');
    const dbs = ['postgres', 'neo4j', 'qdrant', 'redis', 'minio'];
    for (const db of dbs) {
      const dot = shell.dbDot(db);
      await expect(dot, `infra pill for ${db} should render`).toBeVisible();
      // The widget starts at "checking" and resolves once the health poll returns —
      // wait past that transient state before judging the reported status.
      await expect
        .poll(async () => (await dot.getAttribute('title')) ?? '', { timeout: 12_000 })
        .not.toContain('checking');
      const title = (await dot.getAttribute('title')) ?? '';
      note(testInfo, `infra ${db}: ${title}`);
      if (!/healthy/i.test(title)) warn(testInfo, `Datastore ${db} not healthy: ${title}`);
    }
    cover(testInfo, 'Infra health widget (5 datastores)');
  });
});
