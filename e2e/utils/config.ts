/**
 * Central configuration for the E2E suite. Everything is overridable via env so
 * the same suite runs against local dev, a preview server, or CI unchanged.
 */
export const BACKEND = process.env.E2E_BACKEND ?? 'http://127.0.0.1:8000';
export const PORT = process.env.E2E_PORT ?? '5199';
export const BASE_URL = process.env.E2E_BASE_URL ?? `http://127.0.0.1:${PORT}`;

/** Primary interactive user (the account created during the signup phase). */
export const USER = {
  email: process.env.E2E_USER ?? 'ratish01@industrialbrain.local',
  password: process.env.E2E_PASS ?? 'Ratish*966',
  fullName: 'Ratish',
};

/** Seeded development admin — fallback if the primary user is unavailable. */
export const ADMIN = {
  email: 'admin@industrialbrain.local',
  password: 'ChangeMe123!',
};

/** Equipment tag the demo dataset is built around (KG seed + chat prompts). */
export const DEMO_TAG = 'P-102A';
