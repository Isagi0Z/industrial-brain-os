import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Send, Loader2 } from 'lucide-react';
import { MessageBubble, Message } from '../chat/MessageBubble';
import { Citation } from '../chat/CitationCard';
import { Button } from '../ui/button';
import { Card } from '../ui/card';
import { Badge } from '../ui/badge';

/** Shape returned by every chat-style sub-brain endpoint. Brain-specific extra
 * fields (work orders, gap report, ...) are surfaced via the index signature and
 * rendered by the optional `renderContext` panel. */
export interface BrainChatResponse {
  answer: string;
  citations: Citation[];
  session_id: string;
  error_flag: boolean;
  step_count: number;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any;
}

interface BrainChatProps {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
  /** Absolute API path, e.g. "/api/v1/brain/maintenance/chat". */
  endpoint: string;
  suggestions?: string[];
  /** Optional right-hand panel rendered from the latest response (structured
   * data such as work orders, failure history, or a compliance gap report). */
  renderContext?: (last: BrainChatResponse | null) => React.ReactNode;
}

const genId = (): string => Math.random().toString(36).slice(2, 10);
const genSession = (): string =>
  `brain-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;

export const BrainChat: React.FC<BrainChatProps> = ({
  title,
  icon: Icon,
  description,
  endpoint,
  suggestions = [],
  renderContext,
}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isWaiting, setIsWaiting] = useState(false);
  const [lastResponse, setLastResponse] = useState<BrainChatResponse | null>(null);
  // A stable session id keeps multi-turn history coherent on the backend.
  const sessionRef = useRef<string>(genSession());
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = useCallback(
    async (raw?: string) => {
      const query = (raw ?? input).trim();
      if (!query || isWaiting) return;

      const assistantId = genId();
      setMessages((prev) => [
        ...prev,
        { id: genId(), role: 'user', content: query },
        { id: assistantId, role: 'assistant', content: '', isStreaming: true },
      ]);
      setInput('');
      setIsWaiting(true);

      try {
        // No explicit Authorization header — the global fetch interceptor
        // injects the bearer token and refreshes it on a 401.
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query, session_id: sessionRef.current }),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => null);
          throw new Error(
            data?.detail || data?.message || `Request failed (${res.status})`,
          );
        }
        const data = (await res.json()) as BrainChatResponse;
        setLastResponse(data);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: data.answer || '(no answer returned)',
                  citations: data.citations || [],
                  isStreaming: false,
                }
              : m,
          ),
        );
      } catch (err: unknown) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: `⚠️ ${
                    err instanceof Error ? err.message : 'Request failed'
                  }`,
                  isStreaming: false,
                }
              : m,
          ),
        );
      } finally {
        setIsWaiting(false);
      }
    },
    [input, isWaiting, endpoint],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const contextPanel = renderContext?.(lastResponse);

  return (
    <div className="mx-auto flex h-[calc(100vh-8rem)] max-w-6xl flex-col gap-4">
      {/* Header */}
      <Card className="relative shrink-0 overflow-hidden p-5">
        <div className="pointer-events-none absolute -right-16 -top-16 h-40 w-40 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 ring-1 ring-primary/20">
            <Icon className="h-6 w-6 text-primary" />
          </div>
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
            <p className="mt-0.5 line-clamp-2 max-w-3xl text-sm text-muted-foreground">
              {description}
            </p>
          </div>
        </div>
      </Card>

      <div
        className={
          contextPanel
            ? 'grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-3'
            : 'grid min-h-0 flex-1 grid-cols-1 gap-4'
        }
      >
        {/* Chat column */}
        <Card
          className={
            contextPanel
              ? 'flex min-h-0 flex-col overflow-hidden lg:col-span-2'
              : 'flex min-h-0 flex-col overflow-hidden'
          }
        >
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5">
            {messages.length === 0 && (
              <div className="flex h-full flex-col items-center justify-center gap-5 py-10 text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 ring-1 ring-primary/20">
                  <Icon className="h-7 w-7 text-primary" />
                </div>
                <p className="max-w-sm text-sm text-muted-foreground">
                  Ask the {title}. Answers are grounded in your indexed
                  documents, with inline citations.
                </p>
                {suggestions.length > 0 && (
                  <div className="flex w-full max-w-lg flex-col gap-2">
                    {suggestions.map((s) => (
                      <button
                        key={s}
                        onClick={() => send(s)}
                        className="rounded-lg border border-border bg-card/60 px-4 py-2.5 text-left text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div className="border-t border-border px-5 py-4">
            <div className="flex items-end gap-3 rounded-xl border border-input bg-background/60 px-4 py-2.5 transition-colors focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-ring">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={`Ask the ${title}…`}
                rows={1}
                aria-label="Message"
                className="max-h-40 flex-1 resize-none bg-transparent text-sm leading-relaxed text-foreground placeholder:text-muted-foreground focus:outline-none"
              />
              <Button
                variant="gradient"
                size="icon"
                onClick={() => send()}
                disabled={!input.trim() || isWaiting}
                aria-label="Send message"
              >
                {isWaiting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
        </Card>

        {/* Brain-specific context column */}
        {contextPanel && (
          <div className="min-h-0 overflow-y-auto lg:col-span-1">
            {lastResponse === null ? (
              <Card className="p-5">
                <Badge variant="outline">Awaiting first answer</Badge>
                <p className="mt-3 text-xs text-muted-foreground">
                  Structured results appear here once you ask a question.
                </p>
              </Card>
            ) : (
              contextPanel
            )}
          </div>
        )}
      </div>
    </div>
  );
};
