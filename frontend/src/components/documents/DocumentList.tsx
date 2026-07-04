import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Search, Download, Trash2, Eye, RefreshCw, Clock, FileText, Inbox } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Card } from '../ui/card';
import { Badge, type BadgeProps } from '../ui/badge';
import { Button, buttonVariants } from '../ui/button';
import { Input } from '../ui/input';
import { Skeleton } from '../ui/skeleton';
import { EmptyState } from '../ui/empty-state';
import { cn } from '../../lib/utils';

interface Document {
  id: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  job_status: string | null;
  created_at: string;
  updated_at: string;
}

const STATUS_VARIANT: Record<string, BadgeProps['variant']> = {
  UPLOADED: 'secondary',
  VALIDATED: 'default',
  READY_FOR_PROCESSING: 'default',
  PROCESSING: 'warning',
  PROCESSED: 'success',
  ARCHIVED: 'secondary',
  FAILED: 'destructive',
  QUEUED: 'default',
  COMPLETED: 'success',
};

const IN_PROGRESS_STATUSES = new Set(['QUEUED', 'PROCESSING', 'READY_FOR_PROCESSING']);
const POLL_INTERVAL_MS = 5000;

export const DocumentList: React.FC = () => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const { token } = useAuth();
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchDocuments = useCallback(async () => {
    try {
      let url = '/api/v1/documents/?limit=50';
      if (statusFilter) url += `&status=${statusFilter}`;
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json() as { documents: Document[] };
        setDocuments(data.documents);
      }
    } catch (err) {
      console.error('Failed to fetch documents', err);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, token]);

  // Start/stop polling based on whether any document is in-progress
  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  useEffect(() => {
    const hasInProgress = documents.some(
      (d) => IN_PROGRESS_STATUSES.has(d.status) || IN_PROGRESS_STATUSES.has(d.job_status ?? '')
    );

    if (hasInProgress && !pollTimerRef.current) {
      pollTimerRef.current = setInterval(fetchDocuments, POLL_INTERVAL_MS);
    } else if (!hasInProgress && pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [documents, fetchDocuments]);

  const handleDelete = async (id: string) => {
    if (!window.confirm('Are you sure you want to delete this document?')) return;
    try {
      const res = await fetch(`/api/v1/documents/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) fetchDocuments();
    } catch (err) {
      console.error('Failed to delete document', err);
    }
  };

  const handleDownload = async (id: string) => {
    try {
      const res = await fetch(`/api/v1/documents/${id}/download`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        window.open(data.download_url, '_blank');
      }
    } catch (err) {
      console.error('Failed to get download URL', err);
    }
  };

  const handleRetry = async (id: string) => {
    try {
      const res = await fetch(`/api/v1/documents/${id}/retry`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) fetchDocuments();
    } catch (err) {
      console.error('Failed to retry document', err);
    }
  };

  const getDisplayStatus = (doc: Document): string => doc.job_status ?? doc.status;

  const filteredDocs = documents.filter((doc) =>
    doc.original_filename.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-col items-center gap-3 border-b border-border p-4 sm:flex-row sm:justify-between">
        <div className="relative w-full max-w-md">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search documents…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-9"
            aria-label="Search documents"
          />
        </div>

        <div className="flex items-center gap-2">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="Filter by status"
            className="h-10 rounded-lg border border-input bg-background/60 px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="">All statuses</option>
            <option value="UPLOADED">Uploaded</option>
            <option value="READY_FOR_PROCESSING">Queued</option>
            <option value="PROCESSING">Processing</option>
            <option value="PROCESSED">Completed</option>
            <option value="FAILED">Failed</option>
          </select>
          <Button variant="outline" size="icon" onClick={fetchDocuments} title="Refresh" aria-label="Refresh">
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="space-y-3 p-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : filteredDocs.length === 0 ? (
        <div className="p-4">
          <EmptyState
            icon={Inbox}
            title="No documents found"
            description="Upload industrial documents to build your knowledge base."
          />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-[11px] uppercase tracking-wider text-muted-foreground">
                <th className="px-5 py-3 font-medium">Document</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium">Size</th>
                <th className="px-5 py-3 font-medium">Uploaded</th>
                <th className="px-5 py-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredDocs.map((doc) => {
                const displayStatus = getDisplayStatus(doc);
                const isInProgress = IN_PROGRESS_STATUSES.has(displayStatus);
                const isFailed = displayStatus === 'FAILED';

                return (
                  <tr key={doc.id} className="group transition-colors hover:bg-accent/50">
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
                          <FileText className="h-4 w-4" />
                        </div>
                        <div className="min-w-0">
                          <div className="max-w-xs truncate font-medium text-foreground" title={doc.original_filename}>
                            {doc.original_filename}
                          </div>
                          <div className="font-mono text-[10px] text-muted-foreground">{doc.mime_type}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      <Badge variant={STATUS_VARIANT[displayStatus] ?? 'secondary'}>
                        {isInProgress && <Clock className="h-3 w-3 animate-pulse" />}
                        {displayStatus}
                      </Badge>
                    </td>
                    <td className="whitespace-nowrap px-5 py-3 text-muted-foreground">
                      {(doc.size_bytes / 1024 / 1024).toFixed(2)} MB
                    </td>
                    <td className="whitespace-nowrap px-5 py-3 text-muted-foreground">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center justify-end gap-1 opacity-70 transition-opacity group-hover:opacity-100">
                        {isFailed && (
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleRetry(doc.id)}
                            title="Retry processing"
                            className={cn('h-8 w-8 text-amber-500')}
                          >
                            <RefreshCw className="h-4 w-4" />
                          </Button>
                        )}
                        <Link
                          to={`/documents/${doc.id}`}
                          aria-label="View document"
                          title="View"
                          className={cn(buttonVariants({ variant: 'ghost', size: 'icon' }), 'h-8 w-8')}
                        >
                          <Eye className="h-4 w-4" />
                        </Link>
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleDownload(doc.id)} title="Download">
                          <Download className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive hover:text-destructive"
                          onClick={() => handleDelete(doc.id)}
                          title="Delete"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
};
