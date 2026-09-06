import React, { useState, useEffect } from 'react';
import { X, FileText, RefreshCw, CheckCircle2, AlertCircle, Loader2, Image as ImageIcon } from 'lucide-react';
import { documentApi } from '../../api/documentApi';
import { fileApi } from '../../api/fileApi';
import { useAuthStore } from '../../stores/useAuthStore';
import clsx from 'clsx';

const DEV_USER_ID = '00000000-0000-0000-0000-000000000001';

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

const FileItem = ({ file, onRemove }) => {
  const [docStatus, setDocStatus] = useState(file.parse_status || 'processing');
  const [failureReason, setFailureReason] = useState(null);
  const [isRetrying, setIsRetrying] = useState(false);
  const [imageError, setImageError] = useState(false);
  const user = useAuthStore((s) => s.user);
  const effectiveUserId = user?.id || DEV_USER_ID;

  useEffect(() => {
    let isMounted = true;
    let pollInterval = null;

    const checkStatus = async () => {
      try {
        const res = await documentApi.getStatus(file.id, effectiveUserId);
        if (!isMounted) return;
        setDocStatus(res.status);
        if (res.failure_reason) {
          setFailureReason(res.failure_reason);
        }
        if (res.status === 'completed' || res.status === 'failed') {
          if (pollInterval) clearInterval(pollInterval);
        }
      } catch (err) {
        // Status endpoint may 404 briefly if DB task hasn't committed yet
      }
    };

    checkStatus();
    pollInterval = setInterval(checkStatus, 2500);

    return () => {
      isMounted = false;
      if (pollInterval) clearInterval(pollInterval);
    };
  }, [file.id, effectiveUserId]);

  const handleRetry = async (e) => {
    e.stopPropagation();
    setIsRetrying(true);
    try {
      await documentApi.retryProcessing(file.id, effectiveUserId);
      setDocStatus('pending');
      setFailureReason(null);
    } catch (err) {
      console.error('[FileList] Retry failed:', err);
    } finally {
      setIsRetrying(false);
    }
  };

  const isImage =
    (file.mime_type && file.mime_type.startsWith('image/')) ||
    ['.png', '.jpg', '.jpeg', '.webp', '.gif'].includes((file.extension || '').toLowerCase()) ||
    /\.(png|jpe?g|webp|gif)$/i.test(file.original_filename || '');

  const fileUrl = fileApi.getFileContentUrl(file.id, effectiveUserId);
  const extLabel = (file.extension || (file.original_filename?.split('.').pop() || '')).replace('.', '').toUpperCase();

  if (isImage) {
    return (
      <div className="group relative flex items-center gap-3 p-2 bg-[#141415] border border-white/[0.08] rounded-xl shadow-sm hover:border-accent/40 transition-all max-w-[280px]">
        {/* Thumbnail Preview */}
        <div className="relative w-12 h-12 rounded-lg bg-black/60 border border-white/[0.08] overflow-hidden shrink-0 flex items-center justify-center">
          {!imageError ? (
            <img
              src={fileUrl}
              alt={file.original_filename}
              onError={() => setImageError(true)}
              className="w-full h-full object-cover"
            />
          ) : (
            <ImageIcon size={18} className="text-[#767676]" />
          )}
        </div>

        {/* File Info */}
        <div className="min-w-0 flex-1 space-y-0.5">
          <div className="text-xs font-semibold text-[#F4F2ED] truncate" title={file.original_filename}>
            {file.original_filename}
          </div>
          <div className="flex items-center gap-1.5 text-[10px] text-[#A0A0A0]">
            <span className="font-semibold text-accent uppercase">{extLabel || 'IMG'}</span>
            <span>·</span>
            <span className="uppercase text-[9px] px-1 rounded bg-white/5 font-mono text-[#F4F2ED]">
              {file.storage_provider || 'local'}
            </span>
            <span>·</span>
            <span>{formatBytes(file.size_bytes)}</span>
          </div>

          {/* Status badge */}
          <div className="flex items-center gap-1 pt-0.5">
            {(docStatus === 'processing' || docStatus === 'pending') && (
              <span className="inline-flex items-center gap-1 text-[9px] text-amber-400 font-medium">
                <Loader2 size={9} className="animate-spin" /> Processing…
              </span>
            )}
            {docStatus === 'completed' && (
              <span className="inline-flex items-center gap-1 text-[9px] text-emerald-400 font-medium">
                <CheckCircle2 size={9} /> Ready
              </span>
            )}
            {docStatus === 'failed' && (
              <div className="inline-flex items-center gap-1 text-[9px] text-red-400 font-medium">
                <span title={failureReason || 'Failed to process'}>Failed</span>
                <button
                  type="button"
                  onClick={handleRetry}
                  disabled={isRetrying}
                  className="text-amber-300 hover:text-amber-200 p-0.5"
                  title="Retry"
                >
                  <RefreshCw size={9} className={clsx(isRetrying && 'animate-spin')} />
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Remove Button */}
        <button
          type="button"
          onClick={() => onRemove(file.id)}
          className="p-1 rounded-md text-[#767676] hover:text-red-400 hover:bg-white/5 transition-colors shrink-0 self-start"
          title="Remove attachment"
        >
          <X size={14} />
        </button>
      </div>
    );
  }

  // Non-image document badge
  return (
    <div className="flex items-center gap-2.5 px-3 py-2 bg-[#141415] rounded-xl border border-white/[0.08] text-xs max-w-[280px] shadow-sm hover:border-accent/40 transition-all">
      <FileText size={16} className="text-accent shrink-0" />

      <div className="min-w-0 flex-1">
        <span className="block truncate text-[#F4F2ED] font-medium" title={file.original_filename}>
          {file.original_filename}
        </span>
        <div className="flex items-center gap-1.5 text-[10px] text-[#A0A0A0] mt-0.5">
          <span className="font-semibold uppercase">{extLabel || 'DOC'}</span>
          <span>·</span>
          <span className="uppercase text-[9px] px-1 rounded bg-white/5 font-mono text-[#F4F2ED]">
            {file.storage_provider || 'local'}
          </span>
          <span>·</span>
          <span>{formatBytes(file.size_bytes)}</span>
        </div>
      </div>

      {/* Status Indicators */}
      {(docStatus === 'processing' || docStatus === 'pending') && (
        <span className="flex items-center gap-1 text-[9px] text-amber-400 bg-amber-400/10 px-1.5 py-0.5 rounded shrink-0">
          <Loader2 size={9} className="animate-spin" />
        </span>
      )}

      {docStatus === 'completed' && (
        <span className="flex items-center gap-1 text-[9px] text-emerald-400 bg-emerald-400/10 px-1.5 py-0.5 rounded shrink-0">
          <CheckCircle2 size={10} />
        </span>
      )}

      {docStatus === 'failed' && (
        <div className="flex items-center gap-1 shrink-0">
          <span
            className="flex items-center gap-1 text-[9px] text-red-400 bg-red-400/10 px-1.5 py-0.5 rounded"
            title={failureReason || 'Parsing failed'}
          >
            <AlertCircle size={10} />
          </span>
          <button
            type="button"
            onClick={handleRetry}
            disabled={isRetrying}
            className="text-xs text-amber-300 hover:text-amber-200 p-0.5 hover:bg-white/5 rounded transition-colors"
            title="Retry processing"
          >
            <RefreshCw size={10} className={clsx(isRetrying && 'animate-spin')} />
          </button>
        </div>
      )}

      <button
        type="button"
        onClick={() => onRemove(file.id)}
        className="text-gray-400 hover:text-red-400 p-1 rounded-md hover:bg-white/5 transition-colors shrink-0"
        title="Remove attachment"
      >
        <X size={14} />
      </button>
    </div>
  );
};

const FileList = ({ files, onRemove }) => {
  if (!files || files.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2.5 mb-3">
      {files.map((file) => (
        <FileItem key={file.id} file={file} onRemove={onRemove} />
      ))}
    </div>
  );
};

export default FileList;
