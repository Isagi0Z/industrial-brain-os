import { test, expect } from './fixtures';
import { AppShell } from '../pages/AppShell';
import { scanA11y } from '../utils/a11y';
import { shot } from '../utils/media';
import { cover, note, warn } from '../utils/findings';

test.describe('Responsiveness & Accessibility', () => {
  test('mobile layout hides the sidebar behind a menu button', async ({ page }, testInfo) => {
    const shell = new AppShell(page);
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/documents');

    await expect(shell.openMenuButton()).toBeVisible();
    const aside = page.locator('aside').first();
    const closed = await aside.boundingBox();
    expect(closed && closed.x, 'sidebar should be off-canvas on mobile').toBeLessThan(0);
    await shot(page, 'mobile-collapsed');

    await shell.openMenuButton().click();
    await page.waitForTimeout(400);
    const open = await aside.boundingBox();
    expect(open && open.x, 'sidebar should slide on-screen when opened').toBeGreaterThanOrEqual(0);
    await expect(shell.navLink('Knowledge Graph')).toBeVisible();
    await shot(page, 'mobile-nav-open');
    cover(testInfo, 'Responsive: mobile off-canvas sidebar');

    await page.setViewportSize({ width: 1440, height: 900 });
  });

  test('tablet layout renders without meaningful horizontal overflow', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/knowledge');
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    note(testInfo, `tablet horizontal overflow: ${overflow}px`);
    if (overflow > 0) warn(testInfo, `Tablet viewport has ${overflow}px horizontal overflow.`);
    expect(overflow).toBeLessThanOrEqual(32);
    cover(testInfo, 'Responsive: tablet layout');
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  test('accessibility scan (axe-core) of core authenticated pages', async ({ page }, testInfo) => {
    for (const route of ['/documents', '/knowledge', '/knowledge-graph', '/settings']) {
      await page.goto(route);
      await page.waitForTimeout(800);
      await scanA11y(page, testInfo, route.replace(/\//g, '') || 'root');
    }
    cover(testInfo, 'Accessibility scan of core pages');
  });
});
