import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { ArrowLeft, Save, Trash2, RefreshCw } from 'lucide-react';

export const DocumentDetails: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { token } = useAuth();
  
  const [doc, setDoc] = useState<any>(null);
  const [metadataStr, setMetadataStr] = useState('{}');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const fetchDoc = async () => {
    try {
      const res = await fetch(`/api/v1/documents/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
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
  };

  useEffect(() => {
    fetchDoc();
  }, [id]);

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
    } catch (err: any) {
      setError(err.message || 'Invalid JSON format');
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

  if (loading) return <div className="p-6 text-center text-gray-500">Loading document details...</div>;
  if (!doc) return <div className="p-6 text-center text-red-500">{error}</div>;

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      <div className="flex items-center space-x-4">
        <button onClick={() => navigate('/dashboard/documents')} className="p-2 hover:bg-gray-100 rounded-full transition-colors">
          <ArrowLeft className="w-5 h-5 text-gray-600" />
        </button>
        <h1 className="text-2xl font-bold text-gray-900">{doc.original_filename}</h1>
        <span className={`px-3 py-1 rounded-full text-xs font-semibold ${doc.is_deleted ? 'bg-red-100 text-red-800' : 'bg-green-100 text-green-800'}`}>
          {doc.is_deleted ? 'DELETED' : 'ACTIVE'}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
          <h2 className="text-lg font-semibold mb-4 text-gray-800">Details</h2>
          <div className="space-y-3 text-sm">
            <div className="grid grid-cols-3 gap-2">
              <span className="text-gray-500 font-medium">Status:</span>
              <span className="col-span-2 text-gray-900">{doc.status}</span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <span className="text-gray-500 font-medium">MIME Type:</span>
              <span className="col-span-2 text-gray-900">{doc.mime_type}</span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <span className="text-gray-500 font-medium">Size:</span>
              <span className="col-span-2 text-gray-900">{(doc.size_bytes / 1024 / 1024).toFixed(2)} MB</span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <span className="text-gray-500 font-medium">Uploaded:</span>
              <span className="col-span-2 text-gray-900">{new Date(doc.created_at).toLocaleString()}</span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <span className="text-gray-500 font-medium">SHA-256:</span>
              <span className="col-span-2 text-gray-900 truncate" title={doc.sha256_hash}>{doc.sha256_hash}</span>
            </div>
          </div>
          
          <div className="mt-6 flex space-x-3">
            {!doc.is_deleted ? (
              <button onClick={handleDelete} className="flex items-center space-x-2 px-4 py-2 bg-red-50 text-red-600 rounded-md hover:bg-red-100 transition-colors">
                <Trash2 className="w-4 h-4" />
                <span>Soft Delete</span>
              </button>
            ) : (
              <button onClick={handleRestore} className="flex items-center space-x-2 px-4 py-2 bg-green-50 text-green-600 rounded-md hover:bg-green-100 transition-colors">
                <RefreshCw className="w-4 h-4" />
                <span>Restore</span>
              </button>
            )}
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200 flex flex-col">
          <h2 className="text-lg font-semibold mb-4 text-gray-800">Metadata Editor (JSON)</h2>
          <textarea
            className="flex-1 w-full p-3 border border-gray-300 rounded-md font-mono text-sm focus:ring-blue-500 focus:border-blue-500 resize-none h-48"
            value={metadataStr}
            onChange={(e) => setMetadataStr(e.target.value)}
          />
          {error && <p className="text-red-500 text-sm mt-2">{error}</p>}
          <div className="mt-4 flex justify-end">
            <button 
              onClick={handleSaveMetadata}
              disabled={saving}
              className="flex items-center space-x-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors disabled:bg-blue-400"
            >
              <Save className="w-4 h-4" />
              <span>{saving ? 'Saving...' : 'Save Metadata'}</span>
            </button>
          </div>
        </div>
      </div>

      <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
        <h2 className="text-lg font-semibold mb-4 text-gray-800">Version History</h2>
        {doc.versions && doc.versions.length > 0 ? (
          <div className="space-y-3">
            {doc.versions.map((v: any) => (
              <div key={v.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-200">
                <div>
                  <span className="font-semibold text-gray-800">v{v.version_number}</span>
                  <p className="text-xs text-gray-500 mt-1">Uploaded {new Date(v.created_at).toLocaleString()}</p>
                </div>
                <span className="text-sm text-gray-600">{(v.size_bytes / 1024 / 1024).toFixed(2)} MB</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-gray-500 text-sm">No versions found.</p>
        )}
      </div>
    </div>
  );
};
