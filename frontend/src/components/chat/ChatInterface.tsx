import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Send, Loader2, MessageSquare, RefreshCw } from 'lucide-react';
import { MessageBubble, Message } from './MessageBubble';
import { Citation } from './CitationCard';
import { useAuth } from '../../context/AuthContext';

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

  return (
    <div className="flex flex-col h-full max-h-[calc(100vh-6rem)] max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-900">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-indigo-500/10 border border-indigo-500/20">
            <MessageSquare className="w-5 h-5 text-indigo-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-slate-100">
              Knowledge Copilot
            </h1>
            <p className="text-xs text-slate-500">
              {isConnected ? (
                <span className="text-emerald-400">Connected</span>
              ) : (
                <span className="text-red-400">Disconnected</span>
              )}
              {lastModel && (
                <span className="ml-2 text-slate-600 font-mono">
                  {lastModel}
                </span>
              )}
            </p>
          </div>
        </div>
        <button
          onClick={resetSession}
          className="p-2 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-900 transition-colors"
          title="New conversation"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4 min-h-0">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center space-y-3 py-12">
            <div className="p-4 rounded-2xl bg-indigo-500/5 border border-indigo-500/10">
              <MessageSquare className="w-8 h-8 text-indigo-500/50" />
            </div>
            <p className="text-slate-500 text-sm max-w-sm">
              Ask a question about your indexed industrial documents. Answers
              are grounded in your document library with citations.
            </p>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-6 py-4 border-t border-slate-900">
        <div className="flex gap-3 items-end rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3 focus-within:border-indigo-500/40 transition-colors">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about a document, equipment, procedure…"
            rows={1}
            className="flex-1 bg-transparent text-sm text-slate-100 placeholder-slate-600 resize-none focus:outline-none leading-relaxed max-h-40"
            style={{ fieldSizing: 'content' } as React.CSSProperties}
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || isWaiting || !isConnected}
            className="flex-shrink-0 p-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-600 text-white transition-colors"
          >
            {isWaiting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </div>
        <p className="text-[10px] text-slate-700 mt-2 text-center">
          Enter to send · Shift+Enter for new line · Answers grounded in
          indexed documents only
        </p>
      </div>
    </div>
  );
};
