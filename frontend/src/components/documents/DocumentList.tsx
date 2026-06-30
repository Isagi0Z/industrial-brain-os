import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Search, Filter, Download, Trash2, Eye, RefreshCw, Clock } from 'lucide-react';
import { Link } from 'react-router-dom';

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

const STATUS_COLORS: Record<string, string> = {
  UPLOADED: 'bg-gray-100 text-gray-700',
  VALIDATED: 'bg-blue-100 text-blue-700',
  READY_FOR_PROCESSING: 'bg-indigo-100 text-indigo-700',
  PROCESSING: 'bg-yellow-100 text-yellow-800',
  PROCESSED: 'bg-green-100 text-green-800',
  ARCHIVED: 'bg-gray-200 text-gray-600',
  FAILED: 'bg-red-100 text-red-800',
  // Job statuses
  QUEUED: 'bg-purple-100 text-purple-800',
  COMPLETED: 'bg-green-100 text-green-800',
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
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      <div className="p-4 border-b border-gray-200 flex flex-col sm:flex-row justify-between items-center gap-4">
        <div className="relative flex-1 max-w-md w-full">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 w-5 h-5" />
          <input
            type="text"
            placeholder="Search documents…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
          />
        </div>

        <div className="flex items-center space-x-2">
          <Filter className="text-gray-400 w-5 h-5" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="border border-gray-300 rounded-md py-2 pl-3 pr-8 focus:ring-blue-500 focus:border-blue-500"
          >
            <option value="">All Statuses</option>
            <option value="UPLOADED">Uploaded</option>
            <option value="READY_FOR_PROCESSING">Queued</option>
            <option value="PROCESSING">Processing</option>
            <option value="PROCESSED">Completed</option>
            <option value="FAILED">Failed</option>
          </select>
          <button
            onClick={fetchDocuments}
            title="Refresh"
            className="p-2 text-gray-400 hover:text-gray-700 rounded-md hover:bg-gray-100"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Filename</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Size</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Uploaded</th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-sm text-gray-500">
                  <div className="flex items-center justify-center space-x-2">
                    <Clock className="w-4 h-4 animate-spin" />
                    <span>Loading documents…</span>
                  </div>
                </td>
              </tr>
            ) : filteredDocs.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-sm text-gray-500">
                  No documents found.
                </td>
              </tr>
            ) : (
              filteredDocs.map((doc) => {
                const displayStatus = getDisplayStatus(doc);
                const isInProgress = IN_PROGRESS_STATUSES.has(displayStatus);
                const isFailed = displayStatus === 'FAILED';

                return (
                  <tr key={doc.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className="text-sm font-medium text-gray-900 truncate max-w-xs block"
                        title={doc.original_filename}
                      >
                        {doc.original_filename}
                      </span>
                      <span className="text-xs text-gray-400">{doc.mime_type}</span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={`px-2 inline-flex items-center gap-1 text-xs leading-5 font-semibold rounded-full ${STATUS_COLORS[displayStatus] ?? 'bg-gray-100 text-gray-700'}`}
                      >
                        {isInProgress && <Clock className="w-3 h-3 animate-pulse" />}
                        {displayStatus}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {(doc.size_bytes / 1024 / 1024).toFixed(2)} MB
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <div className="flex justify-end items-center space-x-3">
                        {isFailed && (
                          <button
                            onClick={() => handleRetry(doc.id)}
                            title="Retry processing"
                            className="text-orange-500 hover:text-orange-700"
                          >
                            <RefreshCw className="w-4 h-4" />
                          </button>
                        )}
                        <Link to={`/dashboard/documents/${doc.id}`} className="text-blue-600 hover:text-blue-900">
                          <Eye className="w-5 h-5" />
                        </Link>
                        <button onClick={() => handleDownload(doc.id)} className="text-gray-600 hover:text-gray-900">
                          <Download className="w-5 h-5" />
                        </button>
                        <button onClick={() => handleDelete(doc.id)} className="text-red-600 hover:text-red-900">
                          <Trash2 className="w-5 h-5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
