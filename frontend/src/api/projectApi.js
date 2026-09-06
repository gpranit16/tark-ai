import { fetchApi } from './apiClient';

export const projectApi = {
  getProjects: (includeArchived = false) =>
    fetchApi(`/api/v1/projects?include_archived=${includeArchived}`),

  getProject: (projectId) =>
    fetchApi(`/api/v1/projects/${projectId}`),

  createProject: (data) =>
    fetchApi('/api/v1/projects', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateProject: (projectId, data) =>
    fetchApi(`/api/v1/projects/${projectId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  archiveProject: (projectId) =>
    fetchApi(`/api/v1/projects/${projectId}/archive`, {
      method: 'POST',
    }),

  restoreProject: (projectId) =>
    fetchApi(`/api/v1/projects/${projectId}/restore`, {
      method: 'POST',
    }),

  deleteProject: (projectId) =>
    fetchApi(`/api/v1/projects/${projectId}`, {
      method: 'DELETE',
    }),

  // Project Files
  getProjectFiles: (projectId) =>
    fetchApi(`/api/v1/projects/${projectId}/files`),

  attachFileToProject: (projectId, fileId) =>
    fetchApi(`/api/v1/projects/${projectId}/files/${fileId}`, {
      method: 'POST',
    }),

  detachFileFromProject: (projectId, fileId) =>
    fetchApi(`/api/v1/projects/${projectId}/files/${fileId}`, {
      method: 'DELETE',
    }),

  // Project Threads
  getProjectThreads: (projectId) =>
    fetchApi(`/api/v1/projects/${projectId}/threads`),

  moveThreadToProject: (projectId, threadId) =>
    fetchApi(`/api/v1/projects/${projectId}/threads/${threadId}`, {
      method: 'POST',
    }),

  removeThreadFromProject: (projectId, threadId) =>
    fetchApi(`/api/v1/projects/${projectId}/threads/${threadId}`, {
      method: 'DELETE',
    }),

  // Project Memory & Research
  getProjectMemory: (projectId) =>
    fetchApi(`/api/v1/projects/${projectId}/memory`),

  getProjectResearch: (projectId) =>
    fetchApi(`/api/v1/projects/${projectId}/research`),
};
