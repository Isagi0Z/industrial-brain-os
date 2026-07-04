import { test, expect } from './fixtures';
import { AppShell } from '../pages/AppShell';
import { shot } from '../utils/media';
import { cover, note } from '../utils/findings';

test.describe('Settings & Theming', () => {
  test('settings page renders appearance, account, and notifications', async ({ page }, testInfo) => {
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: /^settings$/i })).toBeVisible();
    await expect(page.getByText('Appearance', { exact: true })).toBeVisible();
    await expect(page.getByText('Account', { exact: true })).toBeVisible();
    await expect(page.getByText('Notifications', { exact: true })).toBeVisible();
    cover(testInfo, 'Settings page renders all cards');
  });

  test('dark mode toggles, applies to <html>, and persists across reload', async ({
    page,
  }, testInfo) => {
    const shell = new AppShell(page);
    await page.goto('/knowledge');

    let cls = await shell.htmlThemeClass();
    for (let i = 0; i < 3 && !/dark/.test(cls); i++) {
      await shell.themeToggle().click();
      await page.waitForTimeout(300);
      cls = await shell.htmlThemeClass();
    }
    expect(cls, '<html> should carry the "dark" class').toMatch(/dark/);
    await shot(page, 'dark-mode');
    cover(testInfo, 'Dark mode applies to <html>');

    const stored = await page.evaluate(() => localStorage.getItem('ib-ui-theme'));
    note(testInfo, `persisted theme = ${stored}`);
    await page.reload();
    await expect.poll(async () => shell.htmlThemeClass(), { timeout: 8000 }).toMatch(/dark/);
    cover(testInfo, 'Theme persists across reload');

    // Switch back to light via the Settings appearance cards.
    await page.goto('/settings');
    await page.getByRole('button', { name: 'Light' }).click();
    await expect.poll(async () => shell.htmlThemeClass(), { timeout: 8000 }).toMatch(/light/);
    await shot(page, 'light-mode');
    cover(testInfo, 'Theme switch via Settings controls');
  });
});
