import { fetchApi } from './apiClient';

export const integrationsApi = {
  getGoogleCalendarStatus: async () => {
    return fetchApi('/api/v1/integrations/google/calendar/status');
  },

  getGoogleCalendarAuthUrl: async (allowWrite = true) => {
    return fetchApi(`/api/v1/integrations/google/calendar/authorize?allow_write=${allowWrite}`);
  },

  disconnectGoogleCalendar: async () => {
    return fetchApi('/api/v1/integrations/google/calendar/disconnect', {
      method: 'POST',
    });
  },

  getUpcomingEvents: async ({ timeMin, timeMax, maxResults = 15 } = {}) => {
    const params = new URLSearchParams();
    if (timeMin) params.append('time_min', timeMin);
    if (timeMax) params.append('time_max', timeMax);
    if (maxResults) params.append('max_results', maxResults.toString());
    const query = params.toString() ? `?${params.toString()}` : '';
    return fetchApi(`/api/v1/integrations/google/calendar/events${query}`);
  },

  checkFreeBusy: async ({ timeMin, timeMax }) => {
    return fetchApi('/api/v1/integrations/google/calendar/freebusy', {
      method: 'POST',
      body: JSON.stringify({
        time_min: timeMin,
        time_max: timeMax,
      }),
    });
  },

  // GitHub MCP Integration
  getGitHubStatus: async () => {
    return fetchApi('/api/v1/integrations/github/status');
  },

  saveGitHubToken: async (token) => {
    return fetchApi('/api/v1/integrations/github/token', {
      method: 'POST',
      body: JSON.stringify({ token }),
    });
  },

  disconnectGitHub: async () => {
    return fetchApi('/api/v1/integrations/github/disconnect', {
      method: 'POST',
    });
  },
};
