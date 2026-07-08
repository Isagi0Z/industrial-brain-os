import React, { useCallback, useEffect, useState } from 'react';
import { FileText, Image as ImageIcon, Layers } from 'lucide-react';
import { MarkdownContent } from '../chat/MarkdownContent';
import { Badge } from '../ui/badge';
import { LoadingState } from '../ui/spinner';

/** In-browser preview for every non-PDF document type (PDFs keep the
 * dedicated DocumentViewer with citation jumps):
 *
 * - images       -> rendered directly from the presigned URL
 * - text-like    -> fetched and rendered (markdown formatted, CSV as a
 *                   table, JSON pretty-printed, plain text as-is)
 * - binary office formats (docx/xlsx/pptx/eml/zip) -> the parsed, extracted
 *   content (chunks) — what the AI actually reads — with page/type badges.
 */

interface ChunkRow {
  id: string;
  chunk_index: number;
  chunk_type: string;
  text: string;
  page_number: number | null;
  parent_section_header: string | null;
}

interface Props {
  docId: string;
  mimeType: string;
  filename: string;
  token: string | null;
}

const TEXT_MIMES = new Set([
  'text/plain',
  'text/markdown',
  'text/csv',
  'text/tab-separated-values',
  'application/json',
  'text/xml',
  'application/xml',
  'text/html',
]);

const isImage = (m: string): boolean => m.startsWith('image/');
const isTextLike = (m: string): boolean =>
  TEXT_MIMES.has(m) || m.startsWith('text/');

const CsvTable: React.FC<{ text: string }> = ({ text }) => {
  const rows = text
    .trim()
    .split(/\r?\n/)
    .slice(0, 200)
    .map((line) => line.split(','));
  if (rows.length === 0) return null;
  const [head, ...body] = rows;
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full border-collapse text-xs">
        <thead className="bg-secondary/70">
          <tr>
            {head.map((h, i) => (
              <th key={i} className="border-b border-border px-3 py-2 text-left font-semibold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j} className="border-b border-border/50 px-3 py-1.5 align-top">
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export const UniversalPreview: React.FC<Props> = ({ docId, mimeType, filename, token }) => {
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [chunks, setChunks] = useState<ChunkRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

  const loadChunks = useCallback(async () => {
    const res = await fetch(`/api/v1/documents/${docId}/chunks`, { headers });
    if (!res.ok) throw new Error('chunks unavailable');
    const data = await res.json();
    setChunks((data.chunks as ChunkRow[]) ?? []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId, token]);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      setError('');
      try {
        const res = await fetch(`/api/v1/documents/${docId}/download`, { headers });
        const url = res.ok ? ((await res.json()).download_url as string) : null;
        if (!alive) return;
        setDownloadUrl(url);

        if (url && isImage(mimeType)) {
          // <img> needs no CORS — nothing else to fetch.
        } else if (url && isTextLike(mimeType)) {
          try {
            const raw = await fetch(url);
            if (!raw.ok) throw new Error('raw fetch failed');
            const t = await raw.text();
            if (alive) setText(t.slice(0, 200_000));
          } catch {
            await loadChunks(); // CORS/storage hiccup -> extracted content
          }
        } else {
          await loadChunks(); // binary formats -> extracted content
        }
      } catch {
        if (alive) setError('Preview unavailable for this document.');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId, mimeType, token]);

  if (loading) return <LoadingState label="Preparing preview…" />;
  if (error) return <p className="text-sm text-muted-foreground">{error}</p>;

  if (isImage(mimeType) && downloadUrl) {
    return (
      <div className="space-y-2">
        <Badge variant="outline" className="gap-1.5">
          <ImageIcon className="h-3 w-3" /> image preview
        </Badge>
        <div className="flex justify-center rounded-lg border border-border bg-secondary/30 p-3">
          <img
            src={downloadUrl}
            alt={filename}
            className="max-h-[560px] max-w-full rounded object-contain"
          />
        </div>
      </div>
    );
  }

  if (text !== null) {
    const lower = filename.toLowerCase();
    return (
      <div className="space-y-2">
        <Badge variant="outline" className="gap-1.5">
          <FileText className="h-3 w-3" /> full text preview
        </Badge>
        {lower.endsWith('.md') || lower.endsWith('.markdown') ? (
          <div className="rounded-lg border border-border bg-secondary/20 p-4 text-sm">
            <MarkdownContent text={text} />
          </div>
        ) : lower.endsWith('.csv') ? (
          <CsvTable text={text} />
        ) : lower.endsWith('.json') ? (
          <pre className="max-h-[560px] overflow-auto rounded-lg border border-border bg-secondary/30 p-4 font-mono text-xs">
            {(() => {
              try {
                return JSON.stringify(JSON.parse(text), null, 2);
              } catch {
                return text;
              }
            })()}
          </pre>
        ) : (
          <pre className="max-h-[560px] overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-secondary/30 p-4 text-sm leading-relaxed">
            {text}
          </pre>
        )}
      </div>
    );
  }

  if (chunks) {
    return (
      <div className="space-y-2">
        <Badge variant="outline" className="gap-1.5">
          <Layers className="h-3 w-3" /> extracted content ({chunks.length} chunks) — what the AI reads
        </Badge>
        <div className="max-h-[560px] space-y-2 overflow-y-auto pr-1">
          {chunks.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No extracted content yet — the document may still be processing.
            </p>
          )}
          {chunks.map((c) => (
            <div key={c.id} className="rounded-lg border border-border bg-secondary/30 p-3">
              <div className="mb-1.5 flex items-center gap-2">
                <Badge variant="secondary" className="text-[10px]">
                  {c.chunk_type.toLowerCase()}
                </Badge>
                {c.page_number != null && (
                  <span className="text-[10px] text-muted-foreground">p.{c.page_number}</span>
                )}
                {c.parent_section_header && (
                  <span className="truncate text-[10px] text-muted-foreground">
                    § {c.parent_section_header}
                  </span>
                )}
              </div>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/90">
                {c.text}
              </p>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return <p className="text-sm text-muted-foreground">No preview available.</p>;
};
