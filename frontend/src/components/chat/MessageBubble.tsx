import React from 'react';
import { motion } from 'framer-motion';
import { Sparkles, User } from 'lucide-react';
import { CitationCard, Citation } from './CitationCard';
import { cn } from '../../lib/utils';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  isStreaming?: boolean;
}

export const MessageBubble: React.FC<{ message: Message }> = ({ message }) => {
  const isUser = message.role === 'user';

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className={cn('flex gap-3', isUser ? 'flex-row-reverse' : 'flex-row')}
    >
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-xl',
          isUser
            ? 'border border-border bg-secondary'
            : 'bg-gradient-to-br from-primary to-violet-500 shadow-glow'
        )}
      >
        {isUser ? (
          <User className="h-4 w-4 text-muted-foreground" />
        ) : (
          <Sparkles className="h-4 w-4 text-white" />
        )}
      </div>

      <div className={cn('min-w-0 flex-1', isUser && 'flex flex-col items-end')}>
        <div
          className={cn(
            'relative max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-4 py-3 text-sm leading-relaxed',
            isUser
              ? 'bg-primary/15 text-foreground'
              : 'border border-border bg-card text-foreground/90'
          )}
        >
          {message.content}
          {message.isStreaming && (
            <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-primary align-text-bottom" />
          )}
        </div>

        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="w-full max-w-[85%]">
            <CitationCard citations={message.citations} />
          </div>
        )}
      </div>
    </motion.div>
  );
};
