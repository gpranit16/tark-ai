import { fetchApi } from './apiClient';

const DEV_USER_ID = '00000000-0000-0000-0000-000000000001';

export const settingsApi = {
  getSettings: async (userId = DEV_USER_ID) => {
    return fetchApi(`/api/v1/settings?user_id=${userId}`);
  },

  updateSettings: async (payload, userId = DEV_USER_ID) => {
    return fetchApi(`/api/v1/settings?user_id=${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  resetSettings: async (userId = DEV_USER_ID) => {
    return fetchApi(`/api/v1/settings/reset?user_id=${userId}`, {
      method: 'POST',
    });
  },
};
