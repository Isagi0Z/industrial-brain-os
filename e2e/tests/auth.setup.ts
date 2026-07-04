import { test as setup, expect } from '@playwright/test';
import { USER } from '../utils/config';
import { AUTH_FILE, ensureDirs } from '../utils/paths';
import * as human from '../utils/human';
import { observe, attachObserved } from '../utils/observe';
import { shot } from '../utils/media';

/**
 * Authenticates once through the real login UI (not an API shortcut) and persists
 * the resulting session (localStorage JWT) to a storage-state file that every
 * authenticated spec reuses. This both produces the shared session AND validates
 * the primary login happy-path as a human would perform it.
 */
setup('authenticate through the login UI', async ({ page }) => {
  ensureDirs();
  const signals = observe(page);

  await page.goto('/login');
  await expect(page.getByRole('heading', { name: /welcome back/i })).toBeVisible();
  await human.browse(page);
  await shot(page, 'login-screen');

  await human.type(page, page.locator('#email'), USER.email);
  await human.type(page, page.locator('#password'), USER.password);
  await human.think(page, 200, 500);
  await human.click(page, page.getByRole('button', { name: /sign in/i }));

  // Guard sends authenticated users to the copilot workspace.
  await page.waitForURL(/\/(knowledge|documents|knowledge-graph)/, { timeout: 25_000 });
  await expect(
    page.getByRole('heading', { name: /knowledge copilot|document hub/i }).first(),
  ).toBeVisible({ timeout: 20_000 });

  // Confirm the JWT was actually persisted where the app reads it.
  const token = await page.evaluate(() => localStorage.getItem('ib_auth_token'));
  expect(token, 'JWT should be stored in localStorage after login').toBeTruthy();

  await shot(page, 'authenticated-dashboard');
  await page.context().storageState({ path: AUTH_FILE });
  await attachObserved(setup.info(), signals);
});
