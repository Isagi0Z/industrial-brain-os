import { Page, Locator } from '@playwright/test';
import * as human from '../utils/human';

/** Sidebar routes keyed by their exact accessible link name. */
export const NAV: Record<string, string> = {
  'Document Hub': '/documents',
  'Knowledge Copilot': '/knowledge',
  'Knowledge Graph': '/knowledge-graph',
  Maintenance: '/maintenance',
  Compliance: '/compliance',
  'Root Cause': '/rca',
  'Lessons Learned': '/lessons-learned',
};

/** The persistent authenticated chrome: sidebar nav, theme toggle, infra dots. */
export class AppShell {
  constructor(private readonly page: Page) {}

  navLink(name: string): Locator {
    return this.page.getByRole('link', { name, exact: true });
  }

  themeToggle(): Locator {
    return this.page.getByRole('button', { name: /switch theme/i }).first();
  }

  openMenuButton(): Locator {
    return this.page.getByRole('button', { name: /open menu/i });
  }

  settingsLink(): Locator {
    return this.page.getByRole('link', { name: /^settings$/i });
  }

  /** The 5 infra status pills carry a `title="<db>: <status>"`. */
  dbDot(db: string): Locator {
    return this.page.locator(`[title^="${db}:"]`);
  }

  async goto(name: string): Promise<void> {
    await human.click(this.page, this.navLink(name));
    await this.page.waitForURL(`**${NAV[name]}`);
  }

  /** The applied theme lives as a class on <html> ('light' | 'dark'). */
  async htmlThemeClass(): Promise<string> {
    return this.page.evaluate(() => document.documentElement.className.trim());
  }
}
