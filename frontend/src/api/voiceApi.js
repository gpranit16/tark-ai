import { API_BASE_URL } from './apiClient';

export const voiceApi = {
  getConfig: async () => {
    const token = localStorage.getItem('tarkai_access_token');
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/voice/config`, {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      if (!res.ok) return null;
      return res.json();
    } catch (e) {
      return null;
    }
  },

  transcribeAudio: async (audioBlob, filename = 'recording.webm', language = null) => {
    const token = localStorage.getItem('tarkai_access_token');
    const formData = new FormData();
    formData.append('file', audioBlob, filename);
    if (language) {
      formData.append('language', language);
    }

    const res = await fetch(`${API_BASE_URL}/api/v1/voice/transcribe`, {
      method: 'POST',
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: formData,
    });

    if (!res.ok) {
      let detail = 'Voice transcription failed';
      try {
        const err = await res.json();
        detail = err.detail || detail;
      } catch (_) {}
      throw new Error(detail);
    }

    return res.json();
  },
};
