import { test, expect } from './fixtures';
import { GraphPage } from '../pages/GraphPage';
import { DEMO_TAG } from '../utils/config';
import { shot } from '../utils/media';
import { cover, perf, note } from '../utils/findings';

test.describe('Knowledge Graph', () => {
  test('renders the seeded P-102A subgraph', async ({ page }, testInfo) => {
    const kg = new GraphPage(page);
    const t0 = Date.now();
    await page.goto('/knowledge-graph');
    await expect(kg.canvas()).toBeVisible();
    await expect(kg.statsText()).toBeVisible({ timeout: 20_000 });
    const stats = await kg.stats();
    perf(testInfo, 'kg-load-ms', Date.now() - t0);
    note(testInfo, `KG ${DEMO_TAG} depth1: ${stats.nodes} nodes, ${stats.edges} edges`);
    expect(stats.nodes, 'seeded subgraph should contain multiple nodes').toBeGreaterThan(1);
    await shot(page, 'knowledge-graph');
    cover(testInfo, 'KG renders seeded subgraph');
  });

  test('depth expansion returns an equal-or-larger neighbourhood', async ({ page }, testInfo) => {
    const kg = new GraphPage(page);
    await page.goto('/knowledge-graph');
    await expect(kg.statsText()).toBeVisible({ timeout: 20_000 });
    const d1 = await kg.stats();
    await kg.explore(DEMO_TAG, 3);
    await expect(kg.statsText()).toBeVisible({ timeout: 20_000 });
    await page.waitForTimeout(1200);
    const d3 = await kg.stats();
    note(testInfo, `depth1=${d1.nodes} nodes, depth3=${d3.nodes} nodes`);
    expect(d3.nodes).toBeGreaterThanOrEqual(d1.nodes);
    cover(testInfo, 'KG depth control expands traversal');
  });

  test('clicking the canvas surfaces entity details (best-effort)', async ({ page }, testInfo) => {
    const kg = new GraphPage(page);
    await page.goto('/knowledge-graph');
    await expect(kg.statsText()).toBeVisible({ timeout: 20_000 });
    await page.waitForTimeout(1600); // let the cose layout settle
    await kg.clickCanvasCenter();
    await page.waitForTimeout(700);
    const details = page.getByText(/Relationships \(\d+\)/);
    if (await details.count()) {
      cover(testInfo, 'KG node selection → entity details panel');
    } else {
      note(
        testInfo,
        'Canvas-centre click did not land on a node (Cytoscape renders to <canvas>; coordinate hit-testing is inherently best-effort).',
      );
    }
  });

  test('unknown tag is handled gracefully (no crash)', async ({ page }, testInfo) => {
    const kg = new GraphPage(page);
    await page.goto('/knowledge-graph');
    await kg.explore('NOPE-DOES-NOT-EXIST-999');
    await page.waitForTimeout(1500);
    // Either the amber empty-state message or a minimal stats readout — never a crash.
    await expect(kg.errorText().or(kg.statsText())).toBeVisible({ timeout: 20_000 });
    await expect(kg.canvas()).toBeVisible();
    await expect(page.getByText(/page not found/i)).toHaveCount(0);
    cover(testInfo, 'KG handles unknown tag gracefully');
  });
});
