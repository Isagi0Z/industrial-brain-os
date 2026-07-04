# Industrial Brain OS — E2E Validation Summary

_Autonomous browser validation via Playwright + Google Chrome (channel: chrome)._

## Verdict

✅ **PASS** — 31/31 tests passed

| Metric | Value |
|--------|-------|
| Total tests | 31 |
| Passed | 31 |
| Passed on retry (flaky) | 0 |
| Failed | 0 |
| Skipped | 0 |
| Wall-clock duration | 325.1s |
| Warnings recorded | 6 |
| Suggestions recorded | 3 |
| Coverage checks | 47 |

## By suite

| Spec file | Tests | Passed | Failed | Skipped |
|-----------|-------|--------|--------|---------|
| `auth.setup.ts` | 1 | 1 | 0 | 0 |
| `01-auth.spec.ts` | 6 | 6 | 0 | 0 |
| `02-navigation.spec.ts` | 2 | 2 | 0 | 0 |
| `03-documents.spec.ts` | 3 | 3 | 0 | 0 |
| `04-chat.spec.ts` | 2 | 2 | 0 | 0 |
| `05-knowledge-graph.spec.ts` | 4 | 4 | 0 | 0 |
| `06-brains.spec.ts` | 5 | 5 | 0 | 0 |
| `07-settings-theme.spec.ts` | 2 | 2 | 0 | 0 |
| `08-responsive-a11y.spec.ts` | 3 | 3 | 0 | 0 |
| `09-resilience.spec.ts` | 3 | 3 | 0 | 0 |

## Individual tests

| | Test | Project | Duration |
|---|------|---------|----------|
| ✅ | authenticate through the login UI | setup | 14.8s |
| ✅ | landing page renders with primary calls-to-action | guest | 6.1s |
| ✅ | unauthenticated deep-link is redirected to login (route guard) | guest | 1.9s |
| ✅ | invalid credentials are rejected with a friendly error | guest | 7.6s |
| ✅ | signup surfaces duplicate-email conflict (409) | guest | 3.1s |
| ✅ | signup enforces the 8-character minimum password (client validation) | guest | 3.0s |
| ✅ | successful login, then session-end returns to the guard | guest | 9.8s |
| ✅ | every sidebar route loads its page | app | 24.5s |
| ✅ | infra health widget reports all five datastores | app | 1.9s |
| ✅ | library search and status filter behave deterministically | app | 3.5s |
| ✅ | uploads a real industrial PDF through the browser and cleans up | app | 70.3s |
| ✅ | document details opens from the library | app | 2.4s |
| ✅ | connects over WebSocket and answers a grounded question | app | 71.1s |
| ✅ | send is guarded on empty input and New conversation resets the thread | app | 2.8s |
| ✅ | renders the seeded P-102A subgraph | app | 12.1s |
| ✅ | depth expansion returns an equal-or-larger neighbourhood | app | 4.1s |
| ✅ | clicking the canvas surfaces entity details (best-effort) | app | 4.5s |
| ✅ | unknown tag is handled gracefully (no crash) | app | 3.7s |
| ✅ | Maintenance brain panel reports live service health | app | 2.9s |
| ✅ | Compliance brain panel reports live service health | app | 2.6s |
| ✅ | Root Cause brain panel reports live service health | app | 2.4s |
| ✅ | Lessons Learned brain panel reports live service health | app | 2.8s |
| ✅ | brains are status scaffolds — interactive workflows not yet built | app | 0.6s |
| ✅ | settings page renders appearance, account, and notifications | app | 1.7s |
| ✅ | dark mode toggles, applies to <html>, and persists across reload | app | 4.6s |
| ✅ | mobile layout hides the sidebar behind a menu button | app | 2.8s |
| ✅ | tablet layout renders without meaningful horizontal overflow | app | 1.7s |
| ✅ | accessibility scan (axe-core) of core authenticated pages | app | 11.6s |
| ✅ | unknown route renders the 404 page | app | 1.7s |
| ✅ | API failure degrades gracefully (no white screen) | app | 1.9s |
| ✅ | multi-tab: copilot and knowledge graph run in parallel tabs | app | 5.4s |

_See [failures.md](failures.md), [warnings.md](warnings.md), [suggestions.md](suggestions.md), [performance.md](performance.md), and [coverage.md](coverage.md)._
