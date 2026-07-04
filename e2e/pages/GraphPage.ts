import { Page, Locator } from '@playwright/test';

/** Knowledge Graph — Neo4j bounded subgraph rendered on a Cytoscape canvas. */
export class GraphPage {
  constructor(private readonly page: Page) {}

  tagInput(): Locator {
    return this.page.locator('#kg-tag');
  }
  depthSelect(): Locator {
    return this.page.locator('#kg-depth');
  }
  exploreButton(): Locator {
    return this.page.getByRole('button', { name: 'Explore' });
  }
  canvas(): Locator {
    return this.page.getByTestId('kg-canvas');
  }
  /** Details panel summary, e.g. "8 nodes, 7 edges. Click a node to inspect it." */
  statsText(): Locator {
    return this.page.getByText(/\d+ nodes,\s*\d+ edges/);
  }
  errorText(): Locator {
    return this.page.getByText(/No subgraph found/i);
  }
  selectedEntityHeading(): Locator {
    return this.page.getByText('Entity Details');
  }

  /** Parse the "N nodes, M edges" summary into numbers (−1,−1 if absent). */
  async stats(): Promise<{ nodes: number; edges: number }> {
    const el = this.statsText();
    if (!(await el.count())) return { nodes: -1, edges: -1 };
    const txt = await el.first().innerText();
    const m = txt.match(/(\d+)\s*nodes,\s*(\d+)\s*edges/i);
    return m ? { nodes: Number(m[1]), edges: Number(m[2]) } : { nodes: -1, edges: -1 };
  }

  async explore(tag: string, depth?: number): Promise<void> {
    await this.tagInput().fill(tag);
    if (depth) await this.depthSelect().selectOption(String(depth));
    await this.exploreButton().click();
  }

  /** Cytoscape draws to canvas (no DOM nodes), so we click canvas coordinates. */
  async clickCanvasCenter(): Promise<void> {
    const box = await this.canvas().boundingBox();
    if (box) {
      await this.page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    }
  }
}
