import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Brain,
  Plus,
  Search,
  Trash2,
  Edit2,
  CheckCircle2,
  XCircle,
  ToggleLeft,
  ToggleRight,
  Database,
  Sparkles,
  RefreshCw,
  Folder,
  Layers,
  AlertTriangle,
  User,
  Sliders,
  Target,
  GraduationCap,
  MessageSquare,
} from 'lucide-react';
import clsx from 'clsx';
import { listMemories, createMemory, updateMemory, deleteMemory, clearAllMemories } from '../api/memoryApi';
import IntelligenceCore from '../components/IntelligenceCore';

const CATEGORIES = [
  { id: 'all', label: 'All' },
  { id: 'fact', label: 'Personal' },
  { id: 'preference', label: 'Preferences' },
  { id: 'goal', label: 'Goals' },
  { id: 'skill', label: 'Skills' },
  { id: 'project_context', label: 'Projects' },
  { id: 'communication', label: 'Communication' },
  { id: 'other', label: 'Other' },
];

export default function MemoryPage() {
  const queryClient = useQueryClient();
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isMemoryActiveMaster, setIsMemoryActiveMaster] = useState(true);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isClearModalOpen, setIsClearModalOpen] = useState(false);
  const [editingMemory, setEditingMemory] = useState(null);

  // Form state for Add/Edit
  const [formCategory, setFormCategory] = useState('preference');
  const [formKey, setFormKey] = useState('');
  const [formValue, setFormValue] = useState('');
  const [formConfidence, setFormConfidence] = useState(0.95);
  const [formImportance, setFormImportance] = useState(0.85);

  const queryCategory = selectedCategory === 'all' 
    ? null 
    : (selectedCategory === 'communication' ? 'preference' : selectedCategory);

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['memories', selectedCategory, searchQuery],
    queryFn: () =>
      listMemories({
        category: queryCategory,
        search: searchQuery ? searchQuery : (selectedCategory === 'communication' ? 'style' : null),
        limit: 100,
      }),
  });

  const createMutation = useMutation({
    mutationFn: (newMem) => createMemory(newMem),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] });
      setIsAddModalOpen(false);
      resetForm();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, updates }) => updateMemory(id, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] });
      setEditingMemory(null);
      resetForm();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id) => deleteMemory(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] });
    },
  });

  const clearAllMutation = useMutation({
    mutationFn: () => clearAllMemories(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] });
      setIsClearModalOpen(false);
    },
  });

  const resetForm = () => {
    setFormCategory('preference');
    setFormKey('');
    setFormValue('');
    setFormConfidence(0.95);
    setFormImportance(0.85);
  };

  const openAddModal = () => {
    resetForm();
    setIsAddModalOpen(true);
  };

  const openEditModal = (mem) => {
    setEditingMemory(mem);
    setFormCategory(mem.category);
    setFormKey(mem.key);
    setFormValue(mem.value);
    setFormConfidence(mem.confidence);
    setFormImportance(mem.importance);
  };

  const handleSave = (e) => {
    e.preventDefault();
    if (!formKey.trim() || !formValue.trim()) return;

    if (editingMemory) {
      updateMutation.mutate({
        id: editingMemory.id,
        updates: {
          category: formCategory,
          key: formKey.trim(),
          value: formValue.trim(),
          confidence: parseFloat(formConfidence),
          importance: parseFloat(formImportance),
        },
      });
    } else {
      createMutation.mutate({
        category: formCategory,
        key: formKey.trim(),
        value: formValue.trim(),
        confidence: parseFloat(formConfidence),
        importance: parseFloat(formImportance),
        source: 'manual',
      });
    }
  };

  const toggleMemoryActive = (mem) => {
    updateMutation.mutate({
      id: mem.id,
      updates: { is_active: !mem.is_active },
    });
  };

  const memories = data?.items || [];
  const totalCount = data?.total || 0;

  return (
    <div className="flex-1 overflow-y-auto bg-background p-6 md:p-8 space-y-6">
      {/* Header section */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-border/50">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-accent/10 text-accent">
              <Brain size={24} />
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-gray-100">Personal Memory & Context</h1>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            GPT-style intelligent automatic memory and explicit user-controlled personal context.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Master memory status */}
          <button
            onClick={() => setIsMemoryActiveMaster(!isMemoryActiveMaster)}
            className={clsx(
              'flex items-center gap-2 px-3.5 py-1.5 rounded-lg border text-xs font-semibold tracking-wide transition-all',
              isMemoryActiveMaster
                ? 'bg-accent/15 border-accent/40 text-accent'
                : 'bg-surface2 border-border text-muted-foreground'
            )}
          >
            {isMemoryActiveMaster ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
            <span>Memory {isMemoryActiveMaster ? 'Active' : 'Paused'}</span>
          </button>

          {memories.length > 0 && (
            <button
              onClick={() => setIsClearModalOpen(true)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs font-semibold hover:bg-red-500/20 transition-colors"
              title="Forget all memories"
            >
              <Trash2 size={14} />
              Clear All
            </button>
          )}

          <button
            onClick={openAddModal}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-accent text-background text-sm font-semibold hover:bg-accent/90 transition-colors shadow-sm"
          >
            <Plus size={16} />
            Add Memory
          </button>
        </div>
      </div>


      {/* Control Bar: Categories & Search */}
      <div className="flex flex-col lg:flex-row gap-4 justify-between items-stretch lg:items-center">
        {/* Category Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 max-w-full">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.id)}
              className={clsx(
                'px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-colors',
                selectedCategory === cat.id
                  ? 'bg-accent/20 text-accent border border-accent/40'
                  : 'bg-surface2 text-gray-400 border border-border/50 hover:text-gray-200 hover:bg-muted/40'
              )}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {/* Search input & refresh */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1 sm:w-64">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search memories..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 bg-surface2 border border-border rounded-lg text-xs text-gray-200 placeholder-muted-foreground focus:outline-none focus:border-accent"
            />
          </div>
          <button
            onClick={() => refetch()}
            title="Refresh"
            className="p-2 bg-surface2 border border-border rounded-lg text-gray-400 hover:text-accent hover:border-accent transition-colors"
          >
            <RefreshCw size={14} className={clsx(isFetching && 'animate-spin')} />
          </button>
        </div>
      </div>

      {/* Memory List Content */}
      {isLoading ? (
        <div className="p-16 text-center text-[#A0A0A0] space-y-4">
          <IntelligenceCore size="md" active={true} className="mx-auto" />
          <p className="text-xs text-[#767676]">Loading memories...</p>
        </div>
      ) : memories.length === 0 ? (
        <div className="p-16 text-center border border-dashed border-white/[0.08] rounded-2xl bg-[#101011] space-y-4">
          <IntelligenceCore size="md" className="mx-auto" />
          <div className="space-y-1.5 max-w-sm mx-auto">
            <h3 className="text-base font-semibold text-[#F4F2ED]">No memories found</h3>
            <p className="text-xs text-[#A0A0A0] leading-relaxed">
              {searchQuery || selectedCategory !== 'all'
                ? 'No memories matched your current filters.'
                : 'Memories will automatically be extracted from your conversations or you can manually add them.'}
            </p>
          </div>
          <button
            onClick={openAddModal}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-accent text-[#080808] text-xs font-semibold hover:bg-[#E7CA82] transition-colors mt-2"
          >
            <Plus size={14} />
            Create First Memory
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {memories.map((mem) => {
            const isProjectScoped = Boolean(mem.project_id);
            return (
              <div
                key={mem.id}
                className={clsx(
                  'flex flex-col justify-between p-4 rounded-xl border bg-[#101011] transition-all shadow-sm hover:border-white/[0.12] hover:bg-[#141415]',
                  mem.is_active ? 'border-white/[0.06]' : 'border-white/[0.03] opacity-60'
                )}
              >
                <div className="space-y-3">
                  {/* Card top badges */}
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={clsx(
                        'px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider',
                        mem.category === 'preference' && 'bg-amber-500/15 text-amber-300 border border-amber-500/30',
                        mem.category === 'project_context' && 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30',
                        mem.category === 'goal' && 'bg-blue-500/15 text-blue-300 border border-blue-500/30',
                        mem.category === 'skill' && 'bg-purple-500/15 text-purple-300 border border-purple-500/30',
                        mem.category === 'fact' && 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/30',
                        mem.category === 'interest' && 'bg-pink-500/15 text-pink-300 border border-pink-500/30',
                        mem.category === 'other' && 'bg-white/10 text-[#A0A0A0] border border-white/[0.08]'
                      )}
                    >
                      {mem.category.replace('_', ' ')}
                    </span>

                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-[#A0A0A0] border border-white/[0.06] flex items-center gap-1">
                        {isProjectScoped ? <Folder size={10} /> : <Layers size={10} />}
                        {isProjectScoped ? 'Project' : 'Global'}
                      </span>
                    </div>
                  </div>

                  {/* Key & Value */}
                  <div>
                    <div className="text-xs font-mono text-accent mb-1">{mem.key}</div>
                    <div className="text-sm font-medium text-[#F4F2ED] leading-snug">{mem.value}</div>
                  </div>

                  {/* Confidence / Importance / Source */}
                  <div className="flex items-center gap-3 pt-2 text-[11px] text-muted-foreground border-t border-border/40">
                    <span title={`Confidence: ${(mem.confidence * 100).toFixed(0)}%`}>
                      Conf: <strong className="text-gray-300">{(mem.confidence * 100).toFixed(0)}%</strong>
                    </span>
                    <span title={`Importance: ${(mem.importance * 100).toFixed(0)}%`}>
                      Imp: <strong className="text-gray-300">{(mem.importance * 100).toFixed(0)}%</strong>
                    </span>
                    <span className="truncate ml-auto text-[10px] text-muted-foreground/80">
                      Src: {mem.source}
                    </span>
                  </div>
                </div>

                {/* Card actions */}
                <div className="flex items-center justify-between pt-3 mt-3 border-t border-border/40 text-xs">
                  <button
                    onClick={() => toggleMemoryActive(mem)}
                    className={clsx(
                      'flex items-center gap-1 text-[11px] font-medium transition-colors',
                      mem.is_active ? 'text-emerald-400 hover:text-emerald-300' : 'text-gray-400 hover:text-gray-300'
                    )}
                  >
                    {mem.is_active ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
                    {mem.is_active ? 'Active' : 'Inactive'}
                  </button>

                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => openEditModal(mem)}
                      className="p-1 rounded text-gray-400 hover:text-accent hover:bg-muted/40 transition-colors"
                      title="Edit Memory"
                    >
                      <Edit2 size={13} />
                    </button>
                    <button
                      onClick={() => {
                        if (window.confirm(`Delete memory "${mem.key}"?`)) {
                          deleteMutation.mutate(mem.id);
                        }
                      }}
                      className="p-1 rounded text-gray-400 hover:text-red-400 hover:bg-muted/40 transition-colors"
                      title="Delete Memory"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Modal for Add / Edit */}
      {(isAddModalOpen || editingMemory) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg bg-surface2 border border-border rounded-xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border/50 pb-3">
              <h3 className="text-base font-bold text-gray-100 flex items-center gap-2">
                <Sparkles size={18} className="text-accent" />
                {editingMemory ? 'Edit Memory' : 'Create New Memory'}
              </h3>
              <button
                onClick={() => {
                  setIsAddModalOpen(false);
                  setEditingMemory(null);
                }}
                className="text-muted-foreground hover:text-gray-200"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSave} className="space-y-4 text-xs">
              <div>
                <label className="block text-muted-foreground mb-1 font-medium">Category</label>
                <select
                  value={formCategory}
                  onChange={(e) => setFormCategory(e.target.value)}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg text-gray-200 focus:outline-none focus:border-accent"
                >
                  <option value="preference">Preference</option>
                  <option value="fact">Fact</option>
                  <option value="goal">Goal</option>
                  <option value="skill">Skill</option>
                  <option value="interest">Interest</option>
                  <option value="project_context">Project Context</option>
                  <option value="other">Other</option>
                </select>
              </div>

              <div>
                <label className="block text-muted-foreground mb-1 font-medium">Key / Name</label>
                <input
                  type="text"
                  placeholder="e.g. response_style, preferred_language"
                  value={formKey}
                  onChange={(e) => setFormKey(e.target.value)}
                  required
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg text-gray-200 font-mono focus:outline-none focus:border-accent"
                />
              </div>

              <div>
                <label className="block text-muted-foreground mb-1 font-medium">Memory Value</label>
                <textarea
                  placeholder="e.g. Prefers concise and brief responses"
                  value={formValue}
                  onChange={(e) => setFormValue(e.target.value)}
                  rows={3}
                  required
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg text-gray-200 focus:outline-none focus:border-accent"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-muted-foreground mb-1 font-medium">
                    Confidence: {(formConfidence * 100).toFixed(0)}%
                  </label>
                  <input
                    type="range"
                    min="0.1"
                    max="1.0"
                    step="0.05"
                    value={formConfidence}
                    onChange={(e) => setFormConfidence(parseFloat(e.target.value))}
                    className="w-full accent-accent"
                  />
                </div>
                <div>
                  <label className="block text-muted-foreground mb-1 font-medium">
                    Importance: {(formImportance * 100).toFixed(0)}%
                  </label>
                  <input
                    type="range"
                    min="0.1"
                    max="1.0"
                    step="0.05"
                    value={formImportance}
                    onChange={(e) => setFormImportance(parseFloat(e.target.value))}
                    className="w-full accent-accent"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-border/50">
                <button
                  type="button"
                  onClick={() => {
                    setIsAddModalOpen(false);
                    setEditingMemory(null);
                  }}
                  className="px-4 py-2 rounded-lg bg-surface2 border border-border text-gray-300 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending || updateMutation.isPending}
                  className="px-4 py-2 rounded-lg bg-accent text-background font-semibold hover:bg-accent/90 transition-colors"
                >
                  {editingMemory ? 'Update Memory' : 'Save Memory'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal for Clear All Confirmation */}
      {isClearModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-surface2 border border-border rounded-xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-red-400">
              <div className="p-2 rounded-lg bg-red-500/10 border border-red-500/20">
                <AlertTriangle size={20} />
              </div>
              <h3 className="text-base font-bold text-gray-100">Clear All Memories?</h3>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              This will permanently delete all your saved preferences, personal facts, goals, and learning topics. This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2 pt-2 border-t border-border/50">
              <button
                type="button"
                onClick={() => setIsClearModalOpen(false)}
                className="px-4 py-2 rounded-lg bg-surface2 border border-border text-xs text-gray-300 hover:text-white"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={clearAllMutation.isPending}
                onClick={() => clearAllMutation.mutate()}
                className="px-4 py-2 rounded-lg bg-red-500 text-white text-xs font-semibold hover:bg-red-600 transition-colors shadow-sm"
              >
                {clearAllMutation.isPending ? 'Clearing...' : 'Yes, Forget Everything'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

