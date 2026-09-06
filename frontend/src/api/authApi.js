import { fetchApi } from './apiClient';

export const authApi = {
  async signup({ email, password, name }) {
    return fetchApi('/api/v1/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ email, password, name }),
    });
  },

  async login({ email, password }) {
    return fetchApi('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  },

  async getCurrentUser() {
    return fetchApi('/api/v1/auth/me', {
      method: 'GET',
    });
  },

  async refreshToken(refreshToken) {
    return fetchApi('/api/v1/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  },

  async logout() {
    return fetchApi('/api/v1/auth/logout', {
      method: 'POST',
    });
  },

  async forgotPassword(email) {
    return fetchApi('/api/v1/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
  },

  async resetPassword({ token, newPassword }) {
    return fetchApi('/api/v1/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify({ token, new_password: newPassword }),
    });
  },

  async verifyEmail(token) {
    return fetchApi('/api/v1/auth/verify-email', {
      method: 'POST',
      body: JSON.stringify({ token }),
    });
  },

  async resendVerification(email) {
    return fetchApi('/api/v1/auth/resend-verification', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
  },

  async updateProfile({ name, avatar_url }) {
    return fetchApi('/api/v1/auth/profile', {
      method: 'PATCH',
      body: JSON.stringify({ name, avatar_url }),
    });
  },

  async changePassword({ current_password, new_password }) {
    return fetchApi('/api/v1/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password, new_password }),
    });
  },

  async uploadAvatar(file) {
    const formData = new FormData();
    formData.append('file', file);
    return fetchApi('/api/v1/auth/avatar', {
      method: 'POST',
      body: formData,
      headers: {
        'Content-Type': null,
      },
    });
  },
};
