import { fetchApi } from './apiClient';

export const threadApi = {
  getThreads: (params) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return fetchApi(`/api/v1/threads${qs}`);
  },
  getThread: (threadId) => fetchApi(`/api/v1/threads/${threadId}`),
  createThread: (data) => fetchApi('/api/v1/threads', {
    method: 'POST',
    body: JSON.stringify(data || {})
  }),
  updateThread: (threadId, data) => fetchApi(`/api/v1/threads/${threadId}`, {
    method: 'PATCH',
    body: JSON.stringify(data)
  }),
  moveThread: (threadId, direction) => fetchApi(`/api/v1/threads/${threadId}/move`, {
    method: 'POST',
    body: JSON.stringify({ direction })
  }),
  deleteThread: (threadId) => fetchApi(`/api/v1/threads/${threadId}`, {
    method: 'DELETE'
  }),
  getMessages: (threadId) => fetchApi(`/api/v1/threads/${threadId}/messages`),
};
