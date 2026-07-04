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

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const connect = useCallback(() => {
    if (!token) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(
      `${WS_BASE}/api/v1/chat/stream?token=${encodeURIComponent(token)}`
    );
    wsRef.current = ws;

    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => {
      setIsConnected(false);
      setIsWaiting(false);
    };
    ws.onerror = () => {
      setIsConnected(false);
      setIsWaiting(false);
    };

    ws.onmessage = (event: MessageEvent) => {
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
    connect();
    return () => wsRef.current?.close();
  }, [connect]);

  const sendMessage = useCallback(() => {
    const query = input.trim();
    if (!query || isWaiting) return;
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      connect();
      return;
    }

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

    wsRef.current.send(
      JSON.stringify({ query, session_id: sessionId, top_k: 5, role_scope: 'public' })
    );
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
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-violet-500 shadow-glow">
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
            disabled={!input.trim() || isWaiting || !isConnected}
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
