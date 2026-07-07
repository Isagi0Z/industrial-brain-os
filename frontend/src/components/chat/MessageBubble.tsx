import React, { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
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

// Pipeline stages surfaced while the answer is being produced — keeps long
// CPU-bound generations feeling alive instead of frozen.
const THINKING_STAGES = [
  'Retrieving documents…',
  'Traversing knowledge graph…',
  'Reranking evidence…',
  'Synthesizing answer…',
];

const ThinkingIndicator: React.FC = () => {
  const [stage, setStage] = useState(0);
  useEffect(() => {
    const t = setInterval(
      () => setStage((s) => Math.min(s + 1, THINKING_STAGES.length - 1)),
      5000,
    );
    return () => clearInterval(t);
  }, []);

  return (
    <div className="flex min-w-[220px] flex-col gap-2 py-0.5">
      <AnimatePresence mode="wait">
        <motion.span
          key={stage}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.25 }}
          className="text-xs text-muted-foreground"
        >
          {THINKING_STAGES[stage]}
        </motion.span>
      </AnimatePresence>
      <div className="ai-shimmer h-1.5 w-full rounded-full" />
    </div>
  );
};

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
          {!isUser && message.isStreaming && !message.content ? (
            <ThinkingIndicator />
          ) : (
            <>
              {message.content}
              {message.isStreaming && (
                <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-primary align-text-bottom" />
              )}
            </>
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
