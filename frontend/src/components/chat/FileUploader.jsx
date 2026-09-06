import React, { useState, useRef } from 'react';
import { Paperclip } from 'lucide-react';
import { fileApi } from '../../api/fileApi';
import { useAuthStore } from '../../stores/useAuthStore';

// Fallback dev user if unauthenticated
const DEV_USER_ID = '00000000-0000-0000-0000-000000000001';

// Allowed extensions to match backend whitelist
const ACCEPTED_TYPES = '.pdf,.txt,.md,.csv,.docx,.png,.jpg,.jpeg,.gif,.webp';

const FileUploader = ({ onUploadSuccess, storageProvider = 'local', userId, projectId = null }) => {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const fileInputRef = useRef(null);
  const user = useAuthStore((s) => s.user);

  const effectiveUserId = userId || user?.id || DEV_USER_ID;

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setUploadError(null);

    try {
      const uploadedFile = await fileApi.uploadFile(file, effectiveUserId, projectId, storageProvider);
      if (onUploadSuccess) {
        onUploadSuccess(uploadedFile);
      }
    } catch (error) {
      console.error('[FileUploader] Upload failed:', error);
      setUploadError(error.message || 'Upload failed');
      // Clear the error after 4 seconds
      setTimeout(() => setUploadError(null), 4000);
    } finally {
      setIsUploading(false);
      // Reset input so the same file can be re-selected if needed
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  return (
    <div className="relative flex items-center">
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        className="hidden"
        id="file-upload-input"
        accept={ACCEPTED_TYPES}
      />
      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        disabled={isUploading}
        className="p-1 text-muted-foreground hover:text-accent transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        title={isUploading ? 'Uploading…' : 'Attach file'}
      >
        <Paperclip size={15} className={isUploading ? 'animate-pulse' : ''} />
      </button>
      {uploadError && (
        <span className="absolute bottom-8 left-0 text-xs text-red-400 bg-red-400/10 border border-red-400/20 rounded px-2 py-1 whitespace-nowrap z-10">
          {uploadError}
        </span>
      )}
      {isUploading && (
        <span className="absolute bottom-8 left-0 text-xs text-accent bg-background border border-border rounded px-2 py-1 whitespace-nowrap z-10">
          Uploading…
        </span>
      )}
    </div>
  );
};

export default FileUploader;

