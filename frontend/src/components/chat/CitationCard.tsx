import React, { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ChevronDown, FileText } from 'lucide-react';
import { cn } from '../../lib/utils';

export interface Citation {
  chunk_id: string;
  document_title: string;
  page_number: number | null;
  chunk_text_excerpt: string;
  score: number;
  storage_key: string | null;
}

export const CitationCard: React.FC<{ citations: Citation[] }> = ({ citations }) => {
  const [open, setOpen] = useState(false);
  if (citations.length === 0) return null;

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-border bg-card/60">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-xs font-medium text-primary transition-colors hover:bg-primary/5"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2">
          <FileText className="h-3.5 w-3.5" />
          {citations.length} source{citations.length > 1 ? 's' : ''}
        </span>
        <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-180')} />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="divide-y divide-border/60 border-t border-border"
          >
            {citations.map((c) => (
              <div key={c.chunk_id} className="space-y-1 px-4 py-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-xs font-medium text-foreground">
                    {c.document_title}
                    {c.page_number != null ? `, p.${c.page_number}` : ''}
                  </span>
                  <span className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-[10px] text-primary">
                    {(c.score * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="line-clamp-3 text-[11px] leading-relaxed text-muted-foreground">
                  {c.chunk_text_excerpt}
                </p>
                {c.storage_key && (
                  <a
                    href={`/documents/${c.storage_key}`}
                    className="inline-flex items-center gap-1 text-[10px] text-primary transition-colors hover:underline"
                  >
                    View document →
                  </a>
                )}
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
