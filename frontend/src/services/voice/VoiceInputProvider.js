/**
 * VoiceInputProvider abstraction & Hybrid (WebSpeech + MediaRecorder Whisper) Implementation for TARK AI.
 * Ensures reliable speech recognition across Chrome, Brave, Edge, Safari, Firefox, and mobile.
 */
import { voiceApi } from '../../api/voiceApi';

export class VoiceInputProvider {
  isSupported() {
    return false;
  }
  start() {
    throw new Error('Not implemented');
  }
  stop() {
    throw new Error('Not implemented');
  }
  abort() {
    throw new Error('Not implemented');
  }
  destroy() {
    // Cleanup
  }
}

export class BrowserWebSpeechInputProvider extends VoiceInputProvider {
  constructor({ onTranscript, onError, onAudioLevel, onStateChange, silenceTimeoutMs = 1600 }) {
    super();
    this.onTranscript = onTranscript || (() => {});
    this.onError = onError || (() => {});
    this.onAudioLevel = onAudioLevel || (() => {});
    this.onStateChange = onStateChange || (() => {});
    this.silenceTimeoutMs = silenceTimeoutMs;

    this.recognition = null;
    this.isListening = false;
    this.audioContext = null;
    this.analyser = null;
    this.mediaStream = null;
    this.mediaRecorder = null;
    this.audioChunks = [];
    this.animFrameId = null;
    this.silenceTimer = null;
    this.restartTimeout = null;
    this.currentInterimText = '';
    this.accumulatedFinalText = '';
    this.hasSpoken = false;
    this.isTranscribing = false;
    this.mimeType = 'audio/webm';

    this._initRecognition();
  }

  isSupported() {
    if (typeof window === 'undefined') return false;
    const hasMedia = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
    const hasSpeech = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
    return hasMedia || hasSpeech;
  }

  _initRecognition() {
    if (typeof window === 'undefined') return;
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    try {
      this.recognition = new SpeechRecognition();
      this.recognition.continuous = true;
      this.recognition.interimResults = true;
      this.recognition.lang = typeof navigator !== 'undefined' ? (navigator.language || 'en-US') : 'en-US';
      this.recognition.maxAlternatives = 1;

      this.recognition.onstart = () => {
        if (this.isListening) {
          this.onStateChange('LISTENING');
        }
      };

      this.recognition.onresult = (event) => {
        let interim = '';
        let finalBatch = '';

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const result = event.results[i];
          const transcriptPart = result[0].transcript;
          if (result.isFinal) {
            finalBatch += transcriptPart + ' ';
          } else {
            interim += transcriptPart;
          }
        }

        if (finalBatch) {
          this.accumulatedFinalText += finalBatch;
          this.hasSpoken = true;
        }

        const fullDisplay = (this.accumulatedFinalText + ' ' + interim).trim();
        this.currentInterimText = fullDisplay;

        if (fullDisplay) {
          this.hasSpoken = true;
          this.onTranscript({ text: fullDisplay, isFinal: false });
          this._resetSilenceTimer();
        }
      };

      this.recognition.onerror = (event) => {
        if (event.error === 'no-speech' || event.error === 'aborted') {
          return;
        }
        // If Brave or privacy shields block Google Speech Recognition, don't crash;
        // our MediaRecorder + server Whisper pipeline will seamlessly handle transcription.
        if (event.error === 'network' || event.error === 'service-not-allowed') {
          console.warn('[VoiceInput] WebSpeech service unavailable, using MediaRecorder Whisper fallback');
          return;
        }
        if (event.error === 'not-allowed' || event.error === 'permission-denied') {
          this.onError('Microphone access denied. Please allow microphone permissions in your browser.');
        } else {
          console.warn('[VoiceInput] Speech recognition warning:', event.error);
        }
      };

      this.recognition.onend = () => {
        if (this.isListening && !this.isTranscribing) {
          clearTimeout(this.restartTimeout);
          this.restartTimeout = setTimeout(() => {
            if (this.isListening && this.recognition && !this.isTranscribing) {
              try {
                this.recognition.start();
              } catch (_) {}
            }
          }, 150);
        }
      };
    } catch (e) {
      console.warn('[VoiceInput] SpeechRecognition init failed:', e);
      this.recognition = null;
    }
  }

  async _startAudioMeter() {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
      if (!this.mediaStream) {
        this.mediaStream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
          video: false,
        });
      }

      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) {
        this.audioContext = new AudioContext();
        if (this.audioContext.state === 'suspended') {
          await this.audioContext.resume();
        }

        const source = this.audioContext.createMediaStreamSource(this.mediaStream);
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = 256;
        this.analyser.smoothingTimeConstant = 0.4;
        source.connect(this.analyser);

        const bufferLength = this.analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        const updateMeter = () => {
          if (!this.analyser || !this.isListening) {
            this.onAudioLevel(0);
            return;
          }
          this.analyser.getByteFrequencyData(dataArray);
          let sum = 0;
          for (let i = 0; i < bufferLength; i++) {
            sum += dataArray[i];
          }
          const avg = sum / bufferLength;
          const normalized = Math.min(1.0, avg / 128.0);

          // Audio level detection triggers speech activity
          if (normalized > 0.08) {
            this.hasSpoken = true;
            this._resetSilenceTimer();
          }

          this.onAudioLevel(normalized);
          this.animFrameId = requestAnimationFrame(updateMeter);
        };

        this.animFrameId = requestAnimationFrame(updateMeter);
      }

      // Initialize parallel MediaRecorder for guaranteed server-side Whisper transcription
      this._startMediaRecorder();
    } catch (err) {
      console.warn('[VoiceInput] Audio meter / microphone error:', err);
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        this.onError('Microphone access denied. Please allow microphone permissions in your browser.');
      } else {
        this.onError(err.message || 'Microphone error');
      }
    }
  }

  _startMediaRecorder() {
    if (typeof window === 'undefined' || !window.MediaRecorder || !this.mediaStream) return;

    this.audioChunks = [];
    const mimeTypes = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/mp4',
      'audio/ogg;codecs=opus',
      '',
    ];

    let selectedMime = '';
    for (const mime of mimeTypes) {
      if (!mime || MediaRecorder.isTypeSupported(mime)) {
        selectedMime = mime;
        break;
      }
    }
    this.mimeType = selectedMime || 'audio/webm';

    try {
      this.mediaRecorder = selectedMime
        ? new MediaRecorder(this.mediaStream, { mimeType: selectedMime })
        : new MediaRecorder(this.mediaStream);

      this.mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          this.audioChunks.push(e.data);
        }
      };

      this.mediaRecorder.start(250); // Slice every 250ms
    } catch (e) {
      console.warn('[VoiceInput] MediaRecorder start error:', e);
      this.mediaRecorder = null;
    }
  }

  _stopAudioMeter() {
    if (this.animFrameId) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      try {
        this.mediaRecorder.stop();
      } catch (_) {}
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop());
      this.mediaStream = null;
    }
    if (this.audioContext) {
      try {
        this.audioContext.close();
      } catch (_) {}
      this.audioContext = null;
    }
    this.onAudioLevel(0);
  }

  _resetSilenceTimer() {
    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
    }
    this.silenceTimer = setTimeout(() => {
      if (this.hasSpoken && this.isListening && !this.isTranscribing) {
        this.finishAndSend();
      }
    }, this.silenceTimeoutMs);
  }

  /**
   * Finishes user speech session and sends final transcript.
   * Uses WebSpeech result if available; otherwise sends recorded audio to Whisper STT.
   */
  async finishAndSend() {
    if (this.isTranscribing) return;
    this.isTranscribing = true;

    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }

    try {
      const immediateText = (this.accumulatedFinalText + ' ' + this.currentInterimText).trim();

      // 1. If WebSpeech captured text cleanly, emit it immediately
      if (immediateText.length > 0) {
        this.currentInterimText = '';
        this.accumulatedFinalText = '';
        this.hasSpoken = false;
        this.onTranscript({ text: immediateText, isFinal: true });
        return;
      }

      // 2. Otherwise fallback to MediaRecorder + Groq Whisper STT
      if (this.mediaRecorder && this.audioChunks.length > 0) {
        this.onStateChange('PROCESSING');

        // Request final data from recorder
        if (this.mediaRecorder.state === 'recording') {
          try {
            this.mediaRecorder.requestData();
          } catch (_) {}
        }

        // Wait brief tick for final chunk
        await new Promise((r) => setTimeout(r, 120));

        const blob = new Blob(this.audioChunks, { type: this.mimeType || 'audio/webm' });
        this.audioChunks = [];

        if (blob.size > 200) {
          const ext = this.mimeType.includes('mp4') ? 'mp4' : 'webm';
          const result = await voiceApi.transcribeAudio(blob, `voice-recording.${ext}`);
          const transcribedText = (result?.text || '').trim();

          if (transcribedText.length > 0) {
            this.currentInterimText = '';
            this.accumulatedFinalText = '';
            this.hasSpoken = false;
            this.onTranscript({ text: transcribedText, isFinal: true });
            return;
          }
        }
      }
    } catch (err) {
      console.warn('[VoiceInput] Whisper transcription error:', err);
    } finally {
      this.currentInterimText = '';
      this.accumulatedFinalText = '';
      this.hasSpoken = false;
      this.isTranscribing = false;
      this.audioChunks = [];
      if (this.isListening) {
        this.onStateChange('LISTENING');
      }
    }
  }

  async start() {
    this.isListening = true;
    this.isTranscribing = false;
    this.currentInterimText = '';
    this.accumulatedFinalText = '';
    this.hasSpoken = false;
    this.audioChunks = [];

    await this._startAudioMeter();

    if (this.recognition) {
      try {
        this.recognition.start();
      } catch (err) {
        if (err.name !== 'InvalidStateError') {
          console.warn('[VoiceInput] Speech recognition start error:', err);
        }
      }
    }
  }

  stop() {
    this.isListening = false;
    clearTimeout(this.restartTimeout);
    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }
    this._stopAudioMeter();
    if (this.recognition) {
      try {
        this.recognition.stop();
      } catch (_) {}
    }
    this.onStateChange('IDLE');
  }

  abort() {
    this.isListening = false;
    clearTimeout(this.restartTimeout);
    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }
    this._stopAudioMeter();
    if (this.recognition) {
      try {
        this.recognition.abort();
      } catch (_) {}
    }
    this.onStateChange('IDLE');
  }

  destroy() {
    this.abort();
    this.recognition = null;
  }
}
