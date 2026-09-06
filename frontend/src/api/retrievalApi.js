import { fetchApi, API_BASE_URL } from './apiClient';

export const retrievalApi = {
  ingestFile: (fileId, userId) =>
    fetchApi(`/api/v1/embeddings/ingest/${fileId}?user_id=${userId}`, {
      method: 'POST',
    }),

  getIngestionStatus: (fileId, userId) =>
    fetchApi(`/api/v1/embeddings/status/${fileId}?user_id=${userId}`),

  retryIngestion: (fileId, userId) =>
    fetchApi(`/api/v1/embeddings/retry/${fileId}?user_id=${userId}`, {
      method: 'POST',
    }),

  vectorSearch: (payload) =>
    fetchApi('/api/v1/retrieval/vector', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  keywordSearch: (payload) =>
    fetchApi('/api/v1/retrieval/keyword', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  hybridSearch: (payload) =>
    fetchApi('/api/v1/retrieval/hybrid', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  buildContext: (payload) =>
    fetchApi('/api/v1/retrieval/context', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // Phase 7 — RAG
  ragQuery: (payload) =>
    fetchApi('/api/v1/rag/query', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  ragStreamUrl: () => `${API_BASE_URL}/api/v1/rag/stream`,
};

