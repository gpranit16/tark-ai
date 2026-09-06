export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8001';

export async function fetchApi(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  
  const token = localStorage.getItem('tarkai_access_token');
  const headers = new Headers({
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  });
  
  if (options.headers && options.headers['Content-Type'] === null) {
    headers.delete('Content-Type');
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15000);

  try {
    const response = await fetch(url, {
      ...options,
      headers,
      signal: options.signal || controller.signal,
    });
    clearTimeout(timeoutId);

    if (!response.ok) {
      let errorDetail = 'Unknown API Error';
      try {
        const errorData = await response.json();
        errorDetail = errorData.detail || errorData.message || JSON.stringify(errorData);
      } catch (e) {
        errorDetail = response.statusText;
      }
      throw new Error(`API Error (${response.status}): ${errorDetail}`);
    }

    return response.json();
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === 'AbortError' || err.message?.includes('aborted')) {
      throw new Error('API Error (408): Request timed out. Please check your connection or try again.');
    }
    throw err;
  }
}
