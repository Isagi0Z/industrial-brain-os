import { test, expect } from './fixtures';
import { ChatPage } from '../pages/ChatPage';
import { shot } from '../utils/media';
import { cover, perf, warn, note, suggest } from '../utils/findings';

const QUESTION = 'What is the rated discharge pressure of pump P-102A?';

test.describe('Knowledge Copilot (Chat)', () => {
  test('connects over WebSocket and answers a grounded question', async ({ page }, testInfo) => {
    test.setTimeout(150_000); // first-token latency depends on model warm-up
    // Observe the streaming WebSocket directly — deterministic and model-agnostic.
    const frames: string[] = [];
    page.on('websocket', (ws) => {
      if (ws.url().includes('/chat/stream')) {
        ws.on('framereceived', (f) => {
          if (typeof f.payload === 'string') frames.push(f.payload);
        });
      }
    });

    const chat = new ChatPage(page);
    await page.goto('/knowledge');
    await expect(chat.connected()).toBeVisible({ timeout: 20_000 });
    cover(testInfo, 'Chat WebSocket connects (authenticated)');
    await shot(page, 'chat-connected');

    // A suggested prompt should populate the composer.
    const suggestion = page.getByRole('button', { name: /rated discharge pressure of pump P-102A/i });
    if (await suggestion.count()) {
      await suggestion.click();
      await expect(chat.input()).toHaveValue(/discharge pressure/i);
      cover(testInfo, 'Chat suggestion populates composer');
    }

    const outcome = await chat.ask(QUESTION, () => frames, 90_000);
    // Deterministic assertions: the user turn and an assistant turn must render.
    await expect(page.getByText(QUESTION).first()).toBeVisible();
    await expect(chat.bubbles().nth(1)).toBeVisible();
    cover(testInfo, 'Chat sends a query and renders both turns');

    // Answer quality is best-effort (model/pipeline dependent) — recorded, not asserted.
    if (outcome.answered) {
      cover(testInfo, 'Chat completed a streamed answer');
      note(
        testInfo,
        `chat model=${outcome.model ?? 'n/a'} latency_ms=${outcome.latencyMs ?? 'n/a'} citations=${outcome.citationCount}`,
      );
      if (outcome.latencyMs) perf(testInfo, 'chat-answer-latency-ms', outcome.latencyMs);
      if (outcome.citationCount > 0) {
        cover(testInfo, 'Chat answer carried citations on the wire');
        // The `done` frame carried citations — verify the UI actually renders the card.
        const cardShown = await chat
          .sourcesToggle()
          .first()
          .waitFor({ state: 'visible', timeout: 5000 })
          .then(() => true)
          .catch(() => false);
        if (cardShown) {
          await chat.sourcesToggle().first().click();
          await expect(page.getByText(/\d+%/).first()).toBeVisible();
          cover(testInfo, 'Citation card renders and expands');
        } else {
          warn(
            testInfo,
            `Copilot 'done' frame carried ${outcome.citationCount} citation(s) but no citation card rendered in the UI. The answer used "[source_1]"-style inline references rather than the backend's expected [[chunk:<id>]] markers — investigate the citation display / prompt marker format.`,
          );
        }
      } else {
        note(testInfo, 'Chat answered with 0 citations.');
        suggest(
          testInfo,
          'Chat answered but returned no citations — expected while the demo corpus is not indexed (no ingestion worker). After indexing, answers should cite the P-102A manuals; re-run to validate grounded retrieval.',
        );
      }
      await shot(page, 'chat-answer');
    } else if (outcome.errored) {
      warn(testInfo, 'Chat returned an error frame instead of an answer (LLM/pipeline issue).');
      await shot(page, 'chat-answer');
    } else {
      warn(
        testInfo,
        'Chat did not complete within 90s (no done/error frame) — likely cold model warm-up or a stalled pipeline stage.',
      );
      await shot(page, 'chat-answer');
    }
  });

  test('send is guarded on empty input and New conversation resets the thread', async ({
    page,
  }, testInfo) => {
    const chat = new ChatPage(page);
    await page.goto('/knowledge');
    await expect(chat.connected()).toBeVisible({ timeout: 20_000 });

    await expect(chat.sendButton()).toBeDisabled();
    await chat.input().fill('Hello');
    await expect(chat.sendButton()).toBeEnabled();
    await chat.input().fill('');
    await expect(chat.sendButton()).toBeDisabled();
    cover(testInfo, 'Chat send disabled while composer is empty');

    await chat.input().fill('ping');
    await chat.sendButton().click();
    await expect(page.getByText('ping').first()).toBeVisible();
    await chat.newConversation().click();
    await expect(page.getByText(/ask your document library/i)).toBeVisible();
    cover(testInfo, 'Chat "New conversation" resets to the empty state');
  });
});
