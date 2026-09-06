import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  FolderKanban,
  Plus,
  FileText,
  MessageSquare,
  Brain,
  Search,
  Sparkles,
  Archive,
  RotateCcw,
  Trash2,
  Edit3,
  Check,
  ChevronRight,
  Upload,
  ArrowRight,
  ExternalLink,
  BookOpen,
} from 'lucide-react';
import clsx from 'clsx';
import { projectApi } from '../api/projectApi';
import { useAppStore } from '../stores/useAppStore';
import IntelligenceCore from '../components/IntelligenceCore';

const DEV_USER_ID = '00000000-0000-0000-0000-000000000001';

export default function ProjectsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const activeProjectId = useAppStore((s) => s.activeProjectId);
  const setActiveProject = useAppStore((s) => s.setActiveProject);

  const [selectedProjectId, setSelectedProjectId] = useState(activeProjectId);
  const [showArchived, setShowArchived] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('instructions'); // 'instructions' | 'files' | 'threads' | 'memory' | 'research'

  // Form State
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    custom_instructions: '',
    avatar: '📁',
  });

  // Query: Projects List
  const { data: projects = [], isLoading } = useQuery({
    queryKey: ['projects', showArchived],
    queryFn: () => projectApi.getProjects(showArchived),
  });

  // Effective selected project
  const currentProject = projects.find((p) => p.id === selectedProjectId) || projects[0] || null;

  // Query: Project Details & Sub-resources
  const { data: projectFiles = [] } = useQuery({
    queryKey: ['projectFiles', currentProject?.id],
    queryFn: () => projectApi.getProjectFiles(currentProject.id),
    enabled: !!currentProject?.id && activeTab === 'files',
  });

  const { data: projectThreads = [] } = useQuery({
    queryKey: ['projectThreads', currentProject?.id],
    queryFn: () => projectApi.getProjectThreads(currentProject.id),
    enabled: !!currentProject?.id && activeTab === 'threads',
  });

  const { data: projectMemories = [] } = useQuery({
    queryKey: ['projectMemory', currentProject?.id],
    queryFn: () => projectApi.getProjectMemory(currentProject.id),
    enabled: !!currentProject?.id && activeTab === 'memory',
  });

  const { data: projectResearch = [] } = useQuery({
    queryKey: ['projectResearch', currentProject?.id],
    queryFn: () => projectApi.getProjectResearch(currentProject.id),
    enabled: !!currentProject?.id && activeTab === 'research',
  });

  // Mutations
  const createMutation = useMutation({
    mutationFn: (data) => projectApi.createProject({ ...data, user_id: DEV_USER_ID }),
    onSuccess: (newProject) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      setIsCreateModalOpen(false);
      setSelectedProjectId(newProject.id);
      setActiveProject(newProject);
      setFormData({ name: '', description: '', custom_instructions: '', avatar: '📁' });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }) => projectApi.updateProject(id, data),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      setIsEditModalOpen(false);
      if (activeProjectId === updated.id) {
        setActiveProject(updated);
      }
    },
  });

  const archiveMutation = useMutation({
    mutationFn: (id) => projectApi.archiveProject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      if (activeProjectId === currentProject?.id) {
        setActiveProject(null);
      }
    },
  });

  const restoreMutation = useMutation({
    mutationFn: (id) => projectApi.restoreProject(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['projects'] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id) => projectApi.deleteProject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      if (activeProjectId === currentProject?.id) {
        setActiveProject(null);
      }
      setSelectedProjectId(null);
    },
  });

  const openCreateModal = () => {
    setFormData({ name: '', description: '', custom_instructions: '', avatar: '📁' });
    setIsCreateModalOpen(true);
  };

  const openEditModal = () => {
    if (!currentProject) return;
    setFormData({
      name: currentProject.name || '',
      description: currentProject.description || '',
      custom_instructions: currentProject.custom_instructions || '',
      avatar: currentProject.avatar || '📁',
    });
    setIsEditModalOpen(true);
  };

  const handleStartChatInProject = (project) => {
    setActiveProject(project);
    navigate('/');
  };

  return (
    <div className="flex h-full bg-[#080808] text-[#F4F2ED]">
      {/* ── Left Column: Projects List ────────────────────────── */}
      <div className="w-80 border-r border-white/[0.05] flex flex-col shrink-0 bg-[#0B0B0C]">
        {/* Header */}
        <div className="p-4 border-b border-white/[0.05] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FolderKanban className="text-accent" size={18} />
            <h1 className="font-semibold text-sm text-[#F4F2ED]">Workspaces</h1>
          </div>
          <button
            onClick={openCreateModal}
            className="flex items-center gap-1 text-xs bg-accent text-[#080808] font-semibold px-2.5 py-1.5 rounded-lg hover:bg-[#E7CA82] transition-colors"
          >
            <Plus size={14} /> New
          </button>
        </div>

        {/* Filter / Archive Toggle */}
        <div className="px-4 py-2 border-b border-white/[0.05] flex items-center justify-between text-xs text-[#767676]">
          <span>{projects.length} Workspace{projects.length === 1 ? '' : 's'}</span>
          <button
            onClick={() => setShowArchived(!showArchived)}
            className="hover:text-[#F4F2ED] flex items-center gap-1 transition-colors"
          >
            <Archive size={12} />
            {showArchived ? 'Hide Archived' : 'Show Archived'}
          </button>
        </div>

        {/* Projects List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {isLoading ? (
            <div className="p-8 text-center text-xs text-[#767676]">Loading workspaces…</div>
          ) : projects.length === 0 ? (
            <div className="p-8 text-center space-y-3">
              <IntelligenceCore size="sm" className="mx-auto" />
              <p className="text-xs text-[#A0A0A0]">No workspaces yet.</p>
              <button
                onClick={openCreateModal}
                className="text-xs text-accent hover:underline font-medium"
              >
                Create your first workspace
              </button>
            </div>
          ) : (
            projects.map((p) => {
              const isSelected = currentProject?.id === p.id;
              const isActive = activeProjectId === p.id;
              return (
                <div
                  key={p.id}
                  onClick={() => setSelectedProjectId(p.id)}
                  className={clsx(
                    'group p-3 rounded-xl cursor-pointer border transition-all text-left relative',
                    isSelected
                      ? 'bg-[#141415] border-accent/40 shadow-sm'
                      : 'bg-transparent border-transparent hover:bg-[#101011] hover:border-white/[0.06]'
                  )}
                >
                  <div className="flex items-start gap-2.5">
                    <div className="text-xl shrink-0 mt-0.5">{p.avatar || '📁'}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-1">
                        <span className="font-semibold text-xs text-[#F4F2ED] truncate">
                          {p.name}
                        </span>
                        {isActive && (
                          <span className="shrink-0 text-[10px] bg-accent/15 text-accent border border-accent/30 px-1.5 py-0.5 rounded font-medium">
                            Active
                          </span>
                        )}
                        {p.is_archived && (
                          <span className="shrink-0 text-[10px] bg-red-500/10 text-red-400 px-1.5 py-0.5 rounded">
                            Archived
                          </span>
                        )}
                      </div>
                      {p.description && (
                        <p className="text-[11px] text-[#A0A0A0] line-clamp-1 mt-0.5">
                          {p.description}
                        </p>
                      )}
                      <div className="flex items-center gap-3 mt-2 text-[10px] text-[#767676]">
                        <span className="flex items-center gap-1">
                          <FileText size={10} /> {p.file_count || 0}
                        </span>
                        <span className="flex items-center gap-1">
                          <MessageSquare size={10} /> {p.thread_count || 0}
                        </span>
                        <span className="flex items-center gap-1">
                          <Brain size={10} /> {p.memory_count || 0}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* ── Right Column: Project Workspace Details ───────────────── */}
      {currentProject ? (
        <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#080808]">
          {/* Workspace Header */}
          <div className="p-6 border-b border-white/[0.05] flex items-start justify-between bg-[#0B0B0C] shrink-0">
            <div className="flex items-start gap-3.5">
              <div className="w-12 h-12 rounded-2xl bg-[#141415] border border-white/[0.08] flex items-center justify-center text-2xl shrink-0 shadow-inner">
                {currentProject.avatar || '📁'}
              </div>
              <div className="space-y-1">
                <div className="flex items-center gap-3">
                  <h2 className="text-lg font-bold text-[#F4F2ED]">{currentProject.name}</h2>
                  {activeProjectId === currentProject.id ? (
                    <span className="text-xs bg-accent/15 text-accent border border-accent/30 px-2.5 py-0.5 rounded-full font-medium flex items-center gap-1">
                      <Check size={12} /> Active Workspace
                    </span>
                  ) : (
                    <button
                      onClick={() => setActiveProject(currentProject)}
                      className="text-xs border border-white/[0.08] hover:border-accent/50 text-[#A0A0A0] hover:text-accent px-2.5 py-0.5 rounded-full transition-colors"
                    >
                      Set as Active
                    </button>
                  )}
                </div>
                {currentProject.description && (
                  <p className="text-xs text-[#A0A0A0] max-w-xl">{currentProject.description}</p>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => handleStartChatInProject(currentProject)}
                className="flex items-center gap-1.5 bg-accent text-[#080808] font-semibold text-xs px-3.5 py-2 rounded-xl hover:bg-[#E7CA82] transition-colors shadow-sm"
              >
                <MessageSquare size={14} /> Open Chat <ArrowRight size={13} />
              </button>
              <button
                onClick={openEditModal}
                title="Edit workspace"
                className="p-2 text-[#767676] hover:text-[#F4F2ED] border border-white/[0.08] hover:border-white/[0.15] rounded-xl transition-colors bg-[#101011]"
              >
                <Edit3 size={15} />
              </button>
              {currentProject.is_archived ? (
                <button
                  onClick={() => restoreMutation.mutate(currentProject.id)}
                  title="Restore workspace"
                  className="p-2 text-emerald-400 hover:text-emerald-300 border border-white/[0.08] rounded-xl transition-colors bg-[#101011]"
                >
                  <RotateCcw size={15} />
                </button>
              ) : (
                <button
                  onClick={() => archiveMutation.mutate(currentProject.id)}
                  title="Archive workspace"
                  className="p-2 text-[#767676] hover:text-amber-400 border border-white/[0.08] rounded-xl transition-colors bg-[#101011]"
                >
                  <Archive size={15} />
                </button>
              )}
              <button
                onClick={() => {
                  if (confirm(`Delete project "${currentProject.name}" permanently?`)) {
                    deleteMutation.mutate(currentProject.id);
                  }
                }}
                title="Delete workspace"
                className="p-2 text-[#767676] hover:text-red-400 border border-white/[0.08] rounded-xl transition-colors bg-[#101011]"
              >
                <Trash2 size={15} />
              </button>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="px-6 border-b border-white/[0.05] flex gap-6 text-xs bg-[#0B0B0C] shrink-0">
            {[
              { id: 'instructions', label: 'Instructions & Overview', icon: Sparkles },
              { id: 'files', label: `Files (${currentProject.file_count || 0})`, icon: FileText },
              { id: 'threads', label: `Threads (${currentProject.thread_count || 0})`, icon: MessageSquare },
              { id: 'memory', label: `Memory (${currentProject.memory_count || 0})`, icon: Brain },
              { id: 'research', label: `Deep Research (${currentProject.research_count || 0})`, icon: Search },
            ].map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={clsx(
                    'py-3 border-b-2 flex items-center gap-1.5 font-medium transition-colors',
                    isActive
                      ? 'border-[#D4AF37] text-[#D4AF37]'
                      : 'border-transparent text-[#A8A49A] hover:text-gray-200'
                  )}
                >
                  <Icon size={14} /> {tab.label}
                </button>
              );
            })}
          </div>

          {/* Tab Content */}
          <div className="flex-1 overflow-y-auto p-6">
            {/* ── Tab: Instructions & Overview ── */}
            {activeTab === 'instructions' && (
              <div className="max-w-3xl space-y-6">
                <div className="bg-[#1B1C22] border border-[#2A2D36] rounded-2xl p-5 space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-gray-100 flex items-center gap-2">
                      <Sparkles size={16} className="text-[#D4AF37]" /> Custom AI Instructions
                    </h3>
                    <button
                      onClick={openEditModal}
                      className="text-xs text-[#D4AF37] hover:underline"
                    >
                      Edit Instructions
                    </button>
                  </div>
                  {currentProject.custom_instructions ? (
                    <div className="bg-[#121316] border border-[#26282E] rounded-xl p-4 text-xs font-mono text-gray-300 leading-relaxed whitespace-pre-wrap">
                      {currentProject.custom_instructions}
                    </div>
                  ) : (
                    <div className="text-xs text-[#A8A49A] p-4 bg-[#121316] border border-[#26282E] rounded-xl">
                      No custom instructions defined. The AI will use standard defaults. Add instructions to customize the persona, tone, coding style, or project context.
                    </div>
                  )}
                </div>

                {/* Workspace Stat Grid */}
                <div className="grid grid-cols-4 gap-4">
                  {[
                    { label: 'Attached Files', count: currentProject.file_count || 0, icon: FileText, tab: 'files' },
                    { label: 'Chat Threads', count: currentProject.thread_count || 0, icon: MessageSquare, tab: 'threads' },
                    { label: 'Workspace Memories', count: currentProject.memory_count || 0, icon: Brain, tab: 'memory' },
                    { label: 'Research Runs', count: currentProject.research_count || 0, icon: Search, tab: 'research' },
                  ].map((card) => (
                    <div
                      key={card.label}
                      onClick={() => setActiveTab(card.tab)}
                      className="bg-[#1B1C22] border border-[#2A2D36] rounded-2xl p-4 hover:border-[#D4AF37]/40 cursor-pointer transition-all space-y-1"
                    >
                      <card.icon size={16} className="text-[#D4AF37]" />
                      <div className="text-xl font-bold text-gray-100">{card.count}</div>
                      <div className="text-[11px] text-[#A8A49A]">{card.label}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ── Tab: Files ── */}
            {activeTab === 'files' && (
              <div className="max-w-4xl space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-gray-100">Project Documents & Knowledge Files</h3>
                  <button
                    onClick={() => handleStartChatInProject(currentProject)}
                    className="flex items-center gap-1 text-xs text-[#D4AF37] hover:underline"
                  >
                    <Upload size={13} /> Upload in Chat Dropzone
                  </button>
                </div>
                {projectFiles.length === 0 ? (
                  <div className="bg-[#1B1C22] border border-[#2A2D36] rounded-2xl p-8 text-center space-y-2">
                    <FileText className="text-[#A8A49A] mx-auto" size={32} />
                    <p className="text-xs text-gray-300 font-medium">No files attached to this workspace yet.</p>
                    <p className="text-[11px] text-[#A8A49A]">
                      Upload files from chat while this workspace is active to automatically index them for project-scoped RAG.
                    </p>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    {projectFiles.map((f) => (
                      <div
                        key={f.id}
                        className="bg-[#1B1C22] border border-[#2A2D36] rounded-xl p-3.5 flex items-start justify-between gap-3"
                      >
                        <div className="flex items-start gap-2.5 min-w-0">
                          <FileText className="text-[#D4AF37] shrink-0 mt-0.5" size={18} />
                          <div className="min-w-0">
                            <div className="text-xs font-semibold text-gray-200 truncate">
                              {f.original_filename}
                            </div>
                            <div className="text-[10px] text-[#A8A49A] mt-0.5">
                              {(f.size_bytes / 1024).toFixed(1)} KB · {f.mime_type}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── Tab: Threads ── */}
            {activeTab === 'threads' && (
              <div className="max-w-3xl space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-gray-100">Workspace Conversations</h3>
                  <button
                    onClick={() => handleStartChatInProject(currentProject)}
                    className="flex items-center gap-1 bg-[#D4AF37] text-black font-semibold text-xs px-3 py-1.5 rounded-lg hover:opacity-90"
                  >
                    <Plus size={14} /> New Thread
                  </button>
                </div>
                {projectThreads.length === 0 ? (
                  <div className="bg-[#1B1C22] border border-[#2A2D36] rounded-2xl p-8 text-center space-y-2">
                    <MessageSquare className="text-[#A8A49A] mx-auto" size={32} />
                    <p className="text-xs text-gray-300 font-medium">No threads in this workspace yet.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {projectThreads.map((t) => (
                      <div
                        key={t.id}
                        onClick={() => {
                          setActiveProject(currentProject);
                          navigate(`/chat/${t.id}`);
                        }}
                        className="bg-[#1B1C22] border border-[#2A2D36] hover:border-[#D4AF37]/50 rounded-xl p-3.5 flex items-center justify-between cursor-pointer transition-all"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <MessageSquare size={16} className="text-[#D4AF37] shrink-0" />
                          <span className="text-xs font-medium text-gray-200 truncate">
                            {t.title || 'Untitled Chat'}
                          </span>
                        </div>
                        <ChevronRight size={14} className="text-[#A8A49A]" />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── Tab: Memory ── */}
            {activeTab === 'memory' && (
              <div className="max-w-3xl space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-gray-100">Project-Isolated Long-Term Memory</h3>
                  <button
                    onClick={() => navigate('/memory')}
                    className="text-xs text-[#D4AF37] hover:underline flex items-center gap-1"
                  >
                    Manage in Memory Hub <ExternalLink size={12} />
                  </button>
                </div>
                {projectMemories.length === 0 ? (
                  <div className="bg-[#1B1C22] border border-[#2A2D36] rounded-2xl p-8 text-center space-y-2">
                    <Brain className="text-[#A8A49A] mx-auto" size={32} />
                    <p className="text-xs text-gray-300 font-medium">No project memories stored yet.</p>
                    <p className="text-[11px] text-[#A8A49A]">
                      Facts and preferences mentioned while chatting in this workspace will be automatically extracted and scoped here.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {projectMemories.map((m) => (
                      <div
                        key={m.id}
                        className="bg-[#1B1C22] border border-[#2A2D36] rounded-xl p-3.5 flex items-start justify-between gap-3"
                      >
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] font-mono bg-[#2A2D36] text-[#D4AF37] px-2 py-0.5 rounded">
                              {m.category}
                            </span>
                            <span className="text-xs font-semibold text-gray-200">{m.key}</span>
                          </div>
                          <p className="text-xs text-[#A8A49A]">{m.value}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── Tab: Research History ── */}
            {activeTab === 'research' && (
              <div className="max-w-3xl space-y-4">
                <h3 className="text-sm font-semibold text-gray-100">Deep Research History</h3>
                {projectResearch.length === 0 ? (
                  <div className="bg-[#1B1C22] border border-[#2A2D36] rounded-2xl p-8 text-center space-y-2">
                    <Search className="text-[#A8A49A] mx-auto" size={32} />
                    <p className="text-xs text-gray-300 font-medium">No research runs in this workspace yet.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {projectResearch.map((r) => (
                      <div
                        key={r.id}
                        onClick={() => {
                          setActiveProject(currentProject);
                          navigate(`/chat/${r.thread_id}`);
                        }}
                        className="bg-[#1B1C22] border border-[#2A2D36] hover:border-[#D4AF37]/50 rounded-xl p-4 cursor-pointer transition-all space-y-2"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-gray-100">{r.query}</span>
                          <span className="text-[10px] bg-emerald-500/15 text-emerald-400 px-2 py-0.5 rounded font-mono">
                            {r.status}
                          </span>
                        </div>
                        <div className="flex items-center gap-4 text-[11px] text-[#A8A49A]">
                          <span>{r.source_count || 0} Sources</span>
                          <span>{r.task_count || 0} Sub-tasks</span>
                          <span>{Math.round((r.confidence || 0) * 100)}% Confidence</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center text-center p-8 space-y-3">
          <FolderKanban size={40} className="text-[#A8A49A]" />
          <h2 className="text-base font-semibold text-gray-200">No workspace selected</h2>
          <p className="text-xs text-[#A8A49A]">Select a workspace on the left or create a new one.</p>
          <button
            onClick={openCreateModal}
            className="text-xs bg-[#D4AF37] text-black font-semibold px-4 py-2 rounded-xl hover:opacity-90"
          >
            Create Workspace
          </button>
        </div>
      )}

      {/* ── Modal: Create Project ────────────────────────────── */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#1A1B20] border border-[#2C2F38] rounded-2xl max-w-lg w-full p-6 space-y-5 shadow-2xl">
            <div className="flex items-center justify-between border-b border-[#2C2F38] pb-3">
              <h3 className="text-sm font-bold text-gray-100 flex items-center gap-2">
                <FolderKanban size={16} className="text-[#D4AF37]" /> New Project Workspace
              </h3>
              <button
                onClick={() => setIsCreateModalOpen(false)}
                className="text-[#A8A49A] hover:text-gray-200 text-xs"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div className="flex gap-3">
                <div className="w-16 space-y-1">
                  <label className="text-[#A8A49A]">Icon</label>
                  <input
                    type="text"
                    value={formData.avatar}
                    onChange={(e) => setFormData({ ...formData, avatar: e.target.value })}
                    className="w-full bg-[#121316] border border-[#2C2F38] rounded-xl p-2 text-center text-xl outline-none focus:border-[#D4AF37]"
                    maxLength={4}
                  />
                </div>
                <div className="flex-1 space-y-1">
                  <label className="text-[#A8A49A]">Workspace Name *</label>
                  <input
                    type="text"
                    placeholder="e.g., TARK AI Core"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full bg-[#121316] border border-[#2C2F38] rounded-xl px-3 py-2 text-gray-200 outline-none focus:border-[#D4AF37]"
                    autoFocus
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-[#A8A49A]">Description</label>
                <input
                  type="text"
                  placeholder="e.g., Core architecture and algorithms"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className="w-full bg-[#121316] border border-[#2C2F38] rounded-xl px-3 py-2 text-gray-200 outline-none focus:border-[#D4AF37]"
                />
              </div>

              <div className="space-y-1">
                <label className="text-[#A8A49A]">Custom AI Instructions (Optional)</label>
                <textarea
                  rows={4}
                  placeholder="e.g., Always reply concisely. Prefer Python code. Use project terminology."
                  value={formData.custom_instructions}
                  onChange={(e) => setFormData({ ...formData, custom_instructions: e.target.value })}
                  className="w-full bg-[#121316] border border-[#2C2F38] rounded-xl p-3 text-gray-200 font-mono text-[11px] outline-none focus:border-[#D4AF37] resize-none"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-[#2C2F38]">
              <button
                onClick={() => setIsCreateModalOpen(false)}
                className="px-4 py-2 text-xs text-[#A8A49A] hover:text-gray-200"
              >
                Cancel
              </button>
              <button
                onClick={() => createMutation.mutate(formData)}
                disabled={!formData.name.trim() || createMutation.isPending}
                className="bg-[#D4AF37] text-black font-semibold text-xs px-4 py-2 rounded-xl hover:opacity-90 disabled:opacity-40"
              >
                {createMutation.isPending ? 'Creating…' : 'Create Workspace'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Edit Project ──────────────────────────────── */}
      {isEditModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#1A1B20] border border-[#2C2F38] rounded-2xl max-w-lg w-full p-6 space-y-5 shadow-2xl">
            <div className="flex items-center justify-between border-b border-[#2C2F38] pb-3">
              <h3 className="text-sm font-bold text-gray-100 flex items-center gap-2">
                <Edit3 size={16} className="text-[#D4AF37]" /> Edit Workspace
              </h3>
              <button
                onClick={() => setIsEditModalOpen(false)}
                className="text-[#A8A49A] hover:text-gray-200 text-xs"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div className="flex gap-3">
                <div className="w-16 space-y-1">
                  <label className="text-[#A8A49A]">Icon</label>
                  <input
                    type="text"
                    value={formData.avatar}
                    onChange={(e) => setFormData({ ...formData, avatar: e.target.value })}
                    className="w-full bg-[#121316] border border-[#2C2F38] rounded-xl p-2 text-center text-xl outline-none focus:border-[#D4AF37]"
                    maxLength={4}
                  />
                </div>
                <div className="flex-1 space-y-1">
                  <label className="text-[#A8A49A]">Workspace Name *</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full bg-[#121316] border border-[#2C2F38] rounded-xl px-3 py-2 text-gray-200 outline-none focus:border-[#D4AF37]"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-[#A8A49A]">Description</label>
                <input
                  type="text"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className="w-full bg-[#121316] border border-[#2C2F38] rounded-xl px-3 py-2 text-gray-200 outline-none focus:border-[#D4AF37]"
                />
              </div>

              <div className="space-y-1">
                <label className="text-[#A8A49A]">Custom AI Instructions</label>
                <textarea
                  rows={5}
                  value={formData.custom_instructions}
                  onChange={(e) => setFormData({ ...formData, custom_instructions: e.target.value })}
                  className="w-full bg-[#121316] border border-[#2C2F38] rounded-xl p-3 text-gray-200 font-mono text-[11px] outline-none focus:border-[#D4AF37] resize-none"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-[#2C2F38]">
              <button
                onClick={() => setIsEditModalOpen(false)}
                className="px-4 py-2 text-xs text-[#A8A49A] hover:text-gray-200"
              >
                Cancel
              </button>
              <button
                onClick={() =>
                  updateMutation.mutate({
                    id: currentProject.id,
                    data: formData,
                  })
                }
                disabled={!formData.name.trim() || updateMutation.isPending}
                className="bg-[#D4AF37] text-black font-semibold text-xs px-4 py-2 rounded-xl hover:opacity-90 disabled:opacity-40"
              >
                {updateMutation.isPending ? 'Saving…' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
