import type { FullConfig } from '@playwright/test';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { BACKEND, USER } from './utils/config';
import { REPO_ROOT, ensureDirs } from './utils/paths';

/**
 * Global setup runs once before the whole suite:
 *   1. Ensure report directories exist.
 *   2. Wait for the backend to be healthy (best-effort: start it if it is down).
 *   3. Ensure the primary test user exists (idempotent register — 409 is fine).
 * The frontend dev server is handled by the `webServer` block in the config.
 */

interface Health {
  status?: string;
  databases?: Record<string, string>;
}

async function probeHealth(): Promise<Health | null> {
  try {
    const res = await fetch(`${BACKEND}/api/v1/health`, {
      signal: AbortSignal.timeout(4000),
    });
    if (!res.ok) return null;
    return (await res.json()) as Health;
  } catch {
    return null;
  }
}

function tryStartBackend(): void {
  const py = path.join(REPO_ROOT, 'backend', 'venv', 'Scripts', 'python.exe');
  try {
    const child = spawn(
      py,
      ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'],
      { cwd: path.join(REPO_ROOT, 'backend'), detached: true, stdio: 'ignore' },
    );
    child.unref();
    // eslint-disable-next-line no-console
    console.log('[global-setup] backend not reachable — attempted to start uvicorn.');
  } catch (err) {
    // eslint-disable-next-line no-console
    console.log(`[global-setup] could not auto-start backend: ${String(err)}`);
  }
}

async function waitForBackend(timeoutMs = 120_000): Promise<Health> {
  const deadline = Date.now() + timeoutMs;
  let attempted = false;
  let last: Health | null = null;
  while (Date.now() < deadline) {
    last = await probeHealth();
    if (last && (last.status === 'healthy' || last.status === 'degraded')) return last;
    if (!last && !attempted) {
      tryStartBackend();
      attempted = true;
    }
    await sleep(3000);
  }
  throw new Error(
    `Backend at ${BACKEND} never became healthy within ${timeoutMs / 1000}s. ` +
      `Start it with "make dev" (or uvicorn) and re-run.`,
  );
}

async function ensureUser(): Promise<void> {
  try {
    const res = await fetch(`${BACKEND}/api/v1/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: USER.email,
        password: USER.password,
        full_name: USER.fullName,
      }),
      signal: AbortSignal.timeout(8000),
    });
    if (res.status === 201) console.log(`[global-setup] created test user ${USER.email}`);
    else if (res.status === 409) console.log(`[global-setup] test user ${USER.email} already exists`);
    else console.log(`[global-setup] register returned ${res.status} (continuing)`);
  } catch (err) {
    console.log(`[global-setup] register call failed: ${String(err)} (continuing)`);
  }
}

export default async function globalSetup(_config: FullConfig): Promise<void> {
  ensureDirs();
  const health = await waitForBackend();
  const dbs = health.databases ?? {};
  const unhealthy = Object.entries(dbs).filter(([, v]) => v !== 'healthy');
  console.log(
    `[global-setup] backend status=${health.status}; ` +
      `databases: ${Object.keys(dbs).length} total, ${unhealthy.length} not healthy` +
      (unhealthy.length ? ` (${unhealthy.map(([k]) => k).join(', ')})` : ''),
  );
  await ensureUser();
}
