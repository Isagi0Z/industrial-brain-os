import React, { useState, useRef } from 'react';
import { UploadCloud, File as FileIcon, X, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

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
    <div className="max-w-2xl mx-auto p-6 bg-white rounded-lg shadow-sm border border-gray-200">
      <h2 className="text-xl font-semibold mb-1 text-gray-800">Upload Document</h2>
      <p className="text-xs text-gray-500 mb-4">PDF · DOCX · XLSX · PNG · JPEG — max 100 MB</p>

      <div
        className={`relative flex flex-col items-center justify-center p-10 border-2 border-dashed rounded-xl transition-colors
          ${dragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300 bg-gray-50 hover:bg-gray-100'}`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <UploadCloud className={`w-12 h-12 mb-4 ${dragActive ? 'text-blue-500' : 'text-gray-400'}`} />
        <p className="text-gray-600 mb-2">Drag and drop your file here</p>
        <p className="text-sm text-gray-500 mb-4">or</p>
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          onChange={handleChange}
          accept={ACCEPTED_EXTENSIONS}
        />
        <button
          onClick={() => inputRef.current?.click()}
          className="px-4 py-2 bg-white border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none"
        >
          Browse Files
        </button>
      </div>

      {files.length > 0 && (
        <div className="mt-6 space-y-4">
          <h3 className="text-sm font-medium text-gray-700">Selected File</h3>

          <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-200">
            <div className="flex items-center space-x-3">
              <FileIcon className="w-5 h-5 text-gray-400 flex-shrink-0" />
              <div>
                <p className="text-sm font-medium text-gray-700 truncate max-w-[300px]">{files[0].name}</p>
                <p className="text-xs text-gray-500">{(files[0].size / (1024 * 1024)).toFixed(2)} MB</p>
              </div>
            </div>
            {uploadStatus === 'idle' && (
              <button onClick={removeFile} className="text-gray-400 hover:text-red-500">
                <X className="w-5 h-5" />
              </button>
            )}
          </div>

          {uploadStatus === 'uploading' && (
            <div className="space-y-1">
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
              <p className="text-xs text-gray-500 text-right">{uploadProgress}%</p>
            </div>
          )}

          {uploadStatus === 'error' && (
            <div className="flex items-start space-x-2 text-red-600 text-sm mt-2">
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          {uploadStatus === 'success' && uploadedDoc && (
            <div className="flex items-center space-x-2 text-green-600 text-sm mt-2">
              <CheckCircle className="w-4 h-4 flex-shrink-0" />
              <span>
                <strong>{uploadedDoc.original_filename}</strong> uploaded and queued for processing.
              </span>
            </div>
          )}

          <div className="flex justify-between items-center pt-4">
            {uploadStatus === 'error' && (
              <button
                onClick={() => { setUploadStatus('idle'); setErrorMessage(''); }}
                className="flex items-center space-x-1 text-sm text-gray-600 hover:text-gray-800"
              >
                <RefreshCw className="w-4 h-4" />
                <span>Clear</span>
              </button>
            )}
            <div className="ml-auto">
              <button
                onClick={uploadFiles}
                disabled={uploadStatus === 'uploading' || uploadStatus === 'success'}
                className={`px-6 py-2 rounded-md text-white font-medium
                  ${uploadStatus === 'uploading' || uploadStatus === 'success'
                    ? 'bg-blue-400 cursor-not-allowed'
                    : 'bg-blue-600 hover:bg-blue-700'}`}
              >
                {uploadStatus === 'uploading' ? 'Uploading…' : 'Upload'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
