import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { ArrowLeft, Save, Trash2, RefreshCw, FileText } from 'lucide-react';
import { DocumentViewer } from './DocumentViewer';
import { UniversalPreview } from './UniversalPreview';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Textarea } from '../ui/input';
import { LoadingState } from '../ui/spinner';
import { FadeIn } from '../ui/motion';

interface DocumentVersion {
  id: string;
  version_number: number;
  size_bytes: number;
  created_at: string;
}

interface DocumentDetail {
  original_filename: string;
  is_deleted: boolean;
  status: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
  sha256_hash: string;
  metadata?: { metadata?: Record<string, unknown> };
  versions?: DocumentVersion[];
}

export const DocumentDetails: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { token } = useAuth();

  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [metadataStr, setMetadataStr] = useState('{}');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const fetchDoc = useCallback(async () => {
    try {
      const res = await fetch(`/api/v1/documents/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json() as DocumentDetail;
        setDoc(data);
        if (data.metadata?.metadata) {
          setMetadataStr(JSON.stringify(data.metadata.metadata, null, 2));
        }
      } else {
        setError('Failed to load document');
      }
    } catch (err) {
      setError('Error fetching document');
    } finally {
      setLoading(false);
    }
  }, [id, token]);

  useEffect(() => {
    fetchDoc();
  }, [fetchDoc]);

  const handleSaveMetadata = async () => {
    setSaving(true);
    try {
      const parsed = JSON.parse(metadataStr);
      const res = await fetch(`/api/v1/documents/${id}/metadata`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(parsed)
      });
      
      if (!res.ok) throw new Error('Failed to save metadata');
      
      fetchDoc();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Invalid JSON format');
    } finally {
      setSaving(false);
    }
  };

  const handleRestore = async () => {
    try {
      await fetch(`/api/v1/documents/${id}/restore`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` }
      });
      fetchDoc();
    } catch (err) {
      console.error('Failed to restore');
    }
  };

  const handleDelete = async () => {
    if (!window.confirm('Soft delete this document?')) return;
    try {
      await fetch(`/api/v1/documents/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });
      fetchDoc();
    } catch (err) {
      console.error('Failed to delete');
    }
  };

  if (loading) return <LoadingState label="Loading document…" />;
  if (!doc)
    return (
      <div className="py-16 text-center text-sm text-destructive">{error || 'Not found'}</div>
    );

  const details = [
    ['Status', doc.status],
    ['MIME type', doc.mime_type],
    ['Size', `${(doc.size_bytes / 1024 / 1024).toFixed(2)} MB`],
    ['Uploaded', new Date(doc.created_at).toLocaleString()],
    ['SHA-256', doc.sha256_hash],
  ] as const;

  return (
    <FadeIn className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="outline" size="icon" onClick={() => navigate('/documents')} aria-label="Back">
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="min-w-0 flex-1 truncate text-xl font-semibold tracking-tight" title={doc.original_filename}>
          {doc.original_filename}
        </h1>
        <Badge variant={doc.is_deleted ? 'destructive' : 'success'}>
          {doc.is_deleted ? 'Deleted' : 'Active'}
        </Badge>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {details.map(([label, value]) => (
              <div key={label} className="grid grid-cols-3 gap-2">
                <span className="font-medium text-muted-foreground">{label}</span>
                <span className="col-span-2 truncate text-foreground" title={String(value)}>
                  {value}
                </span>
              </div>
            ))}
            <div className="pt-3">
              {!doc.is_deleted ? (
                <Button variant="destructive" size="sm" onClick={handleDelete}>
                  <Trash2 className="h-4 w-4" /> Soft delete
                </Button>
              ) : (
                <Button variant="secondary" size="sm" onClick={handleRestore}>
                  <RefreshCw className="h-4 w-4" /> Restore
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="flex flex-col">
          <CardHeader>
            <CardTitle>Metadata (JSON)</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col">
            <Textarea
              className="min-h-[12rem] flex-1 font-mono text-xs"
              value={metadataStr}
              onChange={(e) => setMetadataStr(e.target.value)}
              aria-label="Metadata JSON"
            />
            {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
            <div className="mt-4 flex justify-end">
              <Button onClick={handleSaveMetadata} disabled={saving}>
                <Save className="h-4 w-4" />
                {saving ? 'Saving…' : 'Save metadata'}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {!doc.is_deleted && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-primary" /> Document preview
            </CardTitle>
          </CardHeader>
          <CardContent>
            {doc.mime_type === 'application/pdf' ? (
              <DocumentViewer fileUrl={`/api/v1/documents/${id}/download`} authToken={token} />
            ) : (
              <UniversalPreview
                docId={id as string}
                mimeType={doc.mime_type}
                filename={doc.original_filename}
                token={token}
              />
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Version history</CardTitle>
        </CardHeader>
        <CardContent>
          {doc.versions && doc.versions.length > 0 ? (
            <div className="space-y-2">
              {doc.versions.map((v: DocumentVersion) => (
                <div
                  key={v.id}
                  className="flex items-center justify-between rounded-lg border border-border bg-secondary/40 px-4 py-2.5"
                >
                  <div>
                    <span className="text-sm font-semibold">v{v.version_number}</span>
                    <p className="text-xs text-muted-foreground">
                      Uploaded {new Date(v.created_at).toLocaleString()}
                    </p>
                  </div>
                  <span className="text-sm text-muted-foreground">
                    {(v.size_bytes / 1024 / 1024).toFixed(2)} MB
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No versions found.</p>
          )}
        </CardContent>
      </Card>
    </FadeIn>
  );
};
