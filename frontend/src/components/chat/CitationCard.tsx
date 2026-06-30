import React, { useState } from 'react';
import { ChevronDown, FileText } from 'lucide-react';

export interface Citation {
  chunk_id: string;
  document_title: string;
  page_number: number | null;
  chunk_text_excerpt: string;
  score: number;
  storage_key: string | null;
}

interface CitationCardProps {
  citations: Citation[];
}

export const CitationCard: React.FC<CitationCardProps> = ({ citations }) => {
  const [open, setOpen] = useState(false);

  if (citations.length === 0) return null;

  return (
    <div className="mt-3 rounded-xl border border-indigo-500/20 bg-slate-900/60 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-xs text-indigo-300 hover:bg-indigo-500/5 transition-colors"
      >
        <span className="flex items-center gap-2">
          <FileText className="w-3.5 h-3.5" />
          {citations.length} source{citations.length > 1 ? 's' : ''}
        </span>
        <ChevronDown
          className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div className="border-t border-indigo-500/10 divide-y divide-slate-900/60">
          {citations.map((c) => (
            <div key={c.chunk_id} className="px-4 py-3 space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-200 truncate max-w-[70%]">
                  {c.document_title}
                  {c.page_number != null ? `, p.${c.page_number}` : ''}
                </span>
                <span className="text-[10px] font-mono text-indigo-400 bg-indigo-500/10 px-1.5 py-0.5 rounded">
                  {(c.score * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-[11px] text-slate-400 leading-relaxed line-clamp-3">
                {c.chunk_text_excerpt}
              </p>
              {c.storage_key && (
                <a
                  href={`/documents/${c.storage_key}`}
                  className="inline-flex items-center gap-1 text-[10px] text-indigo-400 hover:text-indigo-300 transition-colors"
                >
                  View document →
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
