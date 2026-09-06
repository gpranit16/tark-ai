import { fetchApi } from './apiClient';

const DEFAULT_USER_ID = '00000000-0000-0000-0000-000000000001';

export async function listMemories({
  userId = DEFAULT_USER_ID,
  projectId = null,
  includeGlobal = true,
  category = null,
  isActive = null,
  search = null,
  limit = 50,
  offset = 0,
} = {}) {
  const params = new URLSearchParams();
  params.set('user_id', userId);
  if (projectId) params.set('project_id', projectId);
  if (includeGlobal !== undefined) params.set('include_global', includeGlobal);
  if (category) params.set('category', category);
  if (isActive !== null && isActive !== undefined) params.set('is_active', isActive);
  if (search) params.set('search', search);
  params.set('limit', limit);
  params.set('offset', offset);

  return fetchApi(`/api/v1/memory?${params.toString()}`);
}

export async function createMemory(payload, userId = DEFAULT_USER_ID) {
  return fetchApi(`/api/v1/memory?user_id=${userId}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getMemory(memoryId, userId = DEFAULT_USER_ID) {
  return fetchApi(`/api/v1/memory/${memoryId}?user_id=${userId}`);
}

export async function updateMemory(memoryId, payload, userId = DEFAULT_USER_ID) {
  return fetchApi(`/api/v1/memory/${memoryId}?user_id=${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export async function deleteMemory(memoryId, userId = DEFAULT_USER_ID) {
  return fetchApi(`/api/v1/memory/${memoryId}?user_id=${userId}`, {
    method: 'DELETE',
  });
}

export async function clearAllMemories(userId = DEFAULT_USER_ID, projectId = null) {
  const params = new URLSearchParams();
  params.set('user_id', userId);
  if (projectId) params.set('project_id', projectId);
  return fetchApi(`/api/v1/memory/clear/all?${params.toString()}`, {
    method: 'DELETE',
  });
}


export async function searchMemories(payload, userId = DEFAULT_USER_ID) {
  return fetchApi(`/api/v1/memory/search?user_id=${userId}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function extractMemories(text, isRagQuery = false) {
  return fetchApi('/api/v1/memory/extract', {
    method: 'POST',
    body: JSON.stringify({ text, is_rag_query: isRagQuery }),
  });
}
