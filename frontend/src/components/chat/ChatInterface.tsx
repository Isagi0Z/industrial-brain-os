import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Send, Loader2, Sparkles, RefreshCw, Bot } from 'lucide-react';
import { MessageBubble, Message } from './MessageBubble';
import { Citation } from './CitationCard';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { cn } from '../../lib/utils';

const WS_BASE = `ws://${window.location.hostname}:8000`;

interface DoneEvent {
  type: 'done';
  citations: Citation[];
  token_usage: {
    prompt_tokens: number;
    completion_tokens: number;
    model: string;
    latency_ms: number;
  };
  session_id: string;
}

function generateId(): string {
  return Math.random().toString(36).slice(2, 10);
}

function generateSessionId(): string {
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
}

export const ChatInterface: React.FC = () => {
  const { token } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [sessionId] = useState(generateSessionId);
  const [isConnected, setIsConnected] = useState(false);
  const [isWaiting, setIsWaiting] = useState(false);
  const [lastModel, setLastModel] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const streamingIdRef = useRef<string | null>(null);
  // The server closes the socket after each answer; a queued query is flushed
  // on the next reconnect so follow-up messages never get dropped.
  const pendingPayloadRef = useRef<string | null>(null);
  // Keep the socket ready between turns: reconnect after the server closes it,
  // unless we are intentionally tearing down (unmount / new conversation).
  const shouldReconnectRef = useRef(true);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const connect = useCallback(() => {
    if (!token) return;
    // Do not open a second socket while one is already OPEN or CONNECTING.
    const existing = wsRef.current?.readyState;
    if (existing === WebSocket.OPEN || existing === WebSocket.CONNECTING) return;

    // Pass the JWT as a WebSocket subprotocol (`ib-bearer, <token>`) instead of
    // the query string, so it never appears in server access logs or history.
    const ws = new WebSocket(`${WS_BASE}/api/v1/chat/stream`, [
      'ib-bearer',
      token,
    ]);
    wsRef.current = ws;
    let opened = false;
    // Every handler ignores events once this socket is no longer the active one.
    // React StrictMode double-mounts effects, and a dropped connection triggers
    // a reconnect, so several sockets can briefly coexist; without this guard a
    // stale socket's frames would corrupt the live stream (e.g. a follow-up
    // answer rendering only its first token) and its close would storm reconnects.
    const isCurrent = () => wsRef.current === ws;

    ws.onopen = () => {
      if (!isCurrent()) {
        try {
          ws.close();
        } catch {
          /* stale socket already gone */
        }
        return;
      }
      opened = true;
      setIsConnected(true);
      // Flush a query queued while the socket was (re)connecting.
      if (pendingPayloadRef.current) {
        ws.send(pendingPayloadRef.current);
        pendingPayloadRef.current = null;
      }
    };
    ws.onclose = () => {
      if (!isCurrent()) return;
      setIsWaiting(false);
      // Reconnect a working connection that dropped unexpectedly so the copilot
      // stays ready for the next question without a visible flicker. A socket
      // that never opened signals a real failure, so we surface Disconnected
      // rather than retry-storm.
      if (opened && shouldReconnectRef.current && token) {
        if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = setTimeout(() => connect(), 300);
      } else {
        setIsConnected(false);
      }
    };
    ws.onerror = () => {
      if (!isCurrent()) return;
      setIsConnected(false);
      setIsWaiting(false);
    };

    ws.onmessage = (event: MessageEvent) => {
      if (!isCurrent()) return;
      const data = JSON.parse(event.data as string) as {
        type: string;
        content?: string;
        message?: string;
        citations?: Citation[];
        token_usage?: DoneEvent['token_usage'];
        session_id?: string;
      };

      if (data.type === 'token') {
        const chunk = data.content ?? '';
        setMessages((prev) =>
          prev.map((m) =>
            m.id === streamingIdRef.current
              ? { ...m, content: m.content + chunk }
              : m
          )
        );
      } else if (data.type === 'done') {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === streamingIdRef.current
              ? { ...m, citations: data.citations ?? [], isStreaming: false }
              : m
          )
        );
        if (data.token_usage) setLastModel(data.token_usage.model);
        streamingIdRef.current = null;
        setIsWaiting(false);
      } else if (data.type === 'error') {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === streamingIdRef.current
              ? {
                  ...m,
                  content: `⚠️ ${data.message ?? 'LLM unavailable'}`,
                  isStreaming: false,
                }
              : m
          )
        );
        streamingIdRef.current = null;
        setIsWaiting(false);
      }
    };
  }, [token]);

  useEffect(() => {
    shouldReconnectRef.current = true;
    connect();
    return () => {
      // Stop the reconnect loop and tear down cleanly on unmount / token change.
      // Disown the socket first so a StrictMode remount always builds a fresh one
      // (and the old socket's late events see themselves as no longer current).
      shouldReconnectRef.current = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      const ws = wsRef.current;
      wsRef.current = null;
      ws?.close();
    };
  }, [connect]);

  const sendMessage = useCallback(() => {
    const query = input.trim();
    if (!query || isWaiting) return;

    const userMsg: Message = {
      id: generateId(),
      role: 'user',
      content: query,
    };
    const assistantId = generateId();
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      isStreaming: true,
    };

    streamingIdRef.current = assistantId;
    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput('');
    setIsWaiting(true);

    const payload = JSON.stringify({
      query,
      session_id: sessionId,
      top_k: 5,
      role_scope: 'public',
    });

    // The server closes the socket after each answer, so a follow-up question
    // often finds it CLOSED. Queue the payload and (re)connect — ws.onopen
    // flushes it — instead of dropping the message and forcing a second click.
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(payload);
    } else {
      pendingPayloadRef.current = payload;
      connect();
    }
  }, [input, isWaiting, sessionId, connect]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const resetSession = () => {
    setMessages([]);
    wsRef.current?.close();
    setTimeout(connect, 200);
  };

  const suggestions = [
    'What is the rated discharge pressure of pump P-102A?',
    'How do I isolate pump P-102A before maintenance?',
    'What failure modes does P-102A exhibit?',
  ];

  return (
    <div className="mx-auto flex h-full max-h-[calc(100vh-8rem)] max-w-4xl flex-col overflow-hidden rounded-2xl border border-border bg-card/40">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-amber-500 to-red-500 shadow-glow">
            <Sparkles className="h-4 w-4 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-semibold">Knowledge Copilot</h1>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <span
                  className={cn(
                    'h-1.5 w-1.5 rounded-full',
                    isConnected ? 'bg-success' : 'bg-destructive'
                  )}
                />
                {isConnected ? 'Connected' : 'Disconnected'}
              </span>
              {lastModel && <span className="font-mono text-muted-foreground/70">{lastModel}</span>}
            </div>
          </div>
        </div>
        <Button variant="ghost" size="icon" onClick={resetSession} title="New conversation">
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {/* Messages */}
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-5 py-10 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 ring-1 ring-primary/20">
              <Bot className="h-8 w-8 text-primary" />
            </div>
            <div>
              <h2 className="text-base font-semibold">Ask your document library</h2>
              <p className="mx-auto mt-1.5 max-w-sm text-sm text-muted-foreground">
                Answers are grounded in your indexed industrial documents, with inline citations.
              </p>
            </div>
            <div className="flex w-full max-w-lg flex-col gap-2">
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => setInput(s)}
                  className="rounded-lg border border-border bg-card/60 px-4 py-2.5 text-left text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
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
            placeholder="Ask about a document, equipment, procedure…"
            rows={1}
            aria-label="Message"
            className="max-h-40 flex-1 resize-none bg-transparent text-sm leading-relaxed text-foreground placeholder:text-muted-foreground focus:outline-none"
            style={{ fieldSizing: 'content' } as React.CSSProperties}
          />
          <Button
            variant="gradient"
            size="icon"
            onClick={sendMessage}
            // Not gated on isConnected: the backend closes the socket between
            // answers, and sendMessage transparently reconnects + queues.
            disabled={!input.trim() || isWaiting}
            aria-label="Send message"
          >
            {isWaiting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
        <p className="mt-2 flex items-center justify-center gap-2 text-center text-[10px] text-muted-foreground/70">
          <Badge variant="outline" className="px-1.5 py-0 text-[9px]">Enter</Badge> to send ·
          <Badge variant="outline" className="px-1.5 py-0 text-[9px]">Shift+Enter</Badge> new line ·
          grounded in indexed documents only
        </p>
      </div>
    </div>
  );
};
