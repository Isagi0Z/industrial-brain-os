import React, { useState, useRef } from 'react';
import { UploadCloud, File as FileIcon, X, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { Card } from '../ui/card';
import { Button } from '../ui/button';
import { cn } from '../../lib/utils';

const ACCEPTED_EXTENSIONS = '.pdf,.docx,.doc,.xlsx,.xls,.png,.jpg,.jpeg';
const ACCEPTED_MIME_TYPES = [
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'image/jpeg',
  'image/png',
];
const MAX_SIZE_BYTES = 100 * 1024 * 1024; // 100 MB

type UploadStatus = 'idle' | 'uploading' | 'success' | 'error';

interface UploadedDocument {
  id: string;
  original_filename: string;
  status: string;
  job_status: string | null;
}

interface Props {
  onUploadComplete?: () => void;
}

export const DocumentUpload: React.FC<Props> = ({ onUploadComplete }) => {
  const [dragActive, setDragActive] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const [uploadedDoc, setUploadedDoc] = useState<UploadedDocument | null>(null);

  const { token } = useAuth();
  const inputRef = useRef<HTMLInputElement>(null);

  const validateFile = (file: File): string | null => {
    if (file.size > MAX_SIZE_BYTES) {
      return `File exceeds the 100 MB limit (${(file.size / 1024 / 1024).toFixed(1)} MB).`;
    }
    if (!ACCEPTED_MIME_TYPES.includes(file.type)) {
      return `File type "${file.type}" is not accepted. Upload PDF, DOCX, XLSX, PNG, or JPEG.`;
    }
    return null;
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    const dropped = Array.from(e.dataTransfer.files);
    setFiles(dropped.slice(0, 1)); // single file per upload
    setUploadStatus('idle');
    setErrorMessage('');
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files?.[0]) {
      setFiles(Array.from(e.target.files).slice(0, 1));
      setUploadStatus('idle');
      setErrorMessage('');
    }
  };

  const removeFile = () => {
    setFiles([]);
    setUploadStatus('idle');
    setErrorMessage('');
  };

  const uploadFiles = async () => {
    const file = files[0];
    if (!file) return;

    const validationError = validateFile(file);
    if (validationError) {
      setUploadStatus('error');
      setErrorMessage(validationError);
      return;
    }

    setUploadStatus('uploading');
    setUploadProgress(0);
    setErrorMessage('');

    const formData = new FormData();
    formData.append('file', file);

    // Simulate progress until fetch completes
    const interval = setInterval(() => {
      setUploadProgress((prev) => (prev >= 85 ? prev : prev + 10));
    }, 200);

    try {
      const response = await fetch('/api/v1/documents/', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      clearInterval(interval);
      setUploadProgress(100);

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || errorData.message || 'Upload failed');
      }

      const data = await response.json() as UploadedDocument;
      setUploadedDoc(data);
      setUploadStatus('success');
      onUploadComplete?.();

      setTimeout(() => {
        setFiles([]);
        setUploadStatus('idle');
        setUploadProgress(0);
        setUploadedDoc(null);
      }, 4000);
    } catch (err: unknown) {
      clearInterval(interval);
      setUploadStatus('error');
      setErrorMessage(err instanceof Error ? err.message : 'An unexpected error occurred.');
    }
  };

  return (
    <Card className="mx-auto max-w-2xl p-6">
      <h2 className="text-base font-semibold">Upload Document</h2>
      <p className="mb-4 mt-1 text-xs text-muted-foreground">
        PDF · DOCX · XLSX · PNG · JPEG — max 100 MB
      </p>

      <div
        className={cn(
          'relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 transition-colors',
          dragActive
            ? 'border-primary bg-primary/5'
            : 'border-border bg-secondary/30 hover:bg-secondary/50'
        )}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <div
          className={cn(
            'mb-4 flex h-14 w-14 items-center justify-center rounded-2xl transition-colors',
            dragActive ? 'bg-primary/15' : 'bg-secondary'
          )}
        >
          <UploadCloud className={cn('h-7 w-7', dragActive ? 'text-primary' : 'text-muted-foreground')} />
        </div>
        <p className="text-sm text-foreground">Drag and drop your file here</p>
        <p className="mb-4 mt-1 text-xs text-muted-foreground">or</p>
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          onChange={handleChange}
          accept={ACCEPTED_EXTENSIONS}
        />
        <Button variant="secondary" size="sm" onClick={() => inputRef.current?.click()}>
          Browse files
        </Button>
      </div>

      {files.length > 0 && (
        <div className="mt-6 space-y-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Selected file
          </h3>

          <div className="flex items-center justify-between rounded-lg border border-border bg-secondary/40 p-3">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
                <FileIcon className="h-4 w-4" />
              </div>
              <div>
                <p className="max-w-[300px] truncate text-sm font-medium text-foreground">{files[0].name}</p>
                <p className="text-xs text-muted-foreground">{(files[0].size / (1024 * 1024)).toFixed(2)} MB</p>
              </div>
            </div>
            {uploadStatus === 'idle' && (
              <Button variant="ghost" size="icon" onClick={removeFile} className="h-8 w-8" aria-label="Remove file">
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>

          {uploadStatus === 'uploading' && (
            <div className="space-y-1">
              <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
                <div
                  className="h-2 rounded-full bg-gradient-to-r from-primary to-violet-500 transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
              <p className="text-right text-xs text-muted-foreground">{uploadProgress}%</p>
            </div>
          )}

          {uploadStatus === 'error' && (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          {uploadStatus === 'success' && uploadedDoc && (
            <div className="flex items-center gap-2 rounded-lg border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">
              <CheckCircle className="h-4 w-4 shrink-0" />
              <span>
                <strong>{uploadedDoc.original_filename}</strong> uploaded and queued for processing.
              </span>
            </div>
          )}

          <div className="flex items-center justify-between pt-2">
            {uploadStatus === 'error' && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setUploadStatus('idle');
                  setErrorMessage('');
                }}
              >
                <RefreshCw className="h-4 w-4" /> Clear
              </Button>
            )}
            <div className="ml-auto">
              <Button
                variant="gradient"
                onClick={uploadFiles}
                disabled={uploadStatus === 'uploading' || uploadStatus === 'success'}
              >
                {uploadStatus === 'uploading' ? 'Uploading…' : 'Upload'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
};
