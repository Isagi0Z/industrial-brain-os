import React from 'react';
import { Bot, User } from 'lucide-react';
import { CitationCard, Citation } from './CitationCard';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  isStreaming?: boolean;
}

interface MessageBubbleProps {
  message: Message;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const isUser = message.role === 'user';

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center ${
          isUser
            ? 'bg-indigo-500/20 border border-indigo-500/30'
            : 'bg-slate-800 border border-slate-700'
        }`}
      >
        {isUser ? (
          <User className="w-4 h-4 text-indigo-400" />
        ) : (
          <Bot className="w-4 h-4 text-slate-300" />
        )}
      </div>

      <div className={`flex-1 min-w-0 ${isUser ? 'flex flex-col items-end' : ''}`}>
        <div
          className={`relative px-4 py-3 rounded-2xl max-w-[85%] text-sm leading-relaxed whitespace-pre-wrap break-words ${
            isUser
              ? 'bg-indigo-600/20 border border-indigo-500/20 text-slate-100'
              : 'bg-slate-900/80 border border-slate-800 text-slate-200'
          }`}
        >
          {message.content}
          {message.isStreaming && (
            <span className="inline-block w-1.5 h-4 ml-0.5 bg-indigo-400 animate-pulse rounded-sm align-text-bottom" />
          )}
        </div>

        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="w-full max-w-[85%]">
            <CitationCard citations={message.citations} />
          </div>
        )}
      </div>
    </div>
  );
};
