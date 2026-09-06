import { fetchApi } from './apiClient';

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

export const documentApi = {
  getStatus: (fileId, userId = null) =>
    fetchApi(`/api/v1/documents/${fileId}/status?user_id=${getEffectiveUserId(userId)}`),

  getParsedDocument: (fileId, userId = null) =>
    fetchApi(`/api/v1/documents/${fileId}?user_id=${getEffectiveUserId(userId)}`),

  getMetadata: (fileId, userId = null) =>
    fetchApi(`/api/v1/documents/${fileId}/metadata?user_id=${getEffectiveUserId(userId)}`),

  retryProcessing: (fileId, userId = null) =>
    fetchApi(`/api/v1/documents/${fileId}/retry?user_id=${getEffectiveUserId(userId)}`, {
      method: 'POST',
    }),
};
