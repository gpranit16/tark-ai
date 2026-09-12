import { create } from 'zustand';

export const useAppStore = create((set, get) => ({
  // UI State
  isSidebarOpen: true,
  toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
  
  isContextPanelOpen: false,
  toggleContextPanel: () => set((state) => ({ isContextPanelOpen: !state.isContextPanelOpen })),

  // Active Thread
  activeThreadId: null,
  setActiveThreadId: (id) => set({ activeThreadId: id }),

  // Active Project Workspace
  activeProjectId: null,
  activeProject: null,
  setActiveProject: (project) =>
    set({
      activeProjectId: project ? (project.id || project) : null,
      activeProject: typeof project === 'object' ? project : null,
    }),

  // User Settings State (synchronized from backend /api/v1/settings)
  userSettings: null,
  setUserSettings: (settings) => {
    if (!settings) return;
    set({
      userSettings: settings,
      displayName: settings.display_name || 'Developer',
      theme: settings.theme || 'dark',
      defaultChatMode: settings.default_mode || 'normal',
      chatDensity: settings.chat_density || 'comfortable',
      animationsEnabled: settings.animations_enabled ?? true,
      enterToSend: settings.enter_to_send ?? true,
      streamingEnabled: settings.streaming_enabled ?? true,
      showTimestamps: settings.show_timestamps ?? true,
      autoScroll: settings.auto_scroll ?? true,
      compactMessages: settings.compact_messages ?? false,
      showCitations: settings.show_citations ?? true,
      showAttachmentPreviews: settings.show_attachment_previews ?? true,
      smartMemoryEnabled: settings.smart_memory_enabled ?? true,
    });
  },

  displayName: 'Developer',
  theme: 'dark',
  defaultChatMode: 'normal',
  chatDensity: 'comfortable',
  animationsEnabled: true,
  enterToSend: true,
  streamingEnabled: true,
  showTimestamps: true,
  autoScroll: true,
  compactMessages: false,
  showCitations: true,
  showAttachmentPreviews: true,
  smartMemoryEnabled: true,

  // Chat Configuration
  mode: 'normal',
  setMode: (mode) => {
    const defaultModels = {
      fast: 'qwen/qwen3.6-27b',
      normal: 'qwen/qwen3.8-27b',
      reasoning: 'openai/gpt-oss-120b',
      coding: 'qwen/qwen3.8-27b',
      rag: 'qwen/qwen3.8-27b',
      deep_research: 'qwen/qwen3.8-27b',
    };
    const defaultProviders = {
      fast: 'groq',
      normal: 'groq',
      reasoning: 'groq',
      coding: 'groq',
      rag: 'groq',
      deep_research: 'groq',
    };
    set({
      mode,
      model: defaultModels[mode] || 'qwen/qwen3.8-27b',
      provider: defaultProviders[mode] || 'groq',
    });
  },
  
  model: 'qwen/qwen3.8-27b',
  setModel: (model) => {
    let provider = 'groq';
    if (model.startsWith('nvidia/') || model.includes('nemotron') || model.startsWith('meta/llama-3.2')) {
      provider = 'nvidia';
    } else if (model.startsWith('gemini')) {
      provider = 'gemini';
    } else if (model.startsWith('mistral')) {
      provider = 'mistral';
    }
    set({ model, provider });
  },
  
  provider: 'groq',
  setProvider: (provider) => set({ provider }),
}));
