/**
 * VoiceInputProvider abstraction & Browser WebSpeech API Implementation for TARK AI.
 */

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
  constructor({ onTranscript, onError, onAudioLevel, onStateChange, silenceTimeoutMs = 1800 }) {
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
    this.animFrameId = null;
    this.silenceTimer = null;
    this.currentInterimText = '';

    this._initRecognition();
  }

  isSupported() {
    if (typeof window === 'undefined') return false;
    return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  }

  _initRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    this.recognition = new SpeechRecognition();
    this.recognition.continuous = true;
    this.recognition.interimResults = true;
    this.recognition.lang = 'en-US';
    this.recognition.maxAlternatives = 1;

    this.recognition.onstart = () => {
      this.isListening = true;
      this.onStateChange('LISTENING');
    };

    this.recognition.onresult = (event) => {
      let interim = '';
      let finalTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; ++i) {
        const result = event.results[i];
        const transcriptPart = result[0].transcript;
        if (result.isFinal) {
          finalTranscript += transcriptPart;
        } else {
          interim += transcriptPart;
        }
      }

      this.currentInterimText = interim;

      if (interim || finalTranscript) {
        this._resetSilenceTimer();
      }

      if (finalTranscript) {
        this.onTranscript({ text: finalTranscript.trim(), isFinal: true });
      } else if (interim) {
        this.onTranscript({ text: interim.trim(), isFinal: false });
      }
    };

    this.recognition.onerror = (event) => {
      if (event.error === 'no-speech') {
        // Normal silence, don't crash
        return;
      }
      if (event.error === 'aborted') {
        return;
      }
      console.warn('[VoiceInputProvider] Speech recognition error:', event.error);
      this.onError(event.error);
    };

    this.recognition.onend = () => {
      if (this.isListening) {
        // Auto-restart if we intended to stay listening
        try {
          this.recognition.start();
        } catch (e) {
          this.isListening = false;
        }
      }
    };
  }

  async _startAudioMeter() {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });

      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return;

      this.audioContext = new AudioContext();
      if (this.audioContext.state === 'suspended') {
        await this.audioContext.resume();
      }

      const source = this.audioContext.createMediaStreamSource(this.mediaStream);
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 256;
      this.analyser.smoothingTimeConstant = 0.5;
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
        this.onAudioLevel(normalized);
        this.animFrameId = requestAnimationFrame(updateMeter);
      };

      this.animFrameId = requestAnimationFrame(updateMeter);
    } catch (err) {
      console.warn('[VoiceInputProvider] Audio meter initialization error:', err);
    }
  }

  _stopAudioMeter() {
    if (this.animFrameId) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop());
      this.mediaStream = null;
    }
    if (this.audioContext) {
      try {
        this.audioContext.close();
      } catch (e) {}
      this.audioContext = null;
    }
    this.onAudioLevel(0);
  }

  _resetSilenceTimer() {
    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
    }
    this.silenceTimer = setTimeout(() => {
      if (this.currentInterimText && this.currentInterimText.trim().length > 0) {
        const text = this.currentInterimText.trim();
        this.currentInterimText = '';
        this.onTranscript({ text, isFinal: true });
      }
    }, this.silenceTimeoutMs);
  }

  async start() {
    if (!this.isSupported()) {
      throw new Error('Speech Recognition is not supported in this browser.');
    }
    this.isListening = true;
    this.currentInterimText = '';
    await this._startAudioMeter();

    try {
      this.recognition.start();
    } catch (err) {
      // Already running
      if (err.name !== 'InvalidStateError') {
        throw err;
      }
    }
  }

  stop() {
    this.isListening = false;
    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }
    this._stopAudioMeter();
    if (this.recognition) {
      try {
        this.recognition.stop();
      } catch (e) {}
    }
    this.onStateChange('IDLE');
  }

  abort() {
    this.isListening = false;
    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }
    this._stopAudioMeter();
    if (this.recognition) {
      try {
        this.recognition.abort();
      } catch (e) {}
    }
    this.onStateChange('IDLE');
  }

  destroy() {
    this.abort();
    this.recognition = null;
  }
}
