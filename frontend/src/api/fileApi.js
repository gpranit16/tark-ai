import { fetchApi, API_BASE_URL } from './apiClient';

const DEFAULT_USER_ID = '00000000-0000-0000-0000-000000000001';

const getEffectiveUserId = (userId) => {
  if (userId && userId !== DEFAULT_USER_ID) {
    return userId;
  }
  try {
    const raw = localStorage.getItem('tarkai_user');
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed?.id) return parsed.id;
    }
  } catch {
    // ignore
  }
  return userId || DEFAULT_USER_ID;
};

export const fileApi = {
  uploadFile: async (file, userId = null, projectId = null, storageProvider = null) => {
    const effectiveUserId = getEffectiveUserId(userId);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('user_id', effectiveUserId);
    if (projectId) {
      formData.append('project_id', projectId);
    }
    if (storageProvider) {
      formData.append('storage_provider', storageProvider);
    }
    
    // We don't set Content-Type header so the browser sets it to multipart/form-data with the boundary
    return fetchApi('/api/v1/files/upload', {
      method: 'POST',
      body: formData,
      headers: {
        'Content-Type': null
      }
    });
  },

  getFiles: (userId = null, projectId = null, storageProvider = null) => {
    const effectiveUserId = getEffectiveUserId(userId);
    const params = new URLSearchParams();
    params.append('user_id', effectiveUserId);
    if (projectId) {
      params.append('project_id', projectId);
    }
    if (storageProvider && storageProvider !== 'all') {
      params.append('storage_provider', storageProvider);
    }
    return fetchApi(`/api/v1/files?${params.toString()}`);
  },

  getStorageStats: (userId = null, projectId = null) => {
    const effectiveUserId = getEffectiveUserId(userId);
    const params = new URLSearchParams();
    params.append('user_id', effectiveUserId);
    if (projectId && projectId !== 'all') {
      params.append('project_id', projectId);
    }
    return fetchApi(`/api/v1/files/stats?${params.toString()}`);
  },

  getFile: (fileId, userId = null) => {
    const effectiveUserId = getEffectiveUserId(userId);
    return fetchApi(`/api/v1/files/${fileId}?user_id=${effectiveUserId}`);
  },
  
  getFileContentUrl: (fileId, userId = null) => {
    const effectiveUserId = getEffectiveUserId(userId);
    return `${API_BASE_URL}/api/v1/files/${fileId}/content?user_id=${effectiveUserId}`;
  },

  deleteFile: (fileId, userId = null) => {
    const effectiveUserId = getEffectiveUserId(userId);
    return fetchApi(`/api/v1/files/${fileId}?user_id=${effectiveUserId}`, {
      method: 'DELETE'
    });
  },
};

