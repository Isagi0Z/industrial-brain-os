import { Page, Locator } from '@playwright/test';

/**
 * Human-behaviour helpers. Real operators move the mouse in arcs, pause to read,
 * type at a variable cadence, and scroll to take a page in. These wrappers layer
 * that realism on top of Playwright's auto-waiting locators (so resilience is
 * preserved — every action still waits for actionability before firing).
 */

export function rand(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

/** Reading / decision pause. */
export async function think(page: Page, min = 350, max: number = min + 750): Promise<void> {
  await page.waitForTimeout(rand(min, max));
}

/** Glide the cursor to the centre of a target in several steps. */
export async function moveTo(page: Page, locator: Locator): Promise<void> {
  await locator.scrollIntoViewIfNeeded().catch(() => {});
  const box = await locator.boundingBox();
  if (box) {
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, {
      steps: rand(10, 24),
    });
  }
}

/** Move-then-click with a natural micro-pause. */
export async function click(page: Page, locator: Locator): Promise<void> {
  await moveTo(page, locator);
  await think(page, 120, 360);
  await locator.click();
}

/** Focus a field and type character-by-character at a human cadence. */
export async function type(page: Page, locator: Locator, text: string): Promise<void> {
  await click(page, locator);
  await locator.fill('');
  await locator.pressSequentially(text, { delay: rand(35, 95) });
}

/** Scroll down the page in wheel increments, pausing between each. */
export async function scroll(page: Page, steps = 4): Promise<void> {
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, rand(240, 520));
    await think(page, 200, 620);
  }
}

/** Wiggle the cursor around to simulate a person orienting on a new page. */
export async function browse(page: Page): Promise<void> {
  const w = page.viewportSize()?.width ?? 1440;
  const h = page.viewportSize()?.height ?? 900;
  for (let i = 0; i < rand(2, 4); i++) {
    await page.mouse.move(rand(80, w - 80), rand(80, h - 80), { steps: rand(8, 18) });
    await think(page, 150, 480);
  }
}
