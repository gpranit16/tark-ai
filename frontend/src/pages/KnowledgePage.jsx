import { useState, useMemo, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  BookOpen,
  Plus,
  Search,
  Trash2,
  RefreshCw,
  FileText,
  FileCode,
  FileSpreadsheet,
  Image as ImageIcon,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Folder,
  Layers,
  ExternalLink,
  Eye,
  SlidersHorizontal,
  X,
  UploadCloud,
  HardDrive,
  Cloud,
  Database,
  FileCheck,
  AlertTriangle,
  Info,
  Sparkles,
} from 'lucide-react';
import clsx from 'clsx';
import { fileApi } from '../api/fileApi';
import { documentApi } from '../api/documentApi';
import { projectApi } from '../api/projectApi';
import { retrievalApi } from '../api/retrievalApi';
import { useAuthStore } from '../stores/useAuthStore';
import IntelligenceCore from '../components/IntelligenceCore';

const DEV_USER_ID = '00000000-0000-0000-0000-000000000001';

const FILE_TYPE_FILTERS = [
  { id: 'all', label: 'All Types' },
  { id: 'pdf', label: 'PDF', exts: ['.pdf'] },
  { id: 'docs', label: 'Docs', exts: ['.docx', '.txt', '.md', '.pptx'] },
  { id: 'sheets', label: 'Data', exts: ['.csv', '.xlsx'] },
  { id: 'images', label: 'Images', exts: ['.png', '.jpg', '.jpeg', '.webp'] },
  { id: 'code', label: 'Code', exts: ['.py', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.json', '.sql', '.yaml', '.yml', '.xml', '.java', '.cpp', '.c', '.go', '.rs', '.php', '.sh', '.bash', '.toml'] },
];

const STORAGE_FILTERS = [
  { id: 'all', label: 'All Storage' },
  { id: 'local', label: 'Local', icon: HardDrive },
  { id: 'b2', label: 'Backblaze B2', icon: Cloud },
];

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function formatDate(dateString) {
  if (!dateString) return '—';
  try {
    const d = new Date(dateString);
    return d.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateString;
  }
}

function getFileIcon(ext) {
  const cleanExt = (ext || '').toLowerCase();
  if (cleanExt === '.pdf') return <FileText className="text-red-400" size={18} />;
  if (['.docx', '.txt', '.md', '.pptx'].includes(cleanExt)) return <FileText className="text-blue-400" size={18} />;
  if (['.csv', '.xlsx'].includes(cleanExt)) return <FileSpreadsheet className="text-emerald-400" size={18} />;
  if (['.png', '.jpg', '.jpeg', '.webp'].includes(cleanExt)) return <ImageIcon className="text-purple-400" size={18} />;
  if (['.py', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.json', '.sql', '.yaml', '.yml', '.xml', '.java', '.cpp', '.c', '.go', '.rs', '.php', '.sh'].includes(cleanExt)) {
    return <FileCode className="text-amber-400" size={18} />;
  }
  return <FileText className="text-gray-400" size={18} />;
}

export default function KnowledgePage() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const effectiveUserId = user?.id || DEV_USER_ID;

  // Filters & State
  const [searchQuery, setSearchQuery] = useState('');
  const [submittedSearch, setSubmittedSearch] = useState('');
  const [searchMode, setSearchMode] = useState('hybrid'); // hybrid, vector, keyword
  const [selectedProjectId, setSelectedProjectId] = useState('all');
  const [selectedTypeFilter, setSelectedTypeFilter] = useState('all');
  const [selectedStorageFilter, setSelectedStorageFilter] = useState('all');
  const [selectedStatusFilter, setSelectedStatusFilter] = useState('all');
  const [sortBy, setSortBy] = useState('recent'); // recent, oldest, name_asc, name_desc, size_desc

  // Drawer / Modals state
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [documentToDelete, setDocumentToDelete] = useState(null);
  const [uploadProjectTarget, setUploadProjectTarget] = useState('global');
  const [uploadStorageProvider, setUploadStorageProvider] = useState('b2');
  const [uploadFilesQueue, setUploadFilesQueue] = useState([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadErrors, setUploadErrors] = useState([]);
  const fileInputRef = useRef(null);

  // 1. Fetch Projects for filter
  const { data: projectsData } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectApi.getProjects(false),
  });
  const projects = projectsData || [];

  // 2. Fetch User's Real Documents
  const {
    data: filesData,
    isLoading: isFilesLoading,
    isFetching: isFilesFetching,
    isError: isFilesError,
    error: filesError,
    refetch: refetchFiles,
  } = useQuery({
    queryKey: ['knowledge', effectiveUserId, selectedProjectId, selectedStorageFilter],
    queryFn: () =>
      fileApi.getFiles(
        effectiveUserId,
        selectedProjectId === 'all' ? null : selectedProjectId,
        selectedStorageFilter === 'all' ? null : selectedStorageFilter
      ),
    refetchInterval: (query) => {
      // Auto-poll every 3s if any file is still processing
      const hasProcessing = query.state.data?.some(
        (f) => f.parse_status === 'processing' || f.parse_status === 'pending' || f.status === 'uploading'
      );
      return hasProcessing ? 3000 : false;
    },
  });

  const rawFiles = filesData || [];

  // Fetch Storage Statistics
  const { data: storageStatsData } = useQuery({
    queryKey: ['knowledge-storage-stats', effectiveUserId, selectedProjectId],
    queryFn: () => fileApi.getStorageStats(effectiveUserId, selectedProjectId === 'all' ? null : selectedProjectId),
  });

  // 3. Semantic Retrieval Query (when user searches)
  const isSearchActive = Boolean(submittedSearch.trim());
  const {
    data: searchData,
    isLoading: isSearchLoading,
    isError: isSearchError,
    error: searchApiError,
  } = useQuery({
    queryKey: ['knowledge-search', effectiveUserId, submittedSearch, searchMode, selectedProjectId],
    queryFn: async () => {
      if (!submittedSearch.trim()) return null;
      const payload = {
        query: submittedSearch.trim(),
        user_id: effectiveUserId,
        project_id: selectedProjectId === 'all' ? null : selectedProjectId,
        top_k: 12,
      };
      if (searchMode === 'vector') return retrievalApi.vectorSearch(payload);
      if (searchMode === 'keyword') return retrievalApi.keywordSearch(payload);
      return retrievalApi.hybridSearch(payload);
    },
    enabled: isSearchActive,
  });

  const searchResults = searchData?.results || [];

  // Mutations: Delete & Retry
  const deleteMutation = useMutation({
    mutationFn: (fileId) => fileApi.deleteFile(fileId, effectiveUserId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge'] });
      queryClient.invalidateQueries({ queryKey: ['knowledge-search'] });
      setDocumentToDelete(null);
      if (selectedDocument?.id === documentToDelete?.id) {
        setSelectedDocument(null);
      }
    },
  });

  const retryMutation = useMutation({
    mutationFn: (fileId) => documentApi.retryProcessing(fileId, effectiveUserId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge'] });
      if (selectedDocument) {
        // update selected document status optimistically
        setSelectedDocument((prev) => (prev ? { ...prev, parse_status: 'pending' } : null));
      }
    },
  });

  // Calculate Real Statistics
  const stats = useMemo(() => {
    let totalDocs = rawFiles.length;
    let readyCount = 0;
    let processingCount = 0;
    let failedCount = 0;
    let totalBytes = 0;
    let localCount = 0;
    let localBytes = 0;
    let b2Count = 0;
    let b2Bytes = 0;

    for (const f of rawFiles) {
      const size = f.size_bytes || 0;
      totalBytes += size;
      const prov = (f.storage_provider || 'local').toLowerCase();
      if (prov === 'b2') {
        b2Count++;
        b2Bytes += size;
      } else {
        localCount++;
        localBytes += size;
      }

      const status = f.parse_status || (f.status === 'active' ? 'completed' : 'processing');
      if (status === 'completed' || status === 'ready') readyCount++;
      else if (status === 'failed') failedCount++;
      else processingCount++;
    }

    if (storageStatsData) {
      return {
        totalDocs: storageStatsData.total_files ?? totalDocs,
        readyCount: storageStatsData.ready_count ?? readyCount,
        processingCount: storageStatsData.processing_count ?? processingCount,
        failedCount: storageStatsData.failed_count ?? failedCount,
        totalBytes: storageStatsData.total_size_bytes ?? totalBytes,
        localCount: storageStatsData.local_files ?? localCount,
        localBytes: storageStatsData.local_size_bytes ?? localBytes,
        b2Count: storageStatsData.b2_files ?? b2Count,
        b2Bytes: storageStatsData.b2_size_bytes ?? b2Bytes,
      };
    }

    return { totalDocs, readyCount, processingCount, failedCount, totalBytes, localCount, localBytes, b2Count, b2Bytes };
  }, [rawFiles, storageStatsData]);

  // Filter and sort files
  const filteredFiles = useMemo(() => {
    return rawFiles
      .filter((file) => {
        // 1. Type filter
        if (selectedTypeFilter !== 'all') {
          const matchedGroup = FILE_TYPE_FILTERS.find((g) => g.id === selectedTypeFilter);
          if (matchedGroup && !matchedGroup.exts.includes(file.extension.toLowerCase())) {
            return false;
          }
        }
        // 2. Storage provider filter
        if (selectedStorageFilter !== 'all') {
          const prov = (file.storage_provider || 'local').toLowerCase();
          if (prov !== selectedStorageFilter.toLowerCase()) {
            return false;
          }
        }
        // 3. Status filter
        if (selectedStatusFilter !== 'all') {
          const status = file.parse_status || 'completed';
          if (selectedStatusFilter === 'ready' && status !== 'completed') return false;
          if (selectedStatusFilter === 'processing' && status !== 'processing' && status !== 'pending') return false;
          if (selectedStatusFilter === 'failed' && status !== 'failed') return false;
        }
        return true;
      })
      .sort((a, b) => {
        if (sortBy === 'recent') return new Date(b.created_at) - new Date(a.created_at);
        if (sortBy === 'oldest') return new Date(a.created_at) - new Date(b.created_at);
        if (sortBy === 'name_asc') return a.original_filename.localeCompare(b.original_filename);
        if (sortBy === 'name_desc') return b.original_filename.localeCompare(a.original_filename);
        if (sortBy === 'size_desc') return (b.size_bytes || 0) - (a.size_bytes || 0);
        return 0;
      });
  }, [rawFiles, selectedTypeFilter, selectedStorageFilter, selectedStatusFilter, sortBy]);

  // Handle Search Submission
  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setSubmittedSearch(searchQuery.trim());
  };

  const handleClearSearch = () => {
    setSearchQuery('');
    setSubmittedSearch('');
  };

  // Upload Handlers
  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) {
      setUploadFilesQueue((prev) => [...prev, ...files]);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files || []);
    if (files.length > 0) {
      setUploadFilesQueue((prev) => [...prev, ...files]);
    }
  };

  const handleExecuteUpload = async () => {
    if (uploadFilesQueue.length === 0 || isUploading) return;
    setIsUploading(true);
    setUploadErrors([]);

    const projId = uploadProjectTarget === 'global' ? null : uploadProjectTarget;
    const errors = [];

    for (const file of uploadFilesQueue) {
      try {
        await fileApi.uploadFile(file, effectiveUserId, projId, uploadStorageProvider);
      } catch (err) {
        errors.push(`${file.name}: ${err.message || 'Upload failed'}`);
      }
    }

    setIsUploading(false);
    if (errors.length > 0) {
      setUploadErrors(errors);
    } else {
      setUploadFilesQueue([]);
      setIsUploadModalOpen(false);
    }
    queryClient.invalidateQueries({ queryKey: ['knowledge'] });
    queryClient.invalidateQueries({ queryKey: ['knowledge-storage-stats'] });
  };

  return (
    <div className="flex-1 flex overflow-hidden bg-background">
      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-y-auto p-6 md:p-8 space-y-6">
        {/* Header Section */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-border/50">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-accent/10 text-accent">
                <BookOpen size={24} />
              </div>
              <h1 className="text-2xl font-bold tracking-tight text-gray-100">Knowledge Base</h1>
            </div>
            <p className="text-sm text-muted-foreground mt-1">
              Search and manage the knowledge used by TARK AI.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                refetchFiles();
                queryClient.invalidateQueries({ queryKey: ['knowledge-storage-stats'] });
              }}
              title="Refresh Knowledge"
              className="flex items-center gap-2 px-3 py-2 bg-surface2 border border-border rounded-lg text-xs text-gray-300 hover:text-accent hover:border-accent transition-colors"
            >
              <RefreshCw size={14} className={clsx(isFilesFetching && 'animate-spin text-accent')} />
              <span>Refresh</span>
            </button>

            <button
              onClick={() => {
                setUploadFilesQueue([]);
                setUploadErrors([]);
                setIsUploadModalOpen(true);
              }}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-accent text-background text-sm font-semibold hover:bg-accent/90 transition-colors shadow-sm"
            >
              <Plus size={16} />
              Upload Files
            </button>
          </div>
        </div>

        {/* Stats Overview Bar with Storage Statistics */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3.5">
          <div className="p-4 rounded-xl border border-border/60 bg-surface2/40 backdrop-blur-sm space-y-1">
            <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
              <FileCheck size={13} className="text-accent" />
              Total Documents
            </div>
            <div className="text-xl font-bold text-gray-100">{stats.totalDocs}</div>
            <div className="text-[10px] text-muted-foreground">{formatBytes(stats.totalBytes)} total</div>
          </div>

          <div className="p-4 rounded-xl border border-blue-500/30 bg-blue-500/5 backdrop-blur-sm space-y-1">
            <div className="text-[11px] font-medium text-blue-400 uppercase tracking-wider flex items-center gap-1.5">
              <HardDrive size={13} className="text-blue-400" />
              Local Storage
            </div>
            <div className="text-xl font-bold text-blue-300">{stats.localCount}</div>
            <div className="text-[10px] text-blue-400/80">{formatBytes(stats.localBytes)}</div>
          </div>

          <div className="p-4 rounded-xl border border-purple-500/30 bg-purple-500/5 backdrop-blur-sm space-y-1">
            <div className="text-[11px] font-medium text-purple-400 uppercase tracking-wider flex items-center gap-1.5">
              <Cloud size={13} className="text-purple-400" />
              Backblaze B2
            </div>
            <div className="text-xl font-bold text-purple-300">{stats.b2Count}</div>
            <div className="text-[10px] text-purple-400/80">{formatBytes(stats.b2Bytes)}</div>
          </div>

          <div className="p-4 rounded-xl border border-border/60 bg-surface2/40 backdrop-blur-sm space-y-1">
            <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
              <CheckCircle2 size={13} className="text-emerald-400" />
              Ready & Ingested
            </div>
            <div className="text-xl font-bold text-emerald-400">{stats.readyCount}</div>
            <div className="text-[10px] text-muted-foreground">{stats.processingCount} processing</div>
          </div>

          <div className="p-4 rounded-xl border border-border/60 bg-surface2/40 backdrop-blur-sm space-y-1 col-span-2 sm:col-span-1">
            <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
              <Database size={13} className="text-cyan-400" />
              Total Ingested
            </div>
            <div className="text-xl font-bold text-gray-100">{formatBytes(stats.totalBytes)}</div>
            <div className="text-[10px] text-muted-foreground">Local + B2</div>
          </div>
        </div>

        {/* Search & Mode Control Bar */}
        <div className="space-y-3 bg-surface2/30 border border-border/60 rounded-xl p-4">
          <form onSubmit={handleSearchSubmit} className="flex flex-col sm:flex-row gap-2">
            <div className="relative flex-1">
              <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search your knowledge (hybrid semantic & keyword search)..."
                className="w-full pl-10 pr-9 py-2 bg-surface2 border border-border rounded-lg text-xs text-gray-100 placeholder:text-muted-foreground focus:outline-none focus:border-accent"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={handleClearSearch}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-gray-200"
                >
                  <X size={14} />
                </button>
              )}
            </div>

            <div className="flex items-center gap-2">
              <div className="flex items-center bg-surface2 border border-border rounded-lg p-0.5 text-[11px]">
                {['hybrid', 'vector', 'keyword'].map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setSearchMode(mode)}
                    className={clsx(
                      'px-2.5 py-1 rounded capitalize font-medium transition-colors',
                      searchMode === mode
                        ? 'bg-accent/20 text-accent font-semibold'
                        : 'text-gray-400 hover:text-gray-200'
                    )}
                  >
                    {mode}
                  </button>
                ))}
              </div>

              <button
                type="submit"
                className="px-4 py-2 bg-accent text-background rounded-lg text-xs font-semibold hover:bg-accent/90 transition-colors shrink-0"
              >
                Search
              </button>
            </div>
          </form>

          {/* Filter Row: Project Scope, Storage Provider, File Types, Status, Sort */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-border/40 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              {/* Project Scope Filter */}
              <select
                value={selectedProjectId}
                onChange={(e) => setSelectedProjectId(e.target.value)}
                className="px-2.5 py-1.5 bg-surface2 border border-border rounded-lg text-gray-300 text-xs focus:outline-none focus:border-accent"
              >
                <option value="all">All Knowledge</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    Project: {p.name}
                  </option>
                ))}
              </select>

              {/* Storage Provider Filter Pills */}
              <div className="flex items-center gap-1">
                {STORAGE_FILTERS.map((s) => {
                  const Icon = s.icon;
                  const isActive = selectedStorageFilter === s.id;
                  return (
                    <button
                      key={s.id}
                      onClick={() => setSelectedStorageFilter(s.id)}
                      className={clsx(
                        'px-2.5 py-1 rounded-md text-[11px] font-medium whitespace-nowrap transition-colors flex items-center gap-1',
                        isActive
                          ? s.id === 'b2'
                            ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40'
                            : s.id === 'local'
                            ? 'bg-blue-500/20 text-blue-300 border border-blue-500/40'
                            : 'bg-accent/20 text-accent border border-accent/40'
                          : 'bg-surface2 text-gray-400 border border-border/50 hover:text-gray-200'
                      )}
                    >
                      {Icon ? <Icon size={11} /> : null}
                      <span>{s.label}</span>
                    </button>
                  );
                })}
              </div>

              {/* File Type Filter Pills */}
              <div className="flex items-center gap-1 overflow-x-auto">
                {FILE_TYPE_FILTERS.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setSelectedTypeFilter(t.id)}
                    className={clsx(
                      'px-2.5 py-1 rounded-md text-[11px] font-medium whitespace-nowrap transition-colors',
                      selectedTypeFilter === t.id
                        ? 'bg-accent/20 text-accent border border-accent/40'
                        : 'bg-surface2 text-gray-400 border border-border/50 hover:text-gray-200'
                    )}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Sort & Status Right */}
            <div className="flex items-center gap-2">
              <select
                value={selectedStatusFilter}
                onChange={(e) => setSelectedStatusFilter(e.target.value)}
                className="px-2.5 py-1 bg-surface2 border border-border rounded-lg text-gray-400 text-[11px] focus:outline-none focus:border-accent"
              >
                <option value="all">All Statuses</option>
                <option value="ready">Ready only</option>
                <option value="processing">Processing only</option>
                <option value="failed">Failed only</option>
              </select>

              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="px-2.5 py-1 bg-surface2 border border-border rounded-lg text-gray-400 text-[11px] focus:outline-none focus:border-accent"
              >
                <option value="recent">Sort: Most Recent</option>
                <option value="oldest">Sort: Oldest</option>
                <option value="name_asc">Sort: Name (A-Z)</option>
                <option value="name_desc">Sort: Name (Z-A)</option>
                <option value="size_desc">Sort: Size (Largest)</option>
              </select>
            </div>
          </div>
        </div>

        {/* Content View: EITHER Semantic Search Results OR Document Library */}
        {isSearchActive ? (
          /* Semantic Search Results Section */
          <div className="space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-border/50">
              <div className="flex items-center gap-2">
                <Sparkles size={16} className="text-accent" />
                <h2 className="text-sm font-semibold text-gray-100">
                  Search Results for &ldquo;{submittedSearch}&rdquo; ({searchMode})
                </h2>
              </div>
              <button
                onClick={handleClearSearch}
                className="text-xs text-muted-foreground hover:text-accent flex items-center gap-1"
              >
                <X size={12} /> Clear search
              </button>
            </div>

            {isSearchLoading ? (
              <div className="p-12 text-center text-muted-foreground space-y-2">
                <Loader2 size={24} className="animate-spin mx-auto text-accent" />
                <p className="text-xs">Searching documents & embeddings...</p>
              </div>
            ) : isSearchError ? (
              <div className="p-6 rounded-xl border border-red-500/30 bg-red-500/10 text-red-400 text-xs">
                Search failed: {searchApiError?.message || 'Unknown error'}
              </div>
            ) : searchResults.length === 0 ? (
              <div className="p-12 text-center border border-dashed border-border rounded-xl space-y-2">
                <Search size={32} className="mx-auto text-muted-foreground/60" />
                <h3 className="text-sm font-semibold text-gray-200">No relevant knowledge found</h3>
                <p className="text-xs text-muted-foreground">
                  Try another search query or check if your documents have completed processing.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {searchResults.map((res, i) => {
                  const filename = res.metadata?.filename || 'Document';
                  const pageNumber = res.page_number;
                  const similarity = Math.round((res.similarity_score || 0) * 100);

                  return (
                    <div
                      key={res.chunk_id || i}
                      onClick={() => {
                        const matched = rawFiles.find((f) => f.id === res.file_id);
                        if (matched) setSelectedDocument(matched);
                      }}
                      className="p-4 rounded-xl border border-border/60 bg-surface2/50 hover:border-accent/50 transition-all cursor-pointer space-y-2.5"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 truncate">
                          <FileText size={15} className="text-accent shrink-0" />
                          <span className="text-xs font-semibold text-gray-200 truncate">{filename}</span>
                        </div>
                        <span className="text-[10px] px-2 py-0.5 rounded bg-accent/15 text-accent font-semibold">
                          {similarity}% Match
                        </span>
                      </div>

                      <p className="text-xs text-gray-300 line-clamp-3 leading-relaxed bg-background/50 p-2.5 rounded-lg border border-border/40 font-mono text-[11px]">
                        {res.content}
                      </p>

                      <div className="flex items-center justify-between text-[10px] text-muted-foreground pt-1">
                        <span className="font-semibold text-accent/90">
                          [Source: {filename} | Page: {pageNumber}]
                        </span>
                        <span>Chunk #{res.chunk_index}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ) : (
          /* Document Library Table/List */
          <div className="space-y-3">
            {isFilesLoading ? (
              <div className="p-16 text-center text-[#A0A0A0] space-y-4">
                <IntelligenceCore size="md" active={true} className="mx-auto" />
                <p className="text-xs text-[#767676]">Loading knowledge library...</p>
              </div>
            ) : isFilesError ? (
              <div className="p-8 text-center border border-red-500/30 rounded-xl bg-red-500/10 space-y-3">
                <AlertCircle size={32} className="mx-auto text-red-400" />
                <h3 className="text-sm font-semibold text-red-300">Couldn&rsquo;t load your knowledge.</h3>
                <p className="text-xs text-red-400/80">{filesError?.message || 'Failed to fetch files from server.'}</p>
                <button
                  onClick={() => refetchFiles()}
                  className="px-3 py-1.5 bg-red-500/20 border border-red-500/40 rounded-lg text-xs font-semibold text-red-300 hover:bg-red-500/30 transition-colors"
                >
                  Retry Connection
                </button>
              </div>
            ) : filteredFiles.length === 0 ? (
              /* Genuine Empty State */
              <div className="p-16 text-center border border-dashed border-white/[0.08] rounded-2xl bg-[#101011] space-y-4">
                <IntelligenceCore size="md" className="mx-auto" />
                <div className="space-y-1.5 max-w-md mx-auto">
                  <h3 className="text-base font-semibold text-[#F4F2ED]">No knowledge found</h3>
                  <p className="text-xs text-[#A0A0A0] leading-relaxed">
                    {selectedStorageFilter !== 'all' || selectedTypeFilter !== 'all'
                      ? 'No documents match your active filters. Try resetting the filters or upload new files.'
                      : 'Upload documents to build your searchable knowledge base for Chat, RAG, Research, and Coding.'}
                  </p>
                </div>
                <button
                  onClick={() => {
                    setUploadFilesQueue([]);
                    setUploadErrors([]);
                    setIsUploadModalOpen(true);
                  }}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-accent text-[#080808] text-xs font-semibold hover:bg-[#E7CA82] transition-colors shadow-sm"
                >
                  <Plus size={15} />
                  Upload Files
                </button>
              </div>
            ) : (
              /* Documents Grid / Table */
              <div className="border border-border/60 rounded-xl bg-surface2/40 overflow-hidden divide-y divide-border/40">
                {filteredFiles.map((file) => {
                  const status = file.parse_status || 'completed';
                  const isProject = Boolean(file.project_id);
                  const projectName = file.project_name || (isProject ? 'Project Scoped' : 'Global');
                  const isB2 = (file.storage_provider || 'local').toLowerCase() === 'b2';

                  return (
                    <div
                      key={file.id}
                      onClick={() => setSelectedDocument(file)}
                      className={clsx(
                        'flex flex-col sm:flex-row sm:items-center justify-between p-4 gap-3.5 hover:bg-surface2/80 transition-colors cursor-pointer',
                        selectedDocument?.id === file.id && 'bg-surface2/90 border-l-2 border-l-accent'
                      )}
                    >
                      {/* Left: Icon & Name */}
                      <div className="flex items-center gap-3.5 min-w-0 flex-1">
                        <div className="p-2.5 rounded-lg bg-background/70 border border-border/60 shrink-0">
                          {getFileIcon(file.extension)}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-gray-100 truncate" title={file.original_filename}>
                              {file.original_filename}
                            </span>
                          </div>
                          <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground mt-0.5">
                            <span className="font-semibold uppercase tracking-wider">{file.extension.replace('.', '')}</span>
                            <span>·</span>
                            <span>{formatBytes(file.size_bytes)}</span>
                            {file.page_count ? (
                              <>
                                <span>·</span>
                                <span>{file.page_count} {file.page_count === 1 ? 'page' : 'pages'}</span>
                              </>
                            ) : null}
                          </div>
                        </div>
                      </div>

                      {/* Middle: Scope & Storage Badges */}
                      <div className="flex items-center gap-2 shrink-0">
                        {/* Storage Badge */}
                        <span
                          className={clsx(
                            'text-[10px] px-2 py-0.5 rounded font-semibold uppercase tracking-wider flex items-center gap-1 border',
                            isB2
                              ? 'bg-purple-500/15 text-purple-400 border-purple-500/30'
                              : 'bg-blue-500/15 text-blue-400 border-blue-500/30'
                          )}
                        >
                          {isB2 ? <Cloud size={10} /> : <HardDrive size={10} />}
                          <span>{isB2 ? 'B2' : 'LOCAL'}</span>
                        </span>

                        {/* Scope Badge */}
                        <span className="text-[10px] px-2 py-0.5 rounded-md bg-background/60 border border-border/60 text-muted-foreground font-medium flex items-center gap-1">
                          {isProject ? <Folder size={11} className="text-accent" /> : <Layers size={11} />}
                          {isProject ? `PROJECT · ${projectName}` : 'GLOBAL'}
                        </span>
                      </div>

                      {/* Right: Status & Actions */}
                      <div className="flex items-center justify-between sm:justify-end gap-3 shrink-0">
                        {/* Status Badge */}
                        {status === 'completed' && (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                            <CheckCircle2 size={11} /> Ready
                          </span>
                        )}
                        {(status === 'processing' || status === 'pending') && (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30">
                            <Loader2 size={11} className="animate-spin" /> Processing
                          </span>
                        )}
                        {status === 'failed' && (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-red-500/15 text-red-400 border border-red-500/30">
                            <AlertCircle size={11} /> Failed
                          </span>
                        )}

                        {/* Date */}
                        <span className="text-[11px] text-muted-foreground hidden lg:inline">
                          {formatDate(file.created_at)}
                        </span>

                        {/* Action buttons */}
                        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                          <a
                            href={fileApi.getFileContentUrl(file.id, effectiveUserId)}
                            target="_blank"
                            rel="noreferrer"
                            className="p-1.5 rounded text-gray-400 hover:text-accent hover:bg-muted/40 transition-colors"
                            title="Open Preview"
                          >
                            <Eye size={14} />
                          </a>
                          {status === 'failed' && (
                            <button
                              onClick={() => retryMutation.mutate(file.id)}
                              disabled={retryMutation.isPending}
                              className="p-1.5 rounded text-amber-400 hover:text-amber-300 hover:bg-muted/40 transition-colors"
                              title="Retry Processing"
                            >
                              <RefreshCw size={14} className={clsx(retryMutation.isPending && 'animate-spin')} />
                            </button>
                          )}
                          <button
                            onClick={() => setDocumentToDelete(file)}
                            className="p-1.5 rounded text-gray-400 hover:text-red-400 hover:bg-muted/40 transition-colors"
                            title="Delete Document"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Document Details Drawer Panel */}
      {selectedDocument && (
        <aside className="w-80 md:w-96 border-l border-border bg-surface2/95 flex flex-col shrink-0 z-20 transition-all shadow-xl">
          <div className="flex items-center justify-between p-4 border-b border-border/50">
            <h3 className="text-sm font-bold text-gray-100 flex items-center gap-2">
              <Info size={16} className="text-accent" />
              Document Details
            </h3>
            <button
              onClick={() => setSelectedDocument(null)}
              className="p-1 text-muted-foreground hover:text-gray-200 rounded"
            >
              <X size={16} />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-5 space-y-5 text-xs">
            {/* File Header */}
            <div className="p-4 rounded-xl bg-background/70 border border-border/60 space-y-2">
              <div className="flex items-start gap-3">
                <div className="p-2 rounded-lg bg-surface2 border border-border shrink-0">
                  {getFileIcon(selectedDocument.extension)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="font-semibold text-gray-100 break-words">{selectedDocument.original_filename}</div>
                  <div className="text-[11px] text-muted-foreground mt-0.5 font-mono">{formatBytes(selectedDocument.size_bytes)}</div>
                </div>
              </div>
            </div>

            {/* Metadata Fields */}
            <div className="space-y-3 bg-background/40 border border-border/50 rounded-xl p-4">
              <div className="flex justify-between items-center py-1 border-b border-border/30">
                <span className="text-muted-foreground">Scope</span>
                <span className="font-medium text-gray-200">
                  {selectedDocument.project_id ? `Project (${selectedDocument.project_name || 'Scoped'})` : 'Global'}
                </span>
              </div>

              <div className="flex justify-between items-center py-1 border-b border-border/30">
                <span className="text-muted-foreground">Status</span>
                <span className="font-medium capitalize text-accent">
                  {selectedDocument.parse_status || 'Ready'}
                </span>
              </div>

              <div className="flex justify-between items-center py-1 border-b border-border/30">
                <span className="text-muted-foreground">File Format</span>
                <span className="font-mono text-gray-300">{selectedDocument.extension}</span>
              </div>

              <div className="flex justify-between items-center py-1 border-b border-border/30">
                <span className="text-muted-foreground">Storage Location</span>
                <span
                  className={clsx(
                    'px-2 py-0.5 rounded text-[11px] font-semibold uppercase flex items-center gap-1 border',
                    (selectedDocument.storage_provider || 'local').toLowerCase() === 'b2'
                      ? 'bg-purple-500/15 text-purple-300 border-purple-500/30'
                      : 'bg-blue-500/15 text-blue-300 border-blue-500/30'
                  )}
                >
                  {(selectedDocument.storage_provider || 'local').toLowerCase() === 'b2' ? (
                    <>
                      <Cloud size={11} /> Backblaze B2
                    </>
                  ) : (
                    <>
                      <HardDrive size={11} /> Local Storage
                    </>
                  )}
                </span>
              </div>

              {selectedDocument.page_count ? (
                <div className="flex justify-between items-center py-1 border-b border-border/30">
                  <span className="text-muted-foreground">Page Count</span>
                  <span className="font-medium text-gray-200">{selectedDocument.page_count} pages</span>
                </div>
              ) : null}

              {selectedDocument.word_count ? (
                <div className="flex justify-between items-center py-1 border-b border-border/30">
                  <span className="text-muted-foreground">Word Count</span>
                  <span className="font-medium text-gray-200">{selectedDocument.word_count.toLocaleString()} words</span>
                </div>
              ) : null}

              <div className="flex justify-between items-center py-1">
                <span className="text-muted-foreground">Uploaded At</span>
                <span className="text-gray-300">{formatDate(selectedDocument.created_at)}</span>
              </div>
            </div>

            {/* Failure Reason Alert if failed */}
            {selectedDocument.failure_reason && (
              <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl space-y-1 text-red-400">
                <div className="font-semibold flex items-center gap-1.5 text-[11px]">
                  <AlertCircle size={13} /> Parsing Error
                </div>
                <div className="text-[11px] leading-relaxed">{selectedDocument.failure_reason}</div>
              </div>
            )}

            {/* Action Buttons */}
            <div className="space-y-2 pt-2">
              <a
                href={fileApi.getFileContentUrl(selectedDocument.id, effectiveUserId)}
                target="_blank"
                rel="noreferrer"
                className="w-full flex items-center justify-center gap-2 py-2 bg-accent text-background rounded-lg font-semibold hover:bg-accent/90 transition-colors shadow-sm"
              >
                <ExternalLink size={14} />
                Open / Preview Document
              </a>

              {selectedDocument.parse_status === 'failed' && (
                <button
                  onClick={() => retryMutation.mutate(selectedDocument.id)}
                  disabled={retryMutation.isPending}
                  className="w-full flex items-center justify-center gap-2 py-2 bg-amber-500/15 border border-amber-500/30 text-amber-400 rounded-lg font-semibold hover:bg-amber-500/25 transition-colors"
                >
                  <RefreshCw size={14} className={clsx(retryMutation.isPending && 'animate-spin')} />
                  Retry Processing
                </button>
              )}

              <button
                onClick={() => setDocumentToDelete(selectedDocument)}
                className="w-full flex items-center justify-center gap-2 py-2 bg-surface2 border border-red-500/30 text-red-400 rounded-lg font-semibold hover:bg-red-500/10 transition-colors"
              >
                <Trash2 size={14} />
                Delete Document
              </button>
            </div>
          </div>
        </aside>
      )}

      {/* Upload Modal with Per-File Storage Destination Segmented Control */}
      {isUploadModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg bg-surface2 border border-border rounded-2xl p-6 shadow-2xl space-y-5">
            <div className="flex items-center justify-between border-b border-border/50 pb-3">
              <h3 className="text-base font-bold text-gray-100 flex items-center gap-2">
                <UploadCloud size={18} className="text-accent" />
                Upload to Knowledge Base
              </h3>
              <button
                onClick={() => {
                  setIsUploadModalOpen(false);
                  setUploadFilesQueue([]);
                  setUploadErrors([]);
                }}
                className="text-muted-foreground hover:text-gray-200"
              >
                <X size={18} />
              </button>
            </div>

            {/* Storage Selection Segmented Toggle */}
            <div className="space-y-1.5 text-xs">
              <label className="block text-muted-foreground font-medium">Storage Destination</label>
              <div className="grid grid-cols-2 gap-2 p-1 bg-background border border-border rounded-xl">
                <button
                  type="button"
                  onClick={() => setUploadStorageProvider('local')}
                  className={clsx(
                    'flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-semibold transition-all',
                    uploadStorageProvider === 'local'
                      ? 'bg-blue-500/20 text-blue-300 border border-blue-500/40 shadow-sm'
                      : 'text-gray-400 hover:text-gray-200'
                  )}
                >
                  <HardDrive size={14} className={uploadStorageProvider === 'local' ? 'text-blue-400' : ''} />
                  <span>Local Storage</span>
                </button>
                <button
                  type="button"
                  onClick={() => setUploadStorageProvider('b2')}
                  className={clsx(
                    'flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-semibold transition-all',
                    uploadStorageProvider === 'b2'
                      ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40 shadow-sm'
                      : 'text-gray-400 hover:text-gray-200'
                  )}
                >
                  <Cloud size={14} className={uploadStorageProvider === 'b2' ? 'text-purple-400' : ''} />
                  <span>Backblaze B2</span>
                </button>
              </div>
              <p className="text-[11px] text-muted-foreground">
                {uploadStorageProvider === 'b2'
                  ? 'Files will be stored securely in private Backblaze B2 cloud storage.'
                  : 'Files will be stored on the local server filesystem.'}
              </p>
            </div>

            {/* Target Project Selector */}
            <div className="space-y-1.5 text-xs">
              <label className="block text-muted-foreground font-medium">Assign to Workspace / Scope</label>
              <select
                value={uploadProjectTarget}
                onChange={(e) => setUploadProjectTarget(e.target.value)}
                className="w-full px-3 py-2 bg-background border border-border rounded-lg text-gray-200 focus:outline-none focus:border-accent text-xs"
              >
                <option value="global">Global Knowledge (Available in all chats)</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    Project: {p.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Drag & Drop Area */}
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-border/80 hover:border-accent/60 rounded-xl p-8 text-center bg-background/50 cursor-pointer transition-colors space-y-3"
            >
              <input
                type="file"
                multiple
                ref={fileInputRef}
                onChange={handleFileSelect}
                className="hidden"
              />
              <UploadCloud size={32} className="mx-auto text-accent/80" />
              <div className="space-y-1">
                <p className="text-xs font-semibold text-gray-200">
                  Click to select or drag and drop files here
                </p>
                <p className="text-[11px] text-muted-foreground">
                  Supports PDF, DOCX, PPTX, TXT, CSV, XLSX, Code & Images (up to 50MB)
                </p>
              </div>
            </div>

            {/* Selected Files List */}
            {uploadFilesQueue.length > 0 && (
              <div className="space-y-2 max-h-40 overflow-y-auto pr-1">
                <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Files to Upload ({uploadFilesQueue.length})
                </div>
                {uploadFilesQueue.map((f, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-2 rounded-lg bg-background/80 border border-border/50 text-xs"
                  >
                    <div className="flex items-center gap-2 truncate">
                      <FileText size={14} className="text-accent shrink-0" />
                      <span className="truncate text-gray-200">{f.name}</span>
                      <span className="text-[10px] text-muted-foreground">({formatBytes(f.size)})</span>
                    </div>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setUploadFilesQueue((prev) => prev.filter((_, i) => i !== idx));
                      }}
                      className="text-muted-foreground hover:text-red-400 p-1"
                    >
                      <X size={13} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Upload Errors */}
            {uploadErrors.length > 0 && (
              <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl space-y-1 text-red-400 text-xs">
                {uploadErrors.map((err, i) => (
                  <div key={i} className="flex items-start gap-1.5">
                    <AlertCircle size={13} className="shrink-0 mt-0.5" />
                    <span>{err}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Modal Actions */}
            <div className="flex justify-end gap-2 pt-3 border-t border-border/50">
              <button
                type="button"
                onClick={() => {
                  setIsUploadModalOpen(false);
                  setUploadFilesQueue([]);
                }}
                className="px-4 py-2 rounded-lg bg-surface2 border border-border text-xs text-gray-300 hover:text-white"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={uploadFilesQueue.length === 0 || isUploading}
                onClick={handleExecuteUpload}
                className="px-4 py-2 rounded-lg bg-accent text-background text-xs font-semibold hover:bg-accent/90 disabled:opacity-40 transition-colors flex items-center gap-2"
              >
                {isUploading ? (
                  <>
                    <Loader2 size={14} className="animate-spin" /> Uploading to {uploadStorageProvider === 'b2' ? 'B2' : 'Local'}...
                  </>
                ) : (
                  <>Upload {uploadFilesQueue.length > 0 ? `(${uploadFilesQueue.length})` : ''} to {uploadStorageProvider === 'b2' ? 'B2' : 'Local'}</>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {documentToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-surface2 border border-border rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-red-400">
              <div className="p-2 rounded-lg bg-red-500/10 border border-red-500/20">
                <AlertTriangle size={20} />
              </div>
              <h3 className="text-base font-bold text-gray-100">Delete this document?</h3>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              This will remove <strong className="text-gray-200">{documentToDelete.original_filename}</strong> and its searchable knowledge from vector and keyword search.
            </p>
            <div className="flex justify-end gap-2 pt-2 border-t border-border/50 text-xs">
              <button
                type="button"
                onClick={() => setDocumentToDelete(null)}
                className="px-4 py-2 rounded-lg bg-surface2 border border-border text-gray-300 hover:text-white"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={deleteMutation.isPending}
                onClick={() => deleteMutation.mutate(documentToDelete.id)}
                className="px-4 py-2 rounded-lg bg-red-500 text-white font-semibold hover:bg-red-600 transition-colors shadow-sm"
              >
                {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
