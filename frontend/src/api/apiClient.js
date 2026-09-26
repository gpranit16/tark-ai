export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

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

  const timeoutMs = options.timeout ?? 60000;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

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

    if (response.status === 204 || response.headers.get('content-length') === '0') {
      return null;
    }

    const text = await response.text();
    if (!text || text.trim() === '') {
      return null;
    }

    try {
      return JSON.parse(text);
    } catch (parseErr) {
      return text;
    }
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === 'AbortError' || err.message?.includes('aborted')) {
      throw new Error('API Error (408): Request timed out. Please check your connection or try again.');
    }
    if (err.message === 'Failed to fetch' || err.name === 'TypeError') {
      throw new Error('API Error (503): Unable to reach backend server. Please verify backend service is running.');
    }
    throw err;
  }
}
