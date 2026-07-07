import React, { useMemo, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';

// Vite-compatible worker resolution (pdfjs bundled with react-pdf 10).
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url
).toString();

export interface BBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface CitationHighlight {
  page: number; // 1-indexed
  bbox: BBox; // in PDF points (PyMuPDF top-left origin)
  // gold = vector-matched, blue = KG-traversal matched (checklist).
  kind: 'vector' | 'kg';
}

interface DocumentViewerProps {
  fileUrl: string;
  authToken?: string | null;
  highlights?: CitationHighlight[];
  width?: number;
}

const HIGHLIGHT_STYLE: Record<CitationHighlight['kind'], string> = {
  vector: 'rgba(250, 204, 21, 0.32)', // gold
  kg: 'rgba(59, 130, 246, 0.32)', // blue
};
const HIGHLIGHT_BORDER: Record<CitationHighlight['kind'], string> = {
  vector: '#eab308',
  kg: '#3b82f6',
};

export const DocumentViewer: React.FC<DocumentViewerProps> = ({
  fileUrl,
  authToken,
  highlights = [],
  width = 640,
}) => {
  const [numPages, setNumPages] = useState(0);
  const [pageNumber, setPageNumber] = useState(1);
  const [scale, setScale] = useState(1);
  const [error, setError] = useState('');

  // react-pdf re-fetches when `file` identity changes; memoize so auth headers
  // do not trigger an infinite reload loop.
  const file = useMemo(
    () => ({
      url: fileUrl,
      httpHeaders: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
    }),
    [fileUrl, authToken]
  );

  const pageHighlights = highlights.filter((h) => h.page === pageNumber);

  return (
    <div className="flex flex-col items-center">
      {/* Page controls */}
      <div className="flex items-center gap-4 mb-3">
        <button
          type="button"
          onClick={() => setPageNumber((p) => Math.max(1, p - 1))}
          disabled={pageNumber <= 1}
          aria-label="Previous page"
          className="p-1.5 rounded-lg border border-slate-800 bg-slate-900/60 text-slate-300 disabled:opacity-40 hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-amber-400"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <span className="text-xs text-slate-400 font-mono">
          Page {pageNumber} / {numPages || '—'}
        </span>
        <button
          type="button"
          onClick={() => setPageNumber((p) => Math.min(numPages || 1, p + 1))}
          disabled={numPages > 0 && pageNumber >= numPages}
          aria-label="Next page"
          className="p-1.5 rounded-lg border border-slate-800 bg-slate-900/60 text-slate-300 disabled:opacity-40 hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-amber-400"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>

      <div className="relative border border-slate-800 rounded-lg overflow-hidden bg-white">
        <Document
          file={file}
          onLoadSuccess={({ numPages: n }) => setNumPages(n)}
          onLoadError={() => setError('Unable to load the PDF.')}
          loading={
            <div className="flex items-center justify-center h-64 w-[640px]">
              <Loader2 className="w-6 h-6 text-amber-500 animate-spin" />
            </div>
          }
          error={<div className="p-8 text-sm text-red-500">{error || 'Failed to load PDF.'}</div>}
        >
          <div className="relative">
            <Page
              pageNumber={pageNumber}
              width={width}
              renderTextLayer={false}
              renderAnnotationLayer={false}
              onRenderSuccess={(page) => {
                // page.width is the rendered CSS width; originalWidth is the PDF
                // point width. scale converts PDF-point bboxes into CSS px.
                setScale(page.width / page.originalWidth);
              }}
            />
            {/* Citation bounding-box overlays for the current page. */}
            {pageHighlights.map((h, i) => (
              <div
                key={i}
                className="absolute pointer-events-none"
                style={{
                  left: h.bbox.x0 * scale,
                  top: h.bbox.y0 * scale,
                  width: (h.bbox.x1 - h.bbox.x0) * scale,
                  height: (h.bbox.y1 - h.bbox.y0) * scale,
                  backgroundColor: HIGHLIGHT_STYLE[h.kind],
                  border: `1.5px solid ${HIGHLIGHT_BORDER[h.kind]}`,
                  borderRadius: 2,
                }}
              />
            ))}
          </div>
        </Document>
      </div>

      {highlights.length > 0 && (
        <div className="flex items-center gap-4 mt-3 text-[11px] text-slate-400">
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded" style={{ backgroundColor: HIGHLIGHT_STYLE.vector, border: `1px solid ${HIGHLIGHT_BORDER.vector}` }} />
            Vector-matched
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded" style={{ backgroundColor: HIGHLIGHT_STYLE.kg, border: `1px solid ${HIGHLIGHT_BORDER.kg}` }} />
            KG-traversal
          </span>
        </div>
      )}
    </div>
  );
};
