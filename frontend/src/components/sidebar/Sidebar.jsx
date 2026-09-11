import { useState, useRef, useEffect } from 'react';
import { NavLink, useNavigate, Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAppStore } from '../../stores/useAppStore';
import { useAuthStore } from '../../stores/useAuthStore';
import ProfileModal from '../auth/ProfileModal';
import { threadApi } from '../../api/threadApi';
import { projectApi } from '../../api/projectApi';
import {
  MessageSquare,
  Plus,
  CheckSquare,
  Folder,
  Book,
  Database,
  Wrench,
  Search,
  Settings,
  ChevronDown,
  ChevronRight,
  Check,
  Layers,
  MoreVertical,
  Pin,
  PinOff,
  Archive,
  ArchiveRestore,
  ArrowUp,
  ArrowDown,
  Trash2,
  Edit2,
  X,
  LogOut,
  Sparkles,
} from 'lucide-react';
import clsx from 'clsx';

export default function Sidebar() {
  const isSidebarOpen = useAppStore((state) => state.isSidebarOpen);
  const activeThreadId = useAppStore((state) => state.activeThreadId);
  const activeProjectId = useAppStore((state) => state.activeProjectId);
  const activeProject = useAppStore((state) => state.activeProject);
  const setActiveProject = useAppStore((state) => state.setActiveProject);
  const { user, logout, isAuthenticated } = useAuthStore();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [showProjectPicker, setShowProjectPicker] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [showSearchInput, setShowSearchInput] = useState(false);
  const [isArchivedOpen, setIsArchivedOpen] = useState(false);

  // 3-dot dropdown menu state
  const [openMenuId, setOpenMenuId] = useState(null);

  // Inline rename state
  const [editingThreadId, setEditingThreadId] = useState(null);
  const [editTitle, setEditTitle] = useState('');

  // Delete confirmation modal state
  const [deletingThread, setDeletingThread] = useState(null);

  // Profile modal state
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);

  const menuRef = useRef(null);

  // Close 3-dot menu on click outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setOpenMenuId(null);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectApi.getProjects(),
    enabled: !!isAuthenticated,
  });

  // Active threads query
  const { data: activeThreads = [], isLoading: isLoadingActive } = useQuery({
    queryKey: ['threads', activeProjectId, { is_archived: false }],
    queryFn: () =>
      threadApi.getThreads({
        ...(activeProjectId ? { project_id: activeProjectId } : {}),
        is_archived: false,
      }),
    enabled: !!isAuthenticated,
    staleTime: 1000 * 15,
    retry: 1,
  });

  // Archived threads query
  const { data: archivedThreads = [], isLoading: isLoadingArchived } = useQuery({
    queryKey: ['threads', activeProjectId, { is_archived: true }],
    queryFn: () =>
      threadApi.getThreads({
        ...(activeProjectId ? { project_id: activeProjectId } : {}),
        is_archived: true,
      }),
    enabled: !!isAuthenticated,
    staleTime: 1000 * 30,
    retry: 1,
  });

  const handleNewChat = (e) => {
    e.preventDefault();
    e.stopPropagation();
    navigate('/');
  };

  const handleSelectProject = (proj) => {
    setActiveProject(proj);
    setShowProjectPicker(false);
  };

  const invalidateThreads = () => {
    queryClient.invalidateQueries({ queryKey: ['threads'] });
  };

  // Actions
  const handleStartRename = (thread, e) => {
    e?.stopPropagation();
    setOpenMenuId(null);
    setEditingThreadId(thread.id);
    setEditTitle(thread.title || '');
  };

  const handleSaveRename = async (threadId) => {
    if (editTitle.trim()) {
      try {
        await threadApi.updateThread(threadId, { title: editTitle.trim() });
        invalidateThreads();
      } catch (err) {
        console.error('Failed to rename thread:', err);
      }
    }
    setEditingThreadId(null);
  };

  const handleTogglePin = async (thread, e) => {
    e?.stopPropagation();
    setOpenMenuId(null);
    try {
      await threadApi.updateThread(thread.id, { is_pinned: !thread.is_pinned });
      invalidateThreads();
    } catch (err) {
      console.error('Failed to toggle pin:', err);
    }
  };

  const handleToggleArchive = async (thread, e) => {
    e?.stopPropagation();
    setOpenMenuId(null);
    try {
      await threadApi.updateThread(thread.id, { is_archived: !thread.is_archived });
      invalidateThreads();
    } catch (err) {
      console.error('Failed to toggle archive:', err);
    }
  };

  const handleMove = async (threadId, direction, e) => {
    e?.stopPropagation();
    setOpenMenuId(null);
    try {
      await threadApi.moveThread(threadId, direction);
      invalidateThreads();
    } catch (err) {
      console.error('Failed to move thread:', err);
    }
  };

  const handleConfirmDelete = async () => {
    if (!deletingThread) return;
    const threadIdToDelete = deletingThread.id;
    try {
      await threadApi.deleteThread(threadIdToDelete);
      invalidateThreads();
      if (activeThreadId === threadIdToDelete) {
        navigate('/');
      }
    } catch (err) {
      console.error('Failed to delete thread:', err);
    } finally {
      setDeletingThread(null);
    }
  };

  if (!isSidebarOpen) return null;

  const navItems = [
    { name: 'My Space', path: '/my-space', icon: Sparkles },
    { name: 'Projects', path: '/projects', icon: Folder },
    { name: 'Tasks & Planning', path: '/tasks', icon: CheckSquare },
    { name: 'Knowledge Base', path: '/knowledge', icon: Book },
    { name: 'Memory', path: '/memory', icon: Database },
    { name: 'Tools', path: '/tools', icon: Wrench },
    { name: 'Settings', path: '/settings', icon: Settings },
  ];

  // Filtering by search
  const filterFn = (t) => {
    if (!searchQuery.trim()) return true;
    return (t.title || 'Untitled').toLowerCase().includes(searchQuery.toLowerCase());
  };

  const safeActive = Array.isArray(activeThreads) ? activeThreads : [];
  const filteredActive = safeActive.filter(filterFn);
  const pinnedThreads = filteredActive.filter((t) => t.is_pinned);
  const recentThreads = filteredActive.filter((t) => !t.is_pinned);
  const safeArchived = Array.isArray(archivedThreads) ? archivedThreads : [];
  const filteredArchived = safeArchived.filter(filterFn);

  // Render a thread list item with 3-dot dropdown menu and inline rename
  const renderThreadItem = (thread, isArchivedSection = false) => {
    const isEditing = editingThreadId === thread.id;
    const isMenuOpen = openMenuId === thread.id;

    return (
      <div
        key={thread.id}
        className="group relative flex items-center justify-between rounded-lg transition-colors hover:bg-[#141417]"
      >
        {isEditing ? (
          <div className="flex items-center w-full px-2 py-1.5 gap-1.5">
            <input
              type="text"
              value={editTitle}
              autoFocus
              onChange={(e) => setEditTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSaveRename(thread.id);
                if (e.key === 'Escape') setEditingThreadId(null);
              }}
              onBlur={() => handleSaveRename(thread.id)}
              className="w-full bg-[#141416] border border-accent/40 rounded-md px-2 py-0.5 text-[12px] text-[#F4F2ED] outline-none focus:ring-1 focus:ring-accent/50"
            />
            <button
              onClick={() => handleSaveRename(thread.id)}
              className="text-xs text-accent hover:text-accent/80 p-1"
            >
              <Check size={12} />
            </button>
            <button
              onClick={() => setEditingThreadId(null)}
              className="text-xs text-[#767676] hover:text-[#F4F2ED] p-1"
            >
              <X size={12} />
            </button>
          </div>
        ) : (
          <>
            <NavLink
              to={`/chat/${thread.id}`}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-2 px-2.5 py-2 text-[12px] transition-colors duration-150 truncate flex-1 min-w-0 rounded-lg',
                  isActive
                    ? 'text-[#F2F0EB] font-medium bg-white/[0.04]'
                    : 'text-[#85817B] hover:text-[#F2F0EB]'
                )
              }
            >
              <MessageSquare size={11} className="shrink-0 opacity-45" />
              <span className="truncate">{thread.title || 'Untitled'}</span>
              {thread.is_pinned && !isArchivedSection && (
                <Pin size={10} className="shrink-0 text-accent/80 ml-auto mr-1" />
              )}
            </NavLink>

            {/* 3-Dot Action Button */}
            <div className="relative shrink-0 pr-1">
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setOpenMenuId(isMenuOpen ? null : thread.id);
                }}
                className={clsx(
                  'p-1 rounded text-[#767676] hover:text-[#F4F2ED] hover:bg-[#1C1C22] transition-all',
                  isMenuOpen ? 'opacity-100 bg-[#1C1C22] text-[#F4F2ED]' : 'opacity-0 group-hover:opacity-100'
                )}
                title="Conversation options"
              >
                <MoreVertical size={13} />
              </button>

              {/* Action Menu Dropdown */}
              {isMenuOpen && (
                <div
                  ref={menuRef}
                  className="absolute right-0 top-full mt-1 w-44 bg-[#111114] border border-white/[0.08] rounded-xl shadow-2xl py-1.5 z-50 text-[12px] text-[#F4F2ED] divide-y divide-white/[0.05] backdrop-blur-md"
                >
                  <div className="py-0.5">
                    <button
                      onClick={(e) => handleStartRename(thread, e)}
                      className="w-full px-3 py-1.5 text-left flex items-center gap-2 hover:bg-[#1C1C20] hover:text-accent transition-colors"
                    >
                      <Edit2 size={12} className="text-[#767676]" />
                      <span>Rename</span>
                    </button>
                    <button
                      onClick={(e) => handleTogglePin(thread, e)}
                      className="w-full px-3 py-1.5 text-left flex items-center gap-2 hover:bg-[#1C1C20] hover:text-accent transition-colors"
                    >
                      {thread.is_pinned ? (
                        <>
                          <PinOff size={12} className="text-[#767676]" />
                          <span>Unpin</span>
                        </>
                      ) : (
                        <>
                          <Pin size={12} className="text-[#767676]" />
                          <span>Pin</span>
                        </>
                      )}
                    </button>
                  </div>

                  <div className="py-0.5">
                    <button
                      onClick={(e) => handleMove(thread.id, 'up', e)}
                      className="w-full px-3 py-1.5 text-left flex items-center gap-2 hover:bg-[#1C1C20] hover:text-accent transition-colors"
                    >
                      <ArrowUp size={12} className="text-[#767676]" />
                      <span>Move Up</span>
                    </button>
                    <button
                      onClick={(e) => handleMove(thread.id, 'down', e)}
                      className="w-full px-3 py-1.5 text-left flex items-center gap-2 hover:bg-[#1C1C20] hover:text-accent transition-colors"
                    >
                      <ArrowDown size={12} className="text-[#767676]" />
                      <span>Move Down</span>
                    </button>
                  </div>

                  <div className="py-0.5">
                    <button
                      onClick={(e) => handleToggleArchive(thread, e)}
                      className="w-full px-3 py-1.5 text-left flex items-center gap-2 hover:bg-[#1C1C20] hover:text-accent transition-colors"
                    >
                      {isArchivedSection || thread.is_archived ? (
                        <>
                          <ArchiveRestore size={12} className="text-[#767676]" />
                          <span>Unarchive</span>
                        </>
                      ) : (
                        <>
                          <Archive size={12} className="text-[#767676]" />
                          <span>Archive</span>
                        </>
                      )}
                    </button>
                    <button
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setOpenMenuId(null);
                        setDeletingThread(thread);
                      }}
                      className="w-full px-3 py-1.5 text-left flex items-center gap-2 text-red-400 hover:bg-red-500/10 hover:text-red-300 transition-colors"
                    >
                      <Trash2 size={12} />
                      <span>Delete</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <aside className="w-64 h-full border-r border-white/[0.05] bg-[#060607] flex flex-col flex-shrink-0 relative select-none">
      {/* Logo */}
      <div className="px-4 py-3.5 flex items-center justify-between border-b border-white/[0.05] min-h-[58px]">
        <Link to="/" className="flex items-center group transition-all duration-300">
          <img
            src="/tark-logo.png"
            alt="TARK AI"
            className="h-9 w-auto max-w-[176px] object-contain filter drop-shadow-[0_0_18px_rgba(214,181,106,0.32)] group-hover:drop-shadow-[0_0_28px_rgba(214,181,106,0.55)] transition-all duration-300 select-none pointer-events-none"
          />
        </Link>
      </div>

      {/* Workspace Selector */}
      <div className="px-3 py-2.5 border-b border-white/[0.05] relative">
        <div className="text-[9.5px] font-semibold text-[#77736D] uppercase tracking-[0.1em] px-1 mb-1.5 flex items-center justify-between">
          <span>Workspace</span>
          {activeProject && (
            <button
              onClick={() => setActiveProject(null)}
              className="text-[9.5px] text-accent/80 hover:text-accent lowercase font-normal tracking-normal transition-colors"
            >
              clear
            </button>
          )}
        </div>
        <button
          onClick={() => setShowProjectPicker(!showProjectPicker)}
          className="w-full flex items-center justify-between px-2.5 py-2 bg-[#101011] hover:bg-[#141415] border border-white/[0.06] hover:border-white/[0.12] rounded-lg text-xs font-medium text-[#F2F0EB] transition-all duration-200"
        >
          <div className="flex items-center gap-2 truncate">
            {activeProject ? (
              <>
                <span className="text-sm">{activeProject.avatar || '📁'}</span>
                <span className="truncate font-medium text-[#F2F0EB]">TARK / {activeProject.name}</span>
              </>
            ) : (
              <>
                <Layers size={13} className="text-[#77736D]" />
                <span className="truncate text-[#85817B]">TARK / Default Workspace</span>
              </>
            )}
          </div>
          <ChevronDown size={13} className="text-[#77736D] shrink-0" />
        </button>

        {/* Project Picker Dropdown */}
        {showProjectPicker && (
          <div className="absolute left-3 right-3 top-full mt-1 bg-[#111114] border border-[#222228] rounded-xl shadow-2xl py-1.5 z-30 max-h-60 overflow-y-auto">
            <button
              onClick={() => handleSelectProject(null)}
              className="w-full px-3 py-2 text-left text-xs flex items-center justify-between hover:bg-[#1C1C20] transition-colors text-gray-300"
            >
              <div className="flex items-center gap-2 truncate">
                <Layers size={12} className="text-[#555562]" />
                <span>Default (No Project)</span>
              </div>
              {!activeProjectId && <Check size={12} className="text-accent" />}
            </button>
            <div className="h-px bg-[#1E1E24] my-1 mx-2" />
            {projects.length > 0 ? (
              projects.map((proj) => (
                <button
                  key={proj.id}
                  onClick={() => handleSelectProject(proj)}
                  className="w-full px-3 py-2 text-left text-xs flex items-center justify-between hover:bg-[#1C1C20] transition-colors text-gray-300"
                >
                  <div className="flex items-center gap-2 truncate">
                    <span>{proj.avatar || '📁'}</span>
                    <span className="truncate">{proj.name}</span>
                  </div>
                  {activeProjectId === proj.id && <Check size={12} className="text-accent" />}
                </button>
              ))
            ) : (
              <div className="px-3 py-2 text-[11px] text-[#666674] italic">
                No projects created yet
              </div>
            )}
            <div className="h-px bg-[#1E1E24] my-1 mx-2" />
            <button
              onClick={() => {
                setShowProjectPicker(false);
                navigate('/projects');
              }}
              className="w-full px-3 py-1.5 text-left text-[11px] text-accent/80 hover:text-accent hover:bg-[#1C1C20] transition-colors font-medium flex items-center gap-1.5"
            >
              <Plus size={11} />
              <span>Manage & Create Projects</span>
            </button>
          </div>
        )}
      </div>

      {/* New Chat Button */}
      <div className="px-3 py-2.5 border-b border-white/[0.05]">
        <button
          onClick={handleNewChat}
          className="w-full flex items-center gap-2 justify-center px-4 py-2.5 bg-[#101011] hover:bg-[#141415] border border-white/[0.06] hover:border-accent/30 rounded-xl text-xs font-medium text-[#85817B] hover:text-accent transition-all duration-200 group"
        >
          <Plus size={14} className="group-hover:rotate-90 transition-transform duration-300" />
          {activeProject ? 'New Project Chat' : 'New Chat'}
        </button>
      </div>

      {/* Navigation & Thread History */}
      <div className="flex-1 overflow-y-auto py-3 space-y-5">
        {/* Main Nav Items */}
        <div className="px-3 space-y-0.5">
          <div className="text-[9.5px] font-semibold text-[#77736D] uppercase tracking-[0.1em] px-2 mb-2">
            Navigation
          </div>
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-2.5 px-2.5 py-[7px] rounded-lg text-[12.5px] font-medium transition-all duration-150',
                isActive && !activeThreadId
                  ? 'bg-accent/10 text-accent border border-accent/20 font-medium'
                  : 'text-[#85817B] hover:bg-[#141415] hover:text-[#F2F0EB] border border-transparent'
              )
            }
          >
            <MessageSquare size={13} className="shrink-0" />
            Chat
          </NavLink>
          {navItems.map((item) => (
            <NavLink
              key={item.name}
              to={item.path}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-2.5 px-2.5 py-[7px] rounded-lg text-[12.5px] font-medium transition-all duration-150',
                  isActive
                    ? 'bg-accent/10 text-accent border border-accent/20 font-medium'
                    : 'text-[#85817B] hover:bg-[#141415] hover:text-[#F2F0EB] border border-transparent'
                )
              }
            >
              <item.icon size={13} className="shrink-0" />
              {item.name}
            </NavLink>
          ))}
        </div>

        {/* Search Bar Toggle */}
        <div className="px-3 space-y-2">
          <div className="flex items-center justify-between px-2">
            <span className="text-[9.5px] font-semibold text-[#77736D] uppercase tracking-[0.1em]">
              History
            </span>
            <button
              onClick={() => setShowSearchInput(!showSearchInput)}
              className="text-[#767676] hover:text-[#F4F2ED] p-0.5 rounded transition-colors duration-150"
              title="Search conversations"
            >
              <Search size={12} />
            </button>
          </div>

          {showSearchInput && (
            <div className="px-0.5 relative">
              <input
                type="text"
                placeholder="Search…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-[#101011] border border-white/[0.08] rounded-lg px-2.5 py-1.5 text-[12px] text-[#F4F2ED] placeholder-[#767676] focus:outline-none focus:border-accent/50 transition-colors"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2.5 top-1.5 text-[#767676] hover:text-[#F4F2ED]"
                >
                  <X size={12} />
                </button>
              )}
            </div>
          )}
        </div>

        {/* PINNED SECTION */}
        {pinnedThreads.length > 0 && (
          <div className="px-3 space-y-0.5">
            <div className="text-[9.5px] font-semibold text-accent/80 uppercase tracking-[0.1em] px-2 flex items-center gap-1.5 mb-1.5">
              <Pin size={9} className="rotate-45" />
              <span>Pinned</span>
            </div>
            <div className="space-y-px">
              {pinnedThreads.map((t) => renderThreadItem(t))}
            </div>
          </div>
        )}

        {/* RECENT SECTION */}
        <div className="px-3 space-y-0.5">
          <div className="text-[9.5px] font-semibold text-[#767676] uppercase tracking-[0.1em] px-2 mb-1.5">
            Recent
          </div>
          {isLoadingActive && safeActive.length === 0 ? (
            <div className="px-2 text-[12px] text-[#767676] animate-pulse py-1.5">Loading…</div>
          ) : recentThreads.length > 0 ? (
            <div className="space-y-px">
              {recentThreads.map((t) => renderThreadItem(t))}
            </div>
          ) : pinnedThreads.length === 0 ? (
            <div className="px-2 text-[11.5px] text-[#767676] py-1.5 italic">
              {searchQuery ? 'No matches' : 'No recent threads'}
            </div>
          ) : null}
        </div>

        {/* ARCHIVED SECTION */}
        {archivedThreads.length > 0 && (
          <div className="px-3 space-y-0.5 pt-2 border-t border-white/[0.05]">
            <button
              onClick={() => setIsArchivedOpen(!isArchivedOpen)}
              className="w-full flex items-center justify-between px-2 py-1.5 text-[11px] font-medium text-[#767676] hover:text-[#F4F2ED] transition-colors rounded-lg hover:bg-[#141415]"
            >
              <div className="flex items-center gap-1.5">
                {isArchivedOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                <Archive size={11} />
                <span className="uppercase tracking-[0.08em] text-[9.5px]">Archived</span>
              </div>
              <span className="text-[10px] bg-[#141415] border border-white/[0.06] px-1.5 py-0.2 rounded-full text-[#A0A0A0] font-mono">
                {archivedThreads.length}
              </span>
            </button>

            {isArchivedOpen && (
              <div className="space-y-0.5 pl-2 mt-1">
                {filteredArchived.length > 0 ? (
                  filteredArchived.map((t) => renderThreadItem(t, true))
                ) : (
                  <div className="px-2 text-[12px] text-[#767676] py-1 italic">
                    No matching archived threads
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* User Profile & Sign Out Footer */}
      <div className="p-3 border-t border-white/[0.05] bg-[#0A0A0B]">
        {isAuthenticated ? (
          <div className="flex items-center justify-between gap-2 p-1.5 rounded-xl bg-white/[0.02] border border-white/[0.04]">
            <div
              onClick={() => setIsProfileModalOpen(true)}
              className="flex items-center gap-2.5 min-w-0 flex-1 cursor-pointer group hover:opacity-95"
              title="Manage Profile & Security"
            >
              <div className="h-8 w-8 rounded-lg bg-[#18181A] border border-[#C9A86A]/30 flex items-center justify-center shrink-0 shadow-[0_0_10px_rgba(201,168,106,0.1)] overflow-hidden group-hover:border-[#C9A86A]/60 transition-colors">
                {user?.avatar_url ? (
                  <img
                    src={user.avatar_url}
                    alt={user?.name || 'User Avatar'}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <span className="text-xs font-semibold text-[#C9A86A]">
                    {user?.name
                      ? user.name
                          .split(' ')
                          .map((n) => n[0])
                          .join('')
                          .slice(0, 2)
                          .toUpperCase()
                      : user?.email
                      ? user.email[0].toUpperCase()
                      : 'U'}
                  </span>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-medium text-white truncate group-hover:text-[#C9A86A] transition-colors">
                  {user?.name || 'Developer'}
                </div>
                <div className="text-[10px] text-white/40 truncate">
                  {user?.email || 'Logged In'}
                </div>
              </div>
            </div>

            <button
              onClick={async () => {
                await logout();
                navigate('/login');
              }}
              title="Sign Out"
              className="p-1.5 rounded-lg text-white/40 hover:text-rose-400 hover:bg-rose-500/10 transition-colors cursor-pointer"
            >
              <LogOut size={14} />
            </button>
          </div>
        ) : (
          <button
            onClick={() => navigate('/login')}
            className="w-full py-2.5 px-3 rounded-xl bg-[#C9A86A] hover:bg-[#E1C27A] text-black font-semibold text-xs tracking-wider uppercase flex items-center justify-center gap-1.5 shadow-[0_2px_12px_rgba(201,168,106,0.15)] active:scale-[0.98] transition-all cursor-pointer"
          >
            <span>SIGN IN TO TARK</span>
          </button>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {deletingThread && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#101011] border border-white/[0.08] rounded-2xl max-w-sm w-full p-6 shadow-2xl space-y-4 animate-fade-up">
            <div className="space-y-1.5">
              <h3 className="text-sm font-semibold text-[#F4F2ED] flex items-center gap-2">
                <Trash2 size={15} className="text-red-400" />
                Delete conversation?
              </h3>
              <p className="text-[12px] text-[#A0A0A0] leading-relaxed">
                &quot;<span className="text-[#F4F2ED] font-medium">{deletingThread.title || 'Untitled'}</span>&quot; and its messages will be permanently deleted.
              </p>
            </div>

            <div className="flex items-center justify-end gap-2 pt-1">
              <button
                onClick={() => setDeletingThread(null)}
                className="px-4 py-1.5 rounded-xl border border-white/[0.08] hover:bg-[#141415] text-[12px] font-medium text-[#A0A0A0] hover:text-[#F4F2ED] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmDelete}
                className="px-4 py-1.5 rounded-xl bg-red-600/90 hover:bg-red-500 text-white text-[12px] font-semibold shadow-md transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
      {/* Profile & Account Modal */}
      <ProfileModal isOpen={isProfileModalOpen} onClose={() => setIsProfileModalOpen(false)} />
    </aside>
  );
}
