import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BookOpen,
  CornerDownLeft,
  FileText,
  GitFork,
  LayoutDashboard,
  Lightbulb,
  Network,
  Search,
  Settings,
  ShieldAlert,
  UploadCloud,
  Wrench,
} from 'lucide-react';
import { cn } from '../../lib/utils';

interface PaletteItem {
  id: string;
  group: 'Navigate' | 'Documents';
  title: string;
  hint?: string;
  icon: React.ComponentType<{ className?: string }>;
  to: string;
}

const NAV_ITEMS: PaletteItem[] = [
  { id: 'nav-overview', group: 'Navigate', title: 'Operations Overview', icon: LayoutDashboard, to: '/overview' },
  { id: 'nav-docs', group: 'Navigate', title: 'Document Hub', hint: 'upload & manage', icon: UploadCloud, to: '/documents' },
  { id: 'nav-copilot', group: 'Navigate', title: 'Knowledge Copilot', hint: 'ask the library', icon: BookOpen, to: '/knowledge' },
  { id: 'nav-graph', group: 'Navigate', title: 'Knowledge Graph', hint: 'explore the ontology', icon: Network, to: '/knowledge-graph' },
  { id: 'nav-maint', group: 'Navigate', title: 'Maintenance Brain', icon: Wrench, to: '/maintenance' },
  { id: 'nav-comp', group: 'Navigate', title: 'Compliance Brain', icon: ShieldAlert, to: '/compliance' },
  { id: 'nav-rca', group: 'Navigate', title: 'Root Cause Analysis', icon: GitFork, to: '/rca' },
  { id: 'nav-lessons', group: 'Navigate', title: 'Lessons Learned', icon: Lightbulb, to: '/lessons-learned' },
  { id: 'nav-settings', group: 'Navigate', title: 'Settings', icon: Settings, to: '/settings' },
];

interface DocRow {
  id: string;
  original_filename: string;
}

export const CommandPalette: React.FC<{
  open: boolean;
  onClose: () => void;
}> = ({ open, onClose }) => {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [cursor, setCursor] = useState(0);
  const [docs, setDocs] = useState<DocRow[]>([]);

  // Load the document list once per open (small library; client-side filter).
  useEffect(() => {
    if (!open) return;
    setQuery('');
    setCursor(0);
    const t = setTimeout(() => inputRef.current?.focus(), 30);
    fetch('/api/v1/documents/?limit=100')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setDocs(d.documents ?? []))
      .catch(() => undefined);
    return () => clearTimeout(t);
  }, [open]);

  const items = useMemo<PaletteItem[]>(() => {
    const q = query.trim().toLowerCase();
    const nav = NAV_ITEMS.filter(
      (i) => !q || i.title.toLowerCase().includes(q) || i.hint?.toLowerCase().includes(q),
    );
    const docItems: PaletteItem[] = (q
      ? docs.filter((d) => d.original_filename.toLowerCase().includes(q))
      : docs.slice(0, 4)
    )
      .slice(0, 6)
      .map((d) => ({
        id: `doc-${d.id}`,
        group: 'Documents' as const,
        title: d.original_filename,
        icon: FileText,
        to: `/documents/${d.id}`,
      }));
    return [...nav, ...docItems];
  }, [query, docs]);

  const run = useCallback(
    (item: PaletteItem | undefined) => {
      if (!item) return;
      onClose();
      navigate(item.to);
    },
    [navigate, onClose],
  );

  // Keyboard handling while open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setCursor((c) => Math.min(c + 1, items.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setCursor((c) => Math.max(c - 1, 0));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        run(items[cursor]);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, items, cursor, run, onClose]);

  useEffect(() => setCursor(0), [query]);

  let lastGroup: string | null = null;

  if (!open) return null;

  return (
    <>
      {
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 pt-[14vh] backdrop-blur-sm"
          onClick={onClose}
          role="dialog"
          aria-modal="true"
          aria-label="Command palette"
        >
          <div
            className="w-full max-w-xl animate-fade-in overflow-hidden rounded-2xl border border-border bg-popover shadow-2xl shadow-primary/10"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 border-b border-border px-4">
              <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Jump to a page or search documents…"
                aria-label="Command palette search"
                className="h-12 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              />
              <kbd className="rounded border border-border bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                esc
              </kbd>
            </div>

            <div className="max-h-[46vh] overflow-y-auto p-2">
              {items.length === 0 && (
                <p className="px-3 py-6 text-center text-sm text-muted-foreground">
                  No matches for “{query}”.
                </p>
              )}
              {items.map((item, i) => {
                const header = item.group !== lastGroup ? item.group : null;
                lastGroup = item.group;
                return (
                  <React.Fragment key={item.id}>
                    {header && (
                      <div className="px-3 pb-1 pt-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/70">
                        {header}
                      </div>
                    )}
                    <button
                      onClick={() => run(item)}
                      onMouseEnter={() => setCursor(i)}
                      className={cn(
                        'flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors',
                        i === cursor
                          ? 'bg-primary/15 text-foreground'
                          : 'text-muted-foreground hover:text-foreground',
                      )}
                    >
                      <item.icon
                        className={cn('h-4 w-4 shrink-0', i === cursor ? 'text-primary' : '')}
                      />
                      <span className="min-w-0 flex-1 truncate">{item.title}</span>
                      {item.hint && (
                        <span className="shrink-0 text-[11px] text-muted-foreground/70">
                          {item.hint}
                        </span>
                      )}
                      {i === cursor && (
                        <CornerDownLeft className="h-3.5 w-3.5 shrink-0 text-primary" />
                      )}
                    </button>
                  </React.Fragment>
                );
              })}
            </div>
          </div>
        </div>
      }
    </>
  );
};
