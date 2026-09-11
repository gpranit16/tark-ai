import { useState, useEffect, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { settingsApi } from '../api/settingsApi';
import { useAppStore } from '../stores/useAppStore';
import { useAuthStore } from '../stores/useAuthStore';
import ProfileModal from '../components/auth/ProfileModal';
import GoogleCalendarCard from '../components/personal/GoogleCalendarCard';
import GitHubIntegrationCard from '../components/personal/GitHubIntegrationCard';
import {
  Sliders,
  Palette,
  MessageSquare,
  Cpu,
  Brain,
  BookOpen,
  Wrench,
  Shield,
  HardDrive,
  Code,
  User,
  Search,
  Check,
  RotateCcw,
  ExternalLink,
  Info,
  AlertTriangle,
  Sparkles,
  Zap,
  Lock,
  Database,
  ArrowRight,
  Calendar,
} from 'lucide-react';
import clsx from 'clsx';

const DEV_USER_ID = '00000000-0000-0000-0000-000000000001';

export default function SettingsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const setUserSettingsStore = useAppStore((s) => s.setUserSettings);
  const user = useAuthStore((s) => s.user);

  const [activeTab, setActiveTab] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get('tab') || 'general';
  });
  const [searchQuery, setSearchQuery] = useState('');
  const [showResetModal, setShowResetModal] = useState(false);
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
  const [savedFeedback, setSavedFeedback] = useState(false);
  const [oauthToast, setOauthToast] = useState(null);

  // Check URL params for OAuth redirect feedback
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const tabParam = params.get('tab');
    const statusParam = params.get('status');
    const errorParam = params.get('error');

    if (tabParam) {
      setActiveTab(tabParam);
    }
    if (statusParam === 'google_calendar_connected') {
      setOauthToast({ type: 'success', message: 'Google Calendar successfully connected!' });
      setTimeout(() => setOauthToast(null), 5000);
    } else if (errorParam) {
      setOauthToast({ type: 'error', message: `Google connection failed: ${errorParam}` });
      setTimeout(() => setOauthToast(null), 5000);
    }
  }, [location.search]);

  // Load settings envelope from backend
  const { data: envelope, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['settings'],
    queryFn: () => settingsApi.getSettings(DEV_USER_ID),
  });

  // Sync with Zustand store when data changes
  useEffect(() => {
    if (envelope?.settings) {
      setUserSettingsStore(envelope.settings);
    }
  }, [envelope, setUserSettingsStore]);

  // Mutation for updating settings
  const updateMutation = useMutation({
    mutationFn: (payload) => settingsApi.updateSettings(payload, DEV_USER_ID),
    onSuccess: (updatedEnvelope) => {
      queryClient.setQueryData(['settings'], updatedEnvelope);
      setUserSettingsStore(updatedEnvelope.settings);
      setSavedFeedback(true);
      setTimeout(() => setSavedFeedback(false), 2000);
    },
    onError: (err) => {
      console.error('Failed to update settings:', err);
    },
  });

  // Mutation for resetting settings
  const resetMutation = useMutation({
    mutationFn: () => settingsApi.resetSettings(DEV_USER_ID),
    onSuccess: (resetEnvelope) => {
      queryClient.setQueryData(['settings'], resetEnvelope);
      setUserSettingsStore(resetEnvelope.settings);
      setShowResetModal(false);
      setSavedFeedback(true);
      setTimeout(() => setSavedFeedback(false), 2000);
    },
  });

  const settings = envelope?.settings || {};
  const modes = envelope?.modes || [];
  const providers = envelope?.providers || [];
  const storage = envelope?.storage || {};
  const account = envelope?.account || {};
  const tools = envelope?.tools || [];

  const handleUpdate = (updates) => {
    updateMutation.mutate(updates);
  };

  const handleToolToggle = (toolName, currentVal) => {
    const newPrefs = { ...(settings.tool_preferences || {}), [toolName]: !currentVal };
    handleUpdate({ tool_preferences: newPrefs });
  };

  const navSections = [
    { id: 'general', label: 'General', icon: Sliders, desc: 'Display name, language, and default mode' },
    { id: 'connections', label: 'Connections', icon: Calendar, desc: 'Google Calendar and personal integrations' },
    { id: 'appearance', label: 'Appearance', icon: Palette, desc: 'Theme, density, and interface styling' },
    { id: 'chat', label: 'Chat', icon: MessageSquare, desc: 'Streaming, enter-to-send, and view controls' },
    { id: 'models', label: 'Models', icon: Cpu, desc: 'Mode-to-model routing and provider status' },
    { id: 'memory', label: 'Memory', icon: Brain, desc: 'Smart auto-memory and retention preferences' },
    { id: 'knowledge', label: 'Knowledge', icon: BookOpen, desc: 'Retrieval mode and RAG settings' },
    { id: 'tools', label: 'Tools', icon: Wrench, desc: 'Tool permissions and active catalog' },
    { id: 'privacy', label: 'Privacy', icon: Shield, desc: 'Data controls, temporary chats, and isolation' },
    { id: 'storage', label: 'Storage', icon: HardDrive, desc: 'Storage provider and document capacity' },
    { id: 'advanced', label: 'Advanced', icon: Code, desc: 'CRAG pipeline debugging and developer diagnostics' },
    { id: 'account', label: 'Account', icon: User, desc: 'Profile details and workspace metrics' },
  ];

  // Search filter
  const filteredSections = useMemo(() => {
    if (!searchQuery.trim()) return navSections;
    const q = searchQuery.toLowerCase();
    return navSections.filter(
      (s) => s.label.toLowerCase().includes(q) || s.desc.toLowerCase().includes(q) || s.id.includes(q)
    );
  }, [searchQuery]);

  if (isLoading) {
    return (
      <div className="h-full w-full flex flex-col items-center justify-center p-8 space-y-4">
        <div className="w-8 h-8 rounded-full border-2 border-accent border-t-transparent animate-spin" />
        <p className="text-xs text-muted-foreground uppercase tracking-wider">Loading settings...</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="h-full w-full flex flex-col items-center justify-center p-8 space-y-4">
        <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-full text-red-400">
          <AlertTriangle size={24} />
        </div>
        <div className="text-center space-y-1">
          <h3 className="text-base font-semibold text-gray-200">Couldn&apos;t load your settings</h3>
          <p className="text-xs text-muted-foreground max-w-sm">{error?.message || 'Network error occurred while fetching settings.'}</p>
        </div>
        <button
          onClick={() => refetch()}
          className="px-4 py-2 bg-surface border border-border hover:border-accent text-xs font-medium text-gray-200 rounded-lg transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-background text-gray-200 select-none overflow-hidden">
      {/* Top Header */}
      <header className="px-6 py-5 border-b border-border/70 flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-surface/40 backdrop-blur-md shrink-0">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-bold text-gray-100 tracking-tight flex items-center gap-2">
              <Sliders size={20} className="text-accent" />
              Settings
            </h1>
            {savedFeedback && (
              <span className="px-2 py-0.5 bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 text-[11px] font-medium rounded-full flex items-center gap-1 animate-in fade-in zoom-in-95 duration-150">
                <Check size={11} /> Saved
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground">Configure how TARK AI works for you.</p>
        </div>

        {/* Search settings bar */}
        <div className="relative w-full sm:w-64">
          <Search size={14} className="absolute left-3 top-2.5 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search settings..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-surface border border-border rounded-lg pl-8 pr-3 py-1.5 text-xs text-gray-200 placeholder-muted-foreground focus:outline-none focus:border-accent transition-colors"
          />
        </div>
      </header>

      {/* Main Two-Column Layout */}
      <div className="flex-1 flex flex-col md:flex-row min-h-0 overflow-hidden">
        {/* Left Navigation Sidebar */}
        <nav className="w-full md:w-60 border-b md:border-b-0 md:border-r border-border/70 bg-surface/30 flex md:flex-col shrink-0 overflow-x-auto md:overflow-y-auto p-2 md:p-3 space-x-1 md:space-x-0 md:space-y-1">
          {filteredSections.map((sec) => {
            const Icon = sec.icon;
            const isActive = activeTab === sec.id;
            return (
              <button
                key={sec.id}
                onClick={() => setActiveTab(sec.id)}
                className={clsx(
                  'flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-all text-left whitespace-nowrap md:whitespace-normal',
                  isActive
                    ? 'bg-accent/15 text-accent border border-accent/30 shadow-sm'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-surface/80 border border-transparent'
                )}
              >
                <Icon size={15} className={clsx(isActive ? 'text-accent' : 'text-muted-foreground')} />
                <span className="truncate">{sec.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Right Settings Content Panel */}
        <main className="flex-1 overflow-y-auto p-4 md:p-8 bg-background">
          <div className="max-w-3xl mx-auto space-y-6">
            {/* OAuth Toast Notification */}
            {oauthToast && (
              <div
                className={clsx(
                  "p-3.5 rounded-xl border flex items-center justify-between gap-3 text-xs animate-in fade-in slide-in-from-top-2 duration-200",
                  oauthToast.type === 'success'
                    ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                    : "bg-red-500/10 border-red-500/20 text-red-400"
                )}
              >
                <div className="flex items-center gap-2">
                  <Check size={14} className={oauthToast.type === 'success' ? 'text-emerald-400' : 'hidden'} />
                  <AlertTriangle size={14} className={oauthToast.type === 'error' ? 'text-red-400' : 'hidden'} />
                  <span>{oauthToast.message}</span>
                </div>
                <button onClick={() => setOauthToast(null)} className="text-muted-foreground hover:text-gray-100 text-[11px]">
                  Dismiss
                </button>
              </div>
            )}

            {/* GENERAL SETTINGS */}
            {activeTab === 'general' && (
              <div className="space-y-6 animate-in fade-in-50 duration-150">
                <div className="border-b border-border/50 pb-3">
                  <h2 className="text-base font-semibold text-gray-100 flex items-center gap-2">
                    <Sliders size={18} className="text-accent" />
                    General Settings
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">Customize your display name, language, and default conversation mode.</p>
                </div>

                <div className="space-y-5">
                  {/* Display Name */}
                  <div className="bg-surface border border-border rounded-xl p-4 space-y-2">
                    <label className="text-xs font-medium text-gray-200">Display Name</label>
                    <p className="text-[11px] text-muted-foreground">The name used by TARK AI to personalize assistant interactions.</p>
                    <div className="flex items-center gap-2 max-w-sm pt-1">
                      <input
                        type="text"
                        defaultValue={settings.display_name || ''}
                        onBlur={(e) => {
                          const val = e.target.value.trim();
                          if (val && val !== settings.display_name) {
                            handleUpdate({ display_name: val });
                          }
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.target.blur();
                          }
                        }}
                        className="flex-1 bg-background border border-border rounded-lg px-3 py-1.5 text-xs text-gray-100 focus:outline-none focus:border-accent"
                      />
                    </div>
                  </div>

                  {/* Language */}
                  <div className="bg-surface border border-border rounded-xl p-4 space-y-2">
                    <label className="text-xs font-medium text-gray-200">Language</label>
                    <p className="text-[11px] text-muted-foreground">Select your preferred system language.</p>
                    <select
                      value={settings.language || 'en'}
                      onChange={(e) => handleUpdate({ language: e.target.value })}
                      className="bg-background border border-border rounded-lg px-3 py-1.5 text-xs text-gray-100 focus:outline-none focus:border-accent"
                    >
                      <option value="en">English (US)</option>
                      <option value="es">Español</option>
                      <option value="fr">Français</option>
                      <option value="de">Deutsch</option>
                      <option value="ja">日本語</option>
                    </select>
                  </div>

                  {/* Default Conversation Mode */}
                  <div className="bg-surface border border-border rounded-xl p-4 space-y-2">
                    <div>
                      <label className="text-xs font-medium text-gray-200">Default Conversation Mode</label>
                      <p className="text-[11px] text-muted-foreground">New conversations will start in this mode automatically.</p>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 pt-1">
                      {modes.map((m) => {
                        const isSelected = settings.default_mode === m.mode;
                        return (
                          <button
                            key={m.mode}
                            onClick={() => handleUpdate({ default_mode: m.mode })}
                            className={clsx(
                              'flex flex-col items-start p-3 rounded-lg border text-left transition-all',
                              isSelected
                                ? 'bg-accent/10 border-accent text-gray-100 shadow-sm'
                                : 'bg-background border-border/70 hover:border-accent/50 text-gray-300'
                            )}
                          >
                            <div className="flex items-center justify-between w-full">
                              <span className="text-xs font-semibold">{m.display_name}</span>
                              {isSelected && <Check size={13} className="text-accent" />}
                            </div>
                            <span className="text-[10px] text-muted-foreground mt-0.5 capitalize">{m.provider}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* PERSONAL CONNECTIONS & INTEGRATIONS */}
            {activeTab === 'connections' && (
              <div className="space-y-6 animate-in fade-in-50 duration-150">
                <div className="border-b border-border/50 pb-3">
                  <h2 className="text-base font-semibold text-gray-100 flex items-center gap-2">
                    <Calendar size={18} className="text-accent" />
                    Personal Connections & Integrations
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Connect your personal Google Calendar and external accounts to power schedule-aware AI planning.
                  </p>
                </div>

                <div className="space-y-5">
                  <GoogleCalendarCard />
                  <GitHubIntegrationCard />
                </div>
              </div>
            )}

            {/* APPEARANCE SETTINGS */}
            {activeTab === 'appearance' && (
              <div className="space-y-6 animate-in fade-in-50 duration-150">
                <div className="border-b border-border/50 pb-3">
                  <h2 className="text-base font-semibold text-gray-100 flex items-center gap-2">
                    <Palette size={18} className="text-accent" />
                    Appearance
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">Customize workspace theme, accent colors, and message density.</p>
                </div>

                <div className="space-y-5">
                  {/* Theme */}
                  <div className="bg-surface border border-border rounded-xl p-4 space-y-3">
                    <label className="text-xs font-medium text-gray-200">Theme</label>
                    <div className="grid grid-cols-3 gap-3">
                      {['dark', 'light', 'system'].map((t) => {
                        const isSel = (settings.theme || 'dark') === t;
                        return (
                          <button
                            key={t}
                            onClick={() => handleUpdate({ theme: t })}
                            className={clsx(
                              'p-3 rounded-lg border text-center text-xs font-medium capitalize transition-all',
                              isSel
                                ? 'bg-accent/15 border-accent text-accent'
                                : 'bg-background border-border hover:border-accent/40 text-gray-300'
                            )}
                          >
                            {t}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* Accent Color Display */}
                  <div className="bg-surface border border-border rounded-xl p-4 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-gray-200">Accent Color</div>
                      <p className="text-[11px] text-muted-foreground">TARK AI signature champagne & gold branding</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-5 h-5 rounded-full bg-[#C9A86A] border border-white/20 shadow-sm" />
                      <span className="text-xs font-mono text-[#F2F0EB]">#C9A86A</span>
                    </div>
                  </div>

                  {/* Chat Density */}
                  <div className="bg-surface border border-border rounded-xl p-4 space-y-3">
                    <label className="text-xs font-medium text-gray-200">Chat Density</label>
                    <div className="grid grid-cols-3 gap-3">
                      {[
                        { id: 'compact', label: 'Compact', desc: 'Minimal padding' },
                        { id: 'comfortable', label: 'Comfortable', desc: 'Balanced spacing' },
                        { id: 'spacious', label: 'Spacious', desc: 'Relaxed reading' },
                      ].map((d) => {
                        const isSel = (settings.chat_density || 'comfortable') === d.id;
                        return (
                          <button
                            key={d.id}
                            onClick={() => handleUpdate({ chat_density: d.id })}
                            className={clsx(
                              'p-3 rounded-lg border text-left transition-all',
                              isSel
                                ? 'bg-accent/15 border-accent text-gray-100'
                                : 'bg-background border-border hover:border-accent/40 text-gray-400'
                            )}
                          >
                            <div className="text-xs font-semibold text-gray-200">{d.label}</div>
                            <div className="text-[10px] text-muted-foreground">{d.desc}</div>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* Interface Animations */}
                  <div className="bg-surface border border-border rounded-xl p-4 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-gray-200">Interface Animations</div>
                      <p className="text-[11px] text-muted-foreground">Smooth transitions for drawer panels and modals</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={settings.animations_enabled ?? true}
                      onChange={(e) => handleUpdate({ animations_enabled: e.target.checked })}
                      className="w-4 h-4 accent-accent rounded cursor-pointer"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* CHAT SETTINGS */}
            {activeTab === 'chat' && (
              <div className="space-y-6 animate-in fade-in-50 duration-150">
                <div className="border-b border-border/50 pb-3">
                  <h2 className="text-base font-semibold text-gray-100 flex items-center gap-2">
                    <MessageSquare size={18} className="text-accent" />
                    Chat Settings
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">Configure message sending behaviors, real-time streaming, and display options.</p>
                </div>

                <div className="bg-surface border border-border rounded-xl divide-y divide-border/50">
                  {/* Enter to Send */}
                  <div className="p-4 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-gray-200">Enter to Send</div>
                      <p className="text-[11px] text-muted-foreground">Press Enter to send message, Shift+Enter for newline</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={settings.enter_to_send ?? true}
                      onChange={(e) => handleUpdate({ enter_to_send: e.target.checked })}
                      className="w-4 h-4 accent-accent rounded cursor-pointer"
                    />
                  </div>

                  {/* Enable Streaming */}
                  <div className="p-4 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-gray-200">Enable Streaming</div>
                      <p className="text-[11px] text-muted-foreground">Stream AI responses word-by-word via SSE</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={settings.streaming_enabled ?? true}
                      onChange={(e) => handleUpdate({ streaming_enabled: e.target.checked })}
                      className="w-4 h-4 accent-accent rounded cursor-pointer"
                    />
                  </div>

                  {/* Show Message Timestamps */}
                  <div className="p-4 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-gray-200">Show Message Timestamps</div>
                      <p className="text-[11px] text-muted-foreground">Display timestamp details beside user and assistant messages</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={settings.show_timestamps ?? true}
                      onChange={(e) => handleUpdate({ show_timestamps: e.target.checked })}
                      className="w-4 h-4 accent-accent rounded cursor-pointer"
                    />
                  </div>

                  {/* Auto-scroll */}
                  <div className="p-4 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-gray-200">Auto-scroll during Streaming</div>
                      <p className="text-[11px] text-muted-foreground">Automatically keep viewport scrolled to the newest incoming tokens</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={settings.auto_scroll ?? true}
                      onChange={(e) => handleUpdate({ auto_scroll: e.target.checked })}
                      className="w-4 h-4 accent-accent rounded cursor-pointer"
                    />
                  </div>

                  {/* Compact Messages */}
                  <div className="p-4 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-gray-200">Compact Messages</div>
                      <p className="text-[11px] text-muted-foreground">Reduce vertical padding for more message density on screen</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={settings.compact_messages ?? false}
                      onChange={(e) => handleUpdate({ compact_messages: e.target.checked })}
                      className="w-4 h-4 accent-accent rounded cursor-pointer"
                    />
                  </div>

                  {/* Show Citations */}
                  <div className="p-4 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-gray-200">Show Citations</div>
                      <p className="text-[11px] text-muted-foreground">Display verified document source badges beneath answers</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={settings.show_citations ?? true}
                      onChange={(e) => handleUpdate({ show_citations: e.target.checked })}
                      className="w-4 h-4 accent-accent rounded cursor-pointer"
                    />
                  </div>

                  {/* Show Attachment Previews */}
                  <div className="p-4 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-gray-200">Show Attachment Previews</div>
                      <p className="text-[11px] text-muted-foreground">Show thumbnail chips and metadata for attached documents</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={settings.show_attachment_previews ?? true}
                      onChange={(e) => handleUpdate({ show_attachment_previews: e.target.checked })}
                      className="w-4 h-4 accent-accent rounded cursor-pointer"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* MODEL SETTINGS */}
            {activeTab === 'models' && (
              <div className="space-y-6 animate-in fade-in-50 duration-150">
                <div className="border-b border-border/50 pb-3">
                  <h2 className="text-base font-semibold text-gray-100 flex items-center gap-2">
                    <Cpu size={18} className="text-accent" />
                    Model & Provider Routing
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">Live runtime model configuration and provider availability.</p>
                </div>

                {/* Provider Health Cards */}
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Provider Health</div>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {providers.map((p) => {
                      const isAvail = p.status === 'available';
                      const isConfig = p.status === 'configured';
                      return (
                        <div key={p.provider} className="bg-surface border border-border rounded-xl p-3.5 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-semibold text-gray-100">{p.display_name}</span>
                            <span
                              className={clsx(
                                'px-2 py-0.5 rounded-full text-[10px] font-medium flex items-center gap-1',
                                isAvail
                                  ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                                  : isConfig
                                  ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                                  : 'bg-muted text-gray-400 border border-border'
                              )}
                            >
                              <span className={clsx('w-1.5 h-1.5 rounded-full', isAvail ? 'bg-emerald-400' : isConfig ? 'bg-amber-400' : 'bg-gray-500')} />
                              {p.status}
                            </span>
                          </div>
                          <p className="text-[11px] font-mono text-muted-foreground truncate">{p.default_model}</p>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Live Mode-to-Model Routing Table */}
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Active Mode Routing</div>
                  <div className="bg-surface border border-border rounded-xl overflow-hidden">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-surface2 border-b border-border text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                        <tr>
                          <th className="py-2.5 px-4">Mode</th>
                          <th className="py-2.5 px-4">Provider</th>
                          <th className="py-2.5 px-4">Configured Model</th>
                          <th className="py-2.5 px-4 text-right">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/50 text-gray-300">
                        {modes.map((m) => {
                          const isDefault = settings.default_mode === m.mode;
                          return (
                            <tr key={m.mode} className="hover:bg-muted/30 transition-colors">
                              <td className="py-3 px-4 font-medium text-gray-100 flex items-center gap-2">
                                <span>{m.display_name}</span>
                                {isDefault && (
                                  <span className="px-1.5 py-0.2 bg-accent/20 border border-accent/40 text-accent text-[10px] font-semibold rounded">
                                    DEFAULT
                                  </span>
                                )}
                              </td>
                              <td className="py-3 px-4 capitalize font-mono text-muted-foreground">{m.provider}</td>
                              <td className="py-3 px-4 font-mono text-gray-200">{m.model}</td>
                              <td className="py-3 px-4 text-right">
                                <span className="text-[11px] text-emerald-400 font-medium">Active</span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {/* MEMORY SETTINGS */}
            {activeTab === 'memory' && (
              <div className="space-y-6 animate-in fade-in-50 duration-150">
                <div className="border-b border-border/50 pb-3">
                  <h2 className="text-base font-semibold text-gray-100 flex items-center gap-2">
                    <Brain size={18} className="text-accent" />
                    Memory System
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">Control how TARK AI learns and retains personal preferences and facts.</p>
                </div>

                <div className="space-y-4">
                  {/* Smart Memory Toggle */}
                  <div className="bg-surface border border-border rounded-xl p-4 flex items-start justify-between gap-4">
                    <div className="space-y-1">
                      <div className="text-xs font-semibold text-gray-100 flex items-center gap-2">
                        <span>Smart Memory</span>
                        {settings.smart_memory_enabled && (
                          <span className="px-1.5 py-0.2 bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 text-[10px] rounded">
                            ENABLED
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground leading-relaxed">
                        Allows TARK AI to remember useful long-term preferences, background, and facts automatically from your conversations.
                      </p>
                      <p className="text-[11px] text-gray-400 italic">Turning Smart Memory OFF stops automatic writes without deleting existing memories.</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={settings.smart_memory_enabled ?? true}
                      onChange={(e) => handleUpdate({ smart_memory_enabled: e.target.checked })}
                      className="w-4 h-4 accent-accent rounded cursor-pointer mt-1"
                    />
                  </div>

                  {/* Explicit Memory Toggle */}
                  <div className="bg-surface border border-border rounded-xl p-4 flex items-start justify-between gap-4">
                    <div className="space-y-1">
                      <div className="text-xs font-semibold text-gray-100">Explicit Memory Commands</div>
                      <p className="text-xs text-muted-foreground leading-relaxed">
                        Enable explicit memory instructions like &quot;Remember that I use Python 3.12&quot; or &quot;Forget my formatting preference&quot;.
                      </p>
                    </div>
                    <input
                      type="checkbox"
                      checked={settings.explicit_memory_enabled ?? true}
                      onChange={(e) => handleUpdate({ explicit_memory_enabled: e.target.checked })}
                      className="w-4 h-4 accent-accent rounded cursor-pointer mt-1"
                    />
                  </div>

                  {/* Temporary Chat Notice */}
                  <div className="bg-surface2/60 border border-border/70 rounded-xl p-4 flex items-center justify-between gap-4">
                    <div className="space-y-0.5">
                      <div className="text-xs font-medium text-gray-200">Temporary Chat Mode</div>
                      <p className="text-[11px] text-muted-foreground">Temporary conversations never persist memories or summaries.</p>
                    </div>
                    <button
                      onClick={() => navigate('/memory')}
                      className="px-3 py-1.5 bg-background border border-border hover:border-accent text-xs font-medium text-gray-200 hover:text-accent rounded-lg flex items-center gap-1.5 transition-colors shrink-0"
                    >
                      <Database size={13} />
                      Manage Memories
                      <ArrowRight size={12} />
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* KNOWLEDGE SETTINGS */}
            {activeTab === 'knowledge' && (
              <div className="space-y-6 animate-in fade-in-50 duration-150">
                <div className="border-b border-border/50 pb-3">
                  <h2 className="text-base font-semibold text-gray-100 flex items-center gap-2">
                    <BookOpen size={18} className="text-accent" />
                    Knowledge & Retrieval
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">Configure document retrieval strategies and RAG context building.</p>
                </div>

                <div className="space-y-4">
                  {/* Default Retrieval Mode */}
                  <div className="bg-surface border border-border rounded-xl p-4 space-y-3">
                    <label className="text-xs font-medium text-gray-200">Default Retrieval Strategy</label>
                    <div className="grid grid-cols-3 gap-3">
                      {[
                        { id: 'hybrid', label: 'Hybrid', desc: 'Dense vector + Lexical search' },
                        { id: 'vector', label: 'Vector', desc: 'BGE-M3 semantic cosine similarity' },
                        { id: 'keyword', label: 'Keyword', desc: 'PostgreSQL full-text TSVector' },
                      ].map((r) => {
                        const isSel = (settings.default_retrieval_mode || 'hybrid') === r.id;
                        return (
                          <button
                            key={r.id}
                            onClick={() => handleUpdate({ default_retrieval_mode: r.id })}
                            className={clsx(
                              'p-3 rounded-lg border text-left transition-all',
                              isSel
                                ? 'bg-accent/15 border-accent text-gray-100'
                                : 'bg-background border-border hover:border-accent/40 text-gray-400'
                            )}
                          >
                            <div className="text-xs font-semibold text-gray-200">{r.label}</div>
                            <div className="text-[10px] text-muted-foreground">{r.desc}</div>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* RAG Enabled */}
                  <div className="bg-surface border border-border rounded-xl p-4 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-gray-200">RAG Mode Grounding</div>
                      <p className="text-[11px] text-muted-foreground">Automatically augment responses with relevant knowledge base documents</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={settings.rag_enabled ?? true}
                      onChange={(e) => handleUpdate({ rag_enabled: e.target.checked })}
                      className="w-4 h-4 accent-accent rounded cursor-pointer"
                    />
                  </div>

                  {/* Document Context Scope */}
                  <div className="bg-surface border border-border rounded-xl p-4 space-y-2">
                    <label className="text-xs font-medium text-gray-200">Default Document Scope</label>
                    <select
                      value={settings.document_context_scope || 'project'}
                      onChange={(e) => handleUpdate({ document_context_scope: e.target.value })}
                      className="bg-background border border-border rounded-lg px-3 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-accent max-w-xs"
                    >
                      <option value="project">Project Workspace Only</option>
                      <option value="global_project">Global + Project Scope</option>
                    </select>
                  </div>

                  <div className="pt-2">
                    <button
                      onClick={() => navigate('/knowledge')}
                      className="px-4 py-2 bg-surface border border-border hover:border-accent text-xs font-medium text-accent rounded-lg flex items-center gap-2 transition-colors"
                    >
                      <BookOpen size={14} />
                      Open Knowledge Base
                      <ArrowRight size={13} />
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* TOOLS SETTINGS */}
            {activeTab === 'tools' && (
              <div className="space-y-6 animate-in fade-in-50 duration-150">
                <div className="border-b border-border/50 pb-3 flex items-center justify-between">
                  <div>
                    <h2 className="text-base font-semibold text-gray-100 flex items-center gap-2">
                      <Wrench size={18} className="text-accent" />
                      Tools Settings
                    </h2>
                    <p className="text-xs text-muted-foreground mt-0.5">Manage built-in tools and preferences. Backend permissions remain authoritative.</p>
                  </div>
                  <button
                    onClick={() => navigate('/tools')}
                    className="px-3 py-1.5 bg-surface border border-border hover:border-accent text-xs font-medium text-gray-200 hover:text-accent rounded-lg flex items-center gap-1.5 transition-colors"
                  >
                    Playground <ExternalLink size={12} />
                  </button>
                </div>

                <div className="space-y-2">
                  {tools.map((t) => {
                    const isEnabled = t.enabled;
                    return (
                      <div
                        key={t.name}
                        className="bg-surface border border-border rounded-xl p-3.5 flex items-center justify-between gap-4 hover:border-border/90 transition-colors"
                      >
                        <div className="space-y-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold text-gray-100 truncate">{t.display_name}</span>
                            <span
                              className={clsx(
                                'px-1.5 py-0.2 rounded text-[9px] font-semibold uppercase',
                                t.permission === 'SAFE'
                                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                  : t.permission === 'NETWORK'
                                  ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                                  : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                              )}
                            >
                              {t.permission}
                            </span>
                          </div>
                          <p className="text-[11px] text-muted-foreground line-clamp-1">{t.description}</p>
                        </div>

                        <input
                          type="checkbox"
                          checked={isEnabled}
                          onChange={() => handleToolToggle(t.name, isEnabled)}
                          className="w-4 h-4 accent-accent rounded cursor-pointer shrink-0"
                        />
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* PRIVACY SETTINGS */}
            {activeTab === 'privacy' && (
              <div className="space-y-6 animate-in fade-in-50 duration-150">
                <div className="border-b border-border/50 pb-3">
                  <h2 className="text-base font-semibold text-gray-100 flex items-center gap-2">
                    <Shield size={18} className="text-accent" />
                    Privacy & Data Governance
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">Control how your data, memories, and conversations are handled.</p>
                </div>

                <div className="space-y-4">
                  {/* Temporary Chat Info */}
                  <div className="bg-surface border border-border rounded-xl p-4 space-y-2">
                    <div className="text-xs font-semibold text-gray-100 flex items-center gap-2">
                      <Lock size={14} className="text-accent" />
                      Temporary Chat Isolation
                    </div>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      Temporary chats run with zero long-term memory writes, no incremental thread summaries, and are completely isolated from your durable personalization context.
                    </p>
                  </div>

                  {/* User Data Ownership */}
                  <div className="bg-surface border border-border rounded-xl p-4 space-y-2">
                    <div className="text-xs font-semibold text-gray-100">User Scoped Isolation</div>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      All memories, document vectors, conversations, and projects are strictly isolated by your user credentials on PostgreSQL 16 with pgvector row-level ownership.
                    </p>
                  </div>

                  {/* Clear Memory Link */}
                  <div className="bg-surface border border-border rounded-xl p-4 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-gray-200">Memory Management</div>
                      <p className="text-[11px] text-muted-foreground">View, inspect provenance, edit, or delete individual memories</p>
                    </div>
                    <button
                      onClick={() => navigate('/memory')}
                      className="px-3 py-1.5 bg-background border border-border hover:border-accent text-xs font-medium text-gray-200 rounded-lg transition-colors"
                    >
                      Manage Memories
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* STORAGE SETTINGS */}
            {activeTab === 'storage' && (
              <div className="space-y-6 animate-in fade-in-50 duration-150">
                <div className="border-b border-border/50 pb-3">
                  <h2 className="text-base font-semibold text-gray-100 flex items-center gap-2">
                    <HardDrive size={18} className="text-accent" />
                    Storage & Capacity
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">Safe overview of configured document storage provider and file statistics.</p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="bg-surface border border-border rounded-xl p-4 space-y-1">
                    <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Storage Provider</div>
                    <div className="text-sm font-bold text-gray-100 flex items-center gap-1.5">
                      <span>{storage.provider || 'LOCAL'}</span>
                      <span className="w-2 h-2 rounded-full bg-emerald-400" />
                    </div>
                    <div className="text-[10px] text-emerald-400">{storage.status || 'Connected'}</div>
                  </div>

                  <div className="bg-surface border border-border rounded-xl p-4 space-y-1">
                    <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Documents Ingested</div>
                    <div className="text-sm font-bold text-gray-100">{storage.documents_count ?? 0} files</div>
                    <div className="text-[10px] text-muted-foreground">Across all workspaces</div>
                  </div>

                  <div className="bg-surface border border-border rounded-xl p-4 space-y-1">
                    <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Storage Used</div>
                    <div className="text-sm font-bold text-gray-100">{storage.storage_used_formatted || '0 KB'}</div>
                    <div className="text-[10px] text-muted-foreground">Max upload 50 MB</div>
                  </div>
                </div>

                <div className="bg-surface2/60 border border-border/70 rounded-xl p-4 flex items-start gap-3">
                  <Info size={16} className="text-accent shrink-0 mt-0.5" />
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    Storage credentials and backend cloud bucket settings remain strictly managed by environment configuration for security.
                  </p>
                </div>
              </div>
            )}

            {/* ADVANCED SETTINGS */}
            {activeTab === 'advanced' && (
              <div className="space-y-6 animate-in fade-in-50 duration-150">
                <div className="border-b border-border/50 pb-3">
                  <h2 className="text-base font-semibold text-gray-100 flex items-center gap-2">
                    <Code size={18} className="text-accent" />
                    Advanced & Debug Diagnostics
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">Developer controls for CRAG pipeline inspection and real-time event telemetry.</p>
                </div>

                <div className="bg-surface border border-border rounded-xl divide-y divide-border/50">
                  {/* CRAG Debug Mode */}
                  <div className="p-4 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-gray-200">CRAG Debug Mode</div>
                      <p className="text-[11px] text-muted-foreground">Log detailed retrieval confidence and grading metrics in chat</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={settings.crag_debug_mode ?? false}
                      onChange={(e) => handleUpdate({ crag_debug_mode: e.target.checked })}
                      className="w-4 h-4 accent-accent rounded cursor-pointer"
                    />
                  </div>

                  {/* Show CRAG Pipeline */}
                  <div className="p-4 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-gray-200">Show CRAG Pipeline Events</div>
                      <p className="text-[11px] text-muted-foreground">Display real-time step badges (Retrieval, Reranking, Grading) during RAG runs</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={settings.show_crag_pipeline ?? false}
                      onChange={(e) => handleUpdate({ show_crag_pipeline: e.target.checked })}
                      className="w-4 h-4 accent-accent rounded cursor-pointer"
                    />
                  </div>

                  {/* Detailed Streaming Events */}
                  <div className="p-4 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-gray-200">Detailed Streaming Telemetry</div>
                      <p className="text-[11px] text-muted-foreground">Log SSE event chunks in developer console</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={settings.detailed_streaming_events ?? false}
                      onChange={(e) => handleUpdate({ detailed_streaming_events: e.target.checked })}
                      className="w-4 h-4 accent-accent rounded cursor-pointer"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* ACCOUNT SETTINGS */}
            {activeTab === 'account' && (
              <div className="space-y-6 animate-in fade-in-50 duration-150">
                <div className="border-b border-border/50 pb-3">
                  <h2 className="text-base font-semibold text-gray-100 flex items-center gap-2">
                    <User size={18} className="text-accent" />
                    Account & Personalization
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">Workspace account metrics, profile customization, and factory reset controls.</p>
                </div>

                {/* Profile Card */}
                <div className="bg-surface border border-border rounded-xl p-5 space-y-4">
                  <div className="flex items-center justify-between gap-4 flex-wrap pb-4 border-b border-border/50">
                    <div className="flex items-center gap-3.5 min-w-0">
                      <div className="h-12 w-12 rounded-xl bg-surface2 border-2 border-accent/40 flex items-center justify-center shrink-0 overflow-hidden shadow-[0_0_15px_rgba(201,168,106,0.15)]">
                        {user?.avatar_url ? (
                          <img src={user.avatar_url} alt={user?.name || 'User'} className="w-full h-full object-cover" />
                        ) : (
                          <span className="text-sm font-bold text-accent">
                            {user?.name
                              ? user.name
                                  .split(' ')
                                  .map((n) => n[0])
                                  .join('')
                                  .slice(0, 2)
                                  .toUpperCase()
                              : 'U'}
                          </span>
                        )}
                      </div>
                      <div className="min-w-0 space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-gray-100 truncate">{user?.name || 'Developer'}</span>
                          {user?.is_verified ? (
                            <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.2 rounded-full border border-emerald-500/20">
                              Verified
                            </span>
                          ) : (
                            <span className="text-[10px] font-semibold text-amber-400 bg-amber-500/10 px-2 py-0.2 rounded-full border border-amber-500/20">
                              Unverified
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-muted-foreground truncate">{user?.email || 'user@example.com'}</div>
                      </div>
                    </div>

                    <button
                      onClick={() => setIsProfileModalOpen(true)}
                      className="px-3.5 py-1.5 rounded-lg bg-accent text-background font-semibold text-xs hover:bg-accent-hover transition-colors shadow-sm"
                    >
                      Edit Profile & Security
                    </button>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pb-2 border-b border-border/50">
                    <div>
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Projects</div>
                      <div className="text-lg font-bold text-gray-100">{account.projects_count ?? 0}</div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Conversations</div>
                      <div className="text-lg font-bold text-gray-100">{account.threads_count ?? 0}</div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Memories</div>
                      <div className="text-lg font-bold text-gray-100">{account.memories_count ?? 0}</div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Files</div>
                      <div className="text-lg font-bold text-gray-100">{account.files_count ?? 0}</div>
                    </div>
                  </div>

                  <div className="space-y-1">
                    <div className="text-xs font-semibold text-gray-200">User Identity</div>
                    <div className="text-xs font-mono text-muted-foreground bg-background px-3 py-1.5 rounded-lg border border-border/70 truncate">
                      {user?.id || account.user_id || DEV_USER_ID}
                    </div>
                  </div>
                </div>

                {/* Reset Settings Section */}
                <div className="bg-surface border border-red-500/20 rounded-xl p-5 space-y-3">
                  <div className="space-y-1">
                    <div className="text-xs font-semibold text-red-400 flex items-center gap-1.5">
                      <RotateCcw size={14} />
                      Reset to Factory Defaults
                    </div>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      Restores your personal settings, display name, and UI preferences to default. Your chats, files, projects, and memories will NOT be deleted.
                    </p>
                  </div>

                  <button
                    onClick={() => setShowResetModal(true)}
                    className="px-4 py-2 bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-400 text-xs font-medium rounded-lg transition-colors"
                  >
                    Reset All Preferences
                  </button>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>

      {/* Reset Confirmation Modal */}
      {showResetModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-surface border border-border rounded-xl max-w-sm w-full p-5 shadow-2xl space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="space-y-1.5">
              <h3 className="text-sm font-semibold text-gray-100 flex items-center gap-2">
                <RotateCcw size={16} className="text-accent" />
                Reset all preferences?
              </h3>
              <p className="text-xs text-muted-foreground leading-relaxed">
                This will restore your personal settings to the default configuration. Your conversation threads, projects, documents, and memories will remain completely untouched.
              </p>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setShowResetModal(false)}
                className="px-3 py-1.5 rounded-lg border border-border hover:bg-muted/70 text-xs font-medium text-gray-300 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => resetMutation.mutate()}
                disabled={resetMutation.isPending}
                className="px-3 py-1.5 rounded-lg bg-accent text-background text-xs font-semibold hover:bg-accent-hover transition-colors flex items-center gap-1.5"
              >
                {resetMutation.isPending ? 'Resetting...' : 'Confirm Reset'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Profile & Security Modal */}
      <ProfileModal isOpen={isProfileModalOpen} onClose={() => setIsProfileModalOpen(false)} />
    </div>
  );
}
