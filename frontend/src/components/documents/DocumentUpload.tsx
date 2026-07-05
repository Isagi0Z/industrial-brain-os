import React, { useState, useRef, useCallback } from 'react';
import {
  UploadCloud,
  File as FileIcon,
  X,
  CheckCircle,
  AlertCircle,
  RefreshCw,
  Loader2,
} from 'lucide-react';
import { Card } from '../ui/card';
import { Button } from '../ui/button';
import { cn } from '../../lib/utils';

// Universal ingestion: the backend resolves the real type from extension +
// content, so the UI accepts a broad set and validates primarily by extension
// (browsers send a generic/empty MIME for CSV, Markdown, JSON, ... ).
const ACCEPTED_EXTENSIONS =
  '.pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.csv,.tsv,.txt,.log,.md,.markdown,' +
  '.json,.xml,.html,.htm,.yaml,.yml,.png,.jpg,.jpeg,.gif,.bmp,.tif,.tiff,.webp,' +
  '.eml,.msg,.zip';
const ACCEPTED_EXT_SET = new Set(
  ACCEPTED_EXTENSIONS.split(',').map((e) => e.trim().toLowerCase()),
);
const MAX_SIZE_BYTES = 100 * 1024 * 1024; // 100 MB
// Upload several files at once but bound how many hit the API/worker in parallel
// so a large batch does not overwhelm the ingestion pipeline.
const MAX_CONCURRENT_UPLOADS = 3;

type ItemStatus = 'pending' | 'uploading' | 'success' | 'error';

interface UploadItem {
  id: string;
  file: File;
  status: ItemStatus;
  error?: string;
  docId?: string;
}

let _seq = 0;
const nextId = (): string => {
  _seq += 1;
  return `up_${_seq}_${Math.round(performance.now())}`;
};

interface Props {
  onUploadComplete?: () => void;
}

export const DocumentUpload: React.FC<Props> = ({ onUploadComplete }) => {
  const [dragActive, setDragActive] = useState(false);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const validateFile = (file: File): string | null => {
    if (file.size === 0) {
      return 'File is empty (0 bytes).';
    }
    if (file.size > MAX_SIZE_BYTES) {
      return `Exceeds the 100 MB limit (${(file.size / 1024 / 1024).toFixed(1)} MB).`;
    }
    const dot = file.name.lastIndexOf('.');
    const ext = dot >= 0 ? file.name.slice(dot).toLowerCase() : '';
    if (!ACCEPTED_EXT_SET.has(ext)) {
      return `Type "${ext || file.type || 'unknown'}" is not accepted.`;
    }
    return null;
  };

  // Add files from a drop or the picker: validate each, dedupe against files
  // already staged (by name+size), and keep invalid ones visible with a reason.
  const addFiles = useCallback((incoming: FileList | File[]) => {
    const list = Array.from(incoming);
    if (list.length === 0) return;
    setItems((prev) => {
      // Dedupe on name + size + lastModified so two genuinely different files
      // that merely share a name and byte-size are not silently collapsed.
      const keyOf = (f: File) => `${f.name}:${f.size}:${f.lastModified}`;
      const seen = new Set(prev.map((i) => keyOf(i.file)));
      const additions: UploadItem[] = [];
      for (const file of list) {
        const key = keyOf(file);
        if (seen.has(key)) continue;
        seen.add(key);
        const err = validateFile(file);
        additions.push({
          id: nextId(),
          file,
          status: err ? 'error' : 'pending',
          error: err ?? undefined,
        });
      }
      return [...prev, ...additions];
    });
  }, []);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') setDragActive(true);
    else if (e.type === 'dragleave') setDragActive(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    addFiles(e.dataTransfer.files);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) addFiles(e.target.files);
    // Reset so selecting the same file(s) again still fires onChange.
    e.target.value = '';
  };

  const removeItem = (id: string) =>
    setItems((prev) => prev.filter((i) => i.id !== id));

  const clearAll = () => {
    if (isUploading) return;
    setItems([]);
  };

  const uploadOne = async (item: UploadItem): Promise<void> => {
    setItems((prev) =>
      prev.map((i) =>
        i.id === item.id ? { ...i, status: 'uploading', error: undefined } : i,
      ),
    );
    const formData = new FormData();
    formData.append('file', item.file);
    try {
      // No explicit Authorization header: the global fetch interceptor injects
      // the bearer token and transparently refreshes + retries on a 401, so a
      // long multi-file batch never fails with "token validation failed".
      const res = await fetch('/api/v1/documents/', {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(
          data?.detail || data?.message || `Upload failed (${res.status})`,
        );
      }
      const data = (await res.json()) as { id?: string };
      setItems((prev) =>
        prev.map((i) =>
          i.id === item.id
            ? { ...i, status: 'success', docId: data.id, error: undefined }
            : i,
        ),
      );
    } catch (err: unknown) {
      setItems((prev) =>
        prev.map((i) =>
          i.id === item.id
            ? {
                ...i,
                status: 'error',
                error:
                  err instanceof Error ? err.message : 'An unexpected error occurred.',
              }
            : i,
        ),
      );
    }
  };

  // Upload every pending item with a bounded-concurrency worker pool.
  const runUploads = useCallback(
    async (targets: UploadItem[]) => {
      if (targets.length === 0) return;
      setIsUploading(true);
      const queue = [...targets];
      const worker = async () => {
        for (;;) {
          const next = queue.shift();
          if (!next) return;
          await uploadOne(next);
        }
      };
      const pool = Array.from(
        { length: Math.min(MAX_CONCURRENT_UPLOADS, queue.length) },
        () => worker(),
      );
      await Promise.all(pool);
      setIsUploading(false);
      onUploadComplete?.();
    },
    [onUploadComplete],
  );

  const uploadPending = () =>
    runUploads(items.filter((i) => i.status === 'pending'));

  const retryFailed = () => {
    const failed = items.filter((i) => i.status === 'error' && i.error && !i.docId);
    // Only retry items that failed at upload time (have a file), not validation
    // rejects. Reset them to pending, then run.
    const retryable = failed.filter((i) => validateFile(i.file) === null);
    if (retryable.length === 0) return;
    const ids = new Set(retryable.map((i) => i.id));
    setItems((prev) =>
      prev.map((i) => (ids.has(i.id) ? { ...i, status: 'pending', error: undefined } : i)),
    );
    runUploads(retryable.map((i) => ({ ...i, status: 'pending' as const })));
  };

  const counts = items.reduce(
    (acc, i) => {
      acc[i.status] += 1;
      return acc;
    },
    { pending: 0, uploading: 0, success: 0, error: 0 } as Record<ItemStatus, number>,
  );
  const pendingCount = counts.pending;
  const uploadable = pendingCount > 0 && !isUploading;
  const hasRetryable = items.some(
    (i) => i.status === 'error' && validateFile(i.file) === null,
  );

  return (
    <Card className="mx-auto max-w-2xl p-6">
      <h2 className="text-base font-semibold">Upload Documents</h2>
      <p className="mb-4 mt-1 text-xs text-muted-foreground">
        PDF · Office · CSV · TXT · Markdown · JSON · XML · images · email · ZIP —
        up to 100 MB each · multiple files supported
      </p>

      <div
        className={cn(
          'relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 transition-colors',
          dragActive
            ? 'border-primary bg-primary/5'
            : 'border-border bg-secondary/30 hover:bg-secondary/50',
        )}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <div
          className={cn(
            'mb-4 flex h-14 w-14 items-center justify-center rounded-2xl transition-colors',
            dragActive ? 'bg-primary/15' : 'bg-secondary',
          )}
        >
          <UploadCloud
            className={cn(
              'h-7 w-7',
              dragActive ? 'text-primary' : 'text-muted-foreground',
            )}
          />
        </div>
        <p className="text-sm text-foreground">
          Drag and drop your files here
        </p>
        <p className="mb-4 mt-1 text-xs text-muted-foreground">or</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          onChange={handleChange}
          accept={ACCEPTED_EXTENSIONS}
        />
        <Button
          variant="secondary"
          size="sm"
          onClick={() => inputRef.current?.click()}
        >
          Browse files
        </Button>
      </div>

      {items.length > 0 && (
        <div className="mt-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {items.length} file{items.length > 1 ? 's' : ''}
              {counts.success > 0 && (
                <span className="ml-2 font-normal text-success">
                  {counts.success} uploaded
                </span>
              )}
              {counts.error > 0 && (
                <span className="ml-2 font-normal text-destructive">
                  {counts.error} failed
                </span>
              )}
            </h3>
            {!isUploading && (
              <Button
                variant="ghost"
                size="sm"
                onClick={clearAll}
                className="h-7 text-xs"
              >
                Clear all
              </Button>
            )}
          </div>

          <ul className="space-y-2">
            {items.map((item) => (
              <li
                key={item.id}
                className="flex items-center justify-between gap-3 rounded-lg border border-border bg-secondary/40 p-3"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <div
                    className={cn(
                      'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
                      item.status === 'success' && 'bg-success/15 text-success',
                      item.status === 'error' && 'bg-destructive/15 text-destructive',
                      (item.status === 'pending' || item.status === 'uploading') &&
                        'bg-secondary text-muted-foreground',
                    )}
                  >
                    {item.status === 'uploading' && (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    )}
                    {item.status === 'success' && (
                      <CheckCircle className="h-4 w-4" />
                    )}
                    {item.status === 'error' && (
                      <AlertCircle className="h-4 w-4" />
                    )}
                    {item.status === 'pending' && <FileIcon className="h-4 w-4" />}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-foreground">
                      {item.file.name}
                    </p>
                    <p
                      className={cn(
                        'truncate text-xs',
                        item.status === 'error'
                          ? 'text-destructive'
                          : 'text-muted-foreground',
                      )}
                    >
                      {item.status === 'error' && item.error
                        ? item.error
                        : item.status === 'success'
                          ? 'Uploaded and queued for processing'
                          : item.status === 'uploading'
                            ? 'Uploading…'
                            : `${(item.file.size / (1024 * 1024)).toFixed(2)} MB`}
                    </p>
                  </div>
                </div>
                {!isUploading && item.status !== 'uploading' && (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => removeItem(item.id)}
                    className="h-8 w-8 shrink-0"
                    aria-label={`Remove ${item.file.name}`}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                )}
              </li>
            ))}
          </ul>

          <div className="flex items-center justify-end gap-2 pt-1">
            {hasRetryable && !isUploading && (
              <Button variant="ghost" size="sm" onClick={retryFailed}>
                <RefreshCw className="h-4 w-4" /> Retry failed
              </Button>
            )}
            <Button
              variant="gradient"
              onClick={uploadPending}
              disabled={!uploadable}
            >
              {isUploading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Uploading…
                </>
              ) : pendingCount > 0 ? (
                `Upload ${pendingCount} file${pendingCount > 1 ? 's' : ''}`
              ) : (
                'Upload'
              )}
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
};
