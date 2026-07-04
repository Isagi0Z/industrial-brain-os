import { Page, Locator } from '@playwright/test';

export interface ChatOutcome {
  frames: string[];
  answered: boolean;
  errored: boolean;
  citationCount: number;
  model: string | null;
  latencyMs: number | null;
}

/** Knowledge Copilot — streaming WebSocket chat grounded in the doc library. */
export class ChatPage {
  constructor(private readonly page: Page) {}

  status(): Locator {
    return this.page.getByText(/^(Connected|Disconnected)$/);
  }
  connected(): Locator {
    return this.page.getByText('Connected', { exact: true });
  }
  input(): Locator {
    // Exact — otherwise "Send message" (the button) also matches "Message".
    return this.page.getByLabel('Message', { exact: true });
  }
  sendButton(): Locator {
    return this.page.getByLabel('Send message');
  }
  newConversation(): Locator {
    return this.page.getByRole('button', { name: /new conversation/i });
  }
  suggestion(index = 0): Locator {
    return this.page.getByRole('button', { name: /pump P-102A|failure modes|isolate/i }).nth(index);
  }
  bubbles(): Locator {
    // Message content divs (avoids the `max-w-[85%]` bracketed class token).
    return this.page.locator('.whitespace-pre-wrap.rounded-2xl');
  }
  sourcesToggle(): Locator {
    return this.page.getByRole('button', { name: /source/i });
  }

  /**
   * Sends a query and resolves once the backend signals completion. Chat is a
   * streaming WebSocket, so we observe the frames directly — deterministic and
   * model-agnostic — rather than scraping the DOM as tokens arrive.
   */
  async ask(query: string, ws: () => string[], timeoutMs = 75_000): Promise<ChatOutcome> {
    await this.input().fill(query);
    await this.sendButton().click();

    const deadline = Date.now() + timeoutMs;
    let done: Record<string, unknown> | null = null;
    let errored = false;
    while (Date.now() < deadline) {
      for (const raw of ws()) {
        try {
          const obj = JSON.parse(raw) as Record<string, unknown>;
          if (obj.type === 'done') done = obj;
          if (obj.type === 'error') errored = true;
        } catch {
          /* non-JSON frame — ignore */
        }
      }
      if (done || errored) break;
      await this.page.waitForTimeout(500);
    }

    const usage = (done?.token_usage ?? {}) as Record<string, unknown>;
    const citations = (done?.citations ?? []) as unknown[];
    return {
      frames: ws(),
      answered: Boolean(done),
      errored,
      citationCount: citations.length,
      model: (usage.model as string) ?? null,
      latencyMs: (usage.latency_ms as number) ?? null,
    };
  }
}
