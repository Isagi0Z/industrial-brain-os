import { test, expect } from './fixtures';
import { shot } from '../utils/media';
import { cover, note } from '../utils/findings';

test.describe('Resilience & Edge Cases', () => {
  test('unknown route renders the 404 page', async ({ page }, testInfo) => {
    await page.goto('/this-route-does-not-exist-xyz');
    await expect(page.getByText('404')).toBeVisible();
    await expect(page.getByRole('heading', { name: /page not found/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /home/i })).toBeVisible();
    await shot(page, 'not-found-404');
    cover(testInfo, '404 / NotFound route');
  });

  test('API failure degrades gracefully (no white screen)', async ({ page }, testInfo) => {
    // Force every document list/detail call to fail at the network layer.
    await page.route('**/api/v1/documents/**', (route) => route.abort());
    await page.goto('/documents');
    await expect(page.getByRole('heading', { name: /document hub/i })).toBeVisible({
      timeout: 15_000,
    });
    // The app shows its empty affordance rather than crashing to an error page.
    await expect(page.getByText(/page not found|application error/i)).toHaveCount(0);
    note(testInfo, 'Document list handled an aborted API call without a crash.');
    cover(testInfo, 'Graceful API / network-failure handling');
    await page.unroute('**/api/v1/documents/**');
  });

  test('multi-tab: copilot and knowledge graph run in parallel tabs', async ({
    page,
    context,
  }, testInfo) => {
    await page.goto('/knowledge');
    await expect(page.getByRole('heading', { name: /knowledge copilot/i }).first()).toBeVisible();

    const tab2 = await context.newPage();
    await tab2.goto('/knowledge-graph');
    await expect(tab2.getByRole('heading', { name: /knowledge graph/i }).first()).toBeVisible();

    // Both tabs share the authenticated session and are independently usable.
    await tab2.locator('#kg-tag').fill('M-330');
    await tab2.getByRole('button', { name: 'Explore' }).click();
    await tab2.waitForTimeout(1500);
    await expect(page.getByText('Connected', { exact: true })).toBeVisible();
    await tab2.close();
    cover(testInfo, 'Multi-tab parallel authenticated sessions');
  });
});
