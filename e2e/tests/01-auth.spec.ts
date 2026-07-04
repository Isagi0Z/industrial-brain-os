import { test, expect } from './fixtures';
import { LoginPage, SignupPage } from '../pages/AuthPages';
import { USER } from '../utils/config';
import * as human from '../utils/human';
import { shot } from '../utils/media';
import { scanA11y } from '../utils/a11y';
import { cover, suggest, warn, note, perf } from '../utils/findings';

/**
 * Authentication & authorization — runs in the `guest` project (no stored
 * session) so guard redirects and credential handling are exercised from a
 * genuinely unauthenticated state.
 */
test.describe('Authentication & Authorization', () => {
  test('landing page renders with primary calls-to-action', async ({ page }, testInfo) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: /asset & operations/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /launch console/i }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /explore the graph/i })).toBeVisible();
    await human.scroll(page, 3);
    await shot(page, 'landing', true);
    await scanA11y(page, testInfo, 'landing');
    cover(testInfo, 'Landing page + CTAs');
  });

  test('unauthenticated deep-link is redirected to login (route guard)', async ({
    page,
  }, testInfo) => {
    await page.goto('/documents');
    await page.waitForURL(/\/login/, { timeout: 15_000 });
    await expect(page.getByRole('heading', { name: /welcome back/i })).toBeVisible();
    cover(testInfo, 'Route guard (RequireAuth)');
    note(testInfo, 'Protected /documents correctly bounced an anonymous visitor to /login');
  });

  test('invalid credentials are rejected with a friendly error', async ({ page }, testInfo) => {
    const login = new LoginPage(page);
    await login.goto();
    const t0 = Date.now();
    await login.login('nobody@nowhere.test', 'wrong-password-123');
    await expect(login.error()).toBeVisible();
    await expect(login.error()).toContainText(/invalid email or password/i);
    perf(testInfo, 'login-reject-ms', Date.now() - t0);
    // The backend must never leak raw token/JWT internals to the UI.
    await expect(login.error()).not.toContainText(/segment|jwt|traceback/i);
    cover(testInfo, 'Login rejects bad credentials');
  });

  test('signup surfaces duplicate-email conflict (409)', async ({ page }, testInfo) => {
    const signup = new SignupPage(page);
    await signup.goto();
    // The signup form is pre-filled with the primary account, which exists.
    await expect(signup.email()).toHaveValue(USER.email);
    await human.click(page, signup.submit());
    await expect(signup.error()).toBeVisible();
    await expect(signup.error()).toContainText(/already exists/i);
    await shot(page, 'signup-duplicate');
    cover(testInfo, 'Signup duplicate-email handling');
  });

  test('signup enforces the 8-character minimum password (client validation)', async ({
    page,
  }, testInfo) => {
    const signup = new SignupPage(page);
    await signup.goto();
    await signup.email().fill('brand-new-user@industrialbrain.local');
    await signup.password().fill('short');
    await human.click(page, signup.submit());
    // Native minLength blocks submission — we should still be on /signup.
    await expect(page).toHaveURL(/\/signup/);
    const valid = await signup
      .password()
      .evaluate((el: HTMLInputElement) => el.validity.valid);
    expect(valid, 'a 5-char password must be invalid').toBeFalsy();
    cover(testInfo, 'Signup password min-length validation');
  });

  test('successful login, then session-end returns to the guard', async ({ page }, testInfo) => {
    const login = new LoginPage(page);
    await login.goto();
    const t0 = Date.now();
    await login.login(USER.email, USER.password);
    await page.waitForURL(/\/(knowledge|documents|knowledge-graph)/, { timeout: 25_000 });
    perf(testInfo, 'login-success-ms', Date.now() - t0);
    await expect(
      page.getByRole('heading', { name: /knowledge copilot|document hub/i }).first(),
    ).toBeVisible();
    cover(testInfo, 'Login happy-path (UI)');

    // No logout control exists in the app chrome — simulate a session end and
    // confirm the guard re-engages on the next full load.
    const logout = page.getByRole('button', { name: /log ?out|sign ?out/i });
    if ((await logout.count()) === 0) {
      suggest(
        testInfo,
        'No logout / sign-out control exists in the authenticated UI — users cannot end a session without clearing storage. Add a logout action (e.g. in the header avatar or Settings).',
      );
    }
    await page.evaluate(() => localStorage.removeItem('ib_auth_token'));
    await page.goto('/knowledge');
    await page.waitForURL(/\/login/, { timeout: 15_000 });
    await expect(page.getByRole('heading', { name: /welcome back/i })).toBeVisible();
    cover(testInfo, 'Session-end re-guards protected routes');
    if (Date.now() - t0 > 8000) warn(testInfo, 'Login round-trip exceeded 8s');
  });
});
