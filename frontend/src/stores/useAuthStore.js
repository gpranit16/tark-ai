import { create } from 'zustand';
import { authApi } from '../api/authApi';

const TOKEN_KEY = 'tarkai_access_token';
const REFRESH_TOKEN_KEY = 'tarkai_refresh_token';
const USER_KEY = 'tarkai_user';

export const useAuthStore = create((set, get) => ({
  user: (() => {
    try {
      const saved = localStorage.getItem(USER_KEY);
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  })(),
  token: localStorage.getItem(TOKEN_KEY) || null,
  refreshToken: localStorage.getItem(REFRESH_TOKEN_KEY) || null,
  isAuthenticated: !!localStorage.getItem(TOKEN_KEY),
  isInitialized: false,
  isLoading: false,
  error: null,

  setTokens: (accessToken, refreshToken, user) => {
    if (accessToken) {
      localStorage.setItem(TOKEN_KEY, accessToken);
    } else {
      localStorage.removeItem(TOKEN_KEY);
    }

    if (refreshToken) {
      localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
    } else {
      localStorage.removeItem(REFRESH_TOKEN_KEY);
    }

    if (user) {
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    } else {
      localStorage.removeItem(USER_KEY);
    }

    set({
      token: accessToken,
      refreshToken: refreshToken,
      user: user || null,
      isAuthenticated: !!accessToken,
      isInitialized: true,
      error: null,
    });
  },

  initialize: async () => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      set({ isAuthenticated: false, isInitialized: true, isLoading: false, user: null });
      return;
    }

    try {
      const user = await authApi.getCurrentUser();
      localStorage.setItem(USER_KEY, JSON.stringify(user));
      set({ user, isAuthenticated: true, isInitialized: true, isLoading: false, error: null });
    } catch (err) {
      // If access token expired, attempt refresh
      const rToken = localStorage.getItem(REFRESH_TOKEN_KEY);
      if (rToken) {
        try {
          const refreshed = await authApi.refreshToken(rToken);
          if (refreshed.access_token) {
            localStorage.setItem(TOKEN_KEY, refreshed.access_token);
            const user = await authApi.getCurrentUser();
            localStorage.setItem(USER_KEY, JSON.stringify(user));
            set({
              token: refreshed.access_token,
              user,
              isAuthenticated: true,
              isInitialized: true,
              isLoading: false,
              error: null,
            });
            return;
          }
        } catch {
          // Refresh failed
        }
      }
      // If token invalid and refresh fails, clear session
      get().logout();
      set({ isInitialized: true, isLoading: false });
    }
  },

  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      const data = await authApi.login({ email, password });
      get().setTokens(data.access_token, data.refresh_token, data.user);
      set({ isLoading: false });
      return data.user;
    } catch (err) {
      const message = err.message.replace(/^API Error \(\d+\):\s*/, '');
      set({ isLoading: false, error: message });
      throw new Error(message);
    }
  },

  signup: async (email, password, name) => {
    set({ isLoading: true, error: null });
    try {
      const data = await authApi.signup({ email, password, name });
      get().setTokens(data.access_token, data.refresh_token, data.user);
      set({ isLoading: false });
      return data.user;
    } catch (err) {
      const message = err.message.replace(/^API Error \(\d+\):\s*/, '');
      set({ isLoading: false, error: message });
      throw new Error(message);
    }
  },

  updateProfile: async ({ name, avatar_url }) => {
    set({ isLoading: true, error: null });
    try {
      const updatedUser = await authApi.updateProfile({ name, avatar_url });
      localStorage.setItem(USER_KEY, JSON.stringify(updatedUser));
      set({ user: updatedUser, isLoading: false });
      return updatedUser;
    } catch (err) {
      const message = err.message.replace(/^API Error \(\d+\):\s*/, '');
      set({ isLoading: false, error: message });
      throw new Error(message);
    }
  },

  uploadAvatar: async (file) => {
    set({ isLoading: true, error: null });
    try {
      const updatedUser = await authApi.uploadAvatar(file);
      localStorage.setItem(USER_KEY, JSON.stringify(updatedUser));
      set({ user: updatedUser, isLoading: false });
      return updatedUser;
    } catch (err) {
      const message = err.message.replace(/^API Error \(\d+\):\s*/, '');
      set({ isLoading: false, error: message });
      throw new Error(message);
    }
  },

  changePassword: async ({ current_password, new_password }) => {
    set({ isLoading: true, error: null });
    try {
      const res = await authApi.changePassword({ current_password, new_password });
      set({ isLoading: false });
      return res;
    } catch (err) {
      const message = err.message.replace(/^API Error \(\d+\):\s*/, '');
      set({ isLoading: false, error: message });
      throw new Error(message);
    }
  },

  logout: async () => {
    try {
      await authApi.logout();
    } catch {
      // Ignore network errors on logout
    }
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    set({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      error: null,
      isLoading: false,
    });
  },

  clearError: () => set({ error: null }),
}));
