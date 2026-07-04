import { test as base, expect } from '@playwright/test';
import { observe, attachObserved, type Observed } from '../utils/observe';

/**
 * Base test extended with an auto `signals` fixture: every test transparently
 * gets console/pageerror/network observation attached to its result, and any
 * uncaught page error or 5xx response is promoted to a recorded warning.
 */
export const test = base.extend<{ signals: Observed }>({
  signals: [
    async ({ page }, use, testInfo) => {
      const o = observe(page);
      await use(o);
      await attachObserved(testInfo, o);
      if (o.pageErrors.length) {
        testInfo.annotations.push({
          type: 'warning',
          description: `Uncaught page error(s): ${o.pageErrors.slice(0, 3).join(' | ')}`,
        });
      }
      if (o.serverErrors.length) {
        testInfo.annotations.push({
          type: 'warning',
          description: `Server 5xx: ${o.serverErrors.slice(0, 3).join(' | ')}`,
        });
      }
    },
    { auto: true },
  ],
});

export { expect };
