/**
 * VoiceOutputProvider abstraction & Browser SpeechSynthesis Implementation for TARK AI.
 */

export class VoiceOutputProvider {
  isSupported() {
    return false;
  }
  speak(text) {
    throw new Error('Not implemented');
  }
  stop() {
    throw new Error('Not implemented');
  }
  pause() {
    throw new Error('Not implemented');
  }
  resume() {
    throw new Error('Not implemented');
  }
  destroy() {
    // Cleanup
  }
}

export class BrowserSpeechSynthesisOutputProvider extends VoiceOutputProvider {
  constructor({ onSpeakingStart, onSpeakingEnd, onAudioLevel, onStateChange }) {
    super();
    this.onSpeakingStart = onSpeakingStart || (() => {});
    this.onSpeakingEnd = onSpeakingEnd || (() => {});
    this.onAudioLevel = onAudioLevel || (() => {});
    this.onStateChange = onStateChange || (() => {});

    this.synth = typeof window !== 'undefined' ? window.speechSynthesis : null;
    this.queue = [];
    this.isSpeaking = false;
    this.animFrameId = null;
    this.keepAliveInterval = null;
    this.isMuted = false;
    this.activeUtterances = new Set();
    this.currentUtterance = null;

    this._initVoices();
  }

  isSupported() {
    return typeof window !== 'undefined' && 'speechSynthesis' in window;
  }

  _initVoices() {
    if (!this.synth) return;

    const loadVoices = () => {
      try {
        this.synth.getVoices();
      } catch (_) {}
    };

    loadVoices();
    if (this.synth.onvoiceschanged !== undefined) {
      this.synth.onvoiceschanged = loadVoices;
    }
  }

  /**
   * Warm up browser speech synthesis directly inside a user gesture (click/tap)
   * to satisfy Chromium audio autoplay policy.
   */
  warmup() {
    if (!this.isSupported() || !this.synth) return;
    try {
      if (this.synth.paused) {
        this.synth.resume();
      }
      const u = new SpeechSynthesisUtterance(' ');
      u.volume = 0.01;
      u.rate = 10;
      this.synth.speak(u);
    } catch (_) {}
  }

  _pickVoiceForText(text) {
    if (!this.synth) return null;
    let voices = [];
    try {
      voices = this.synth.getVoices() || [];
    } catch (_) {}

    const hasDevanagari = /[\u0900-\u097F]/.test(text);

    if (hasDevanagari) {
      const hindiVoice = voices.find((v) => v.lang && v.lang.toLowerCase().startsWith('hi'));
      if (hindiVoice) {
        return { voice: hindiVoice, lang: 'hi-IN' };
      }
      return { voice: null, lang: 'hi-IN' };
    }

    if (voices.length > 0) {
      const naturalEn = voices.find(
        (v) =>
          v.lang &&
          v.lang.toLowerCase().startsWith('en') &&
          (v.name.includes('Natural') ||
            v.name.includes('Google') ||
            v.name.includes('Samantha') ||
            v.name.includes('Daniel') ||
            v.name.includes('Jenny') ||
            v.name.includes('Guy') ||
            v.name.includes('Aria') ||
            v.name.includes('Premium'))
      );
      const anyEn = voices.find((v) => v.lang && v.lang.toLowerCase().startsWith('en'));
      return { voice: naturalEn || anyEn || voices[0], lang: naturalEn?.lang || 'en-US' };
    }

    return { voice: null, lang: 'en-US' };
  }

  setMuted(muted) {
    this.isMuted = !!muted;
    if (this.isMuted) {
      this.stop();
    }
  }

  _startSimulatedAudioMeter() {
    let t = 0;
    const animate = () => {
      if (!this.isSpeaking) {
        this.onAudioLevel(0);
        return;
      }
      t += 0.15;
      const level = 0.35 + 0.45 * Math.abs(Math.sin(t) * Math.cos(t * 1.5));
      this.onAudioLevel(level);
      this.animFrameId = requestAnimationFrame(animate);
    };
    this.animFrameId = requestAnimationFrame(animate);
  }

  _stopSimulatedAudioMeter() {
    if (this.animFrameId) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
    this.onAudioLevel(0);
  }

  _startKeepAlive() {
    this._stopKeepAlive();
    this.keepAliveInterval = setInterval(() => {
      if (this.isSpeaking && this.synth && !this.synth.paused) {
        try {
          this.synth.pause();
          this.synth.resume();
        } catch (_) {}
      }
    }, 4500);
  }

  _stopKeepAlive() {
    if (this.keepAliveInterval) {
      clearInterval(this.keepAliveInterval);
      this.keepAliveInterval = null;
    }
  }

  speakSentence(text) {
    if (!this.isSupported() || this.isMuted) return;

    const cleaned = this._cleanTextForSpeech(text);
    if (!cleaned || cleaned.trim().length === 0) return;

    this.queue.push(cleaned.trim());

    if (!this.isSpeaking) {
      this.isSpeaking = true;
      this._playNext();
    }
  }

  _cleanTextForSpeech(text) {
    if (!text) return '';
    return text
      .replace(/<think>[\s\S]*?(?:<\/think>|$)/gi, '')
      .replace(/```[\s\S]*?```/g, 'Here is the code.')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/\[\d+\]/g, '')
      .replace(/https?:\/\/\S+/g, '')
      .replace(/<[^>]+>/g, '')
      .replace(/[*_#~>]/g, '')
      .replace(/^[\s-–—*•]+/gm, '')
      .trim();
  }

  _playNext() {
    if (this.queue.length === 0) {
      this.isSpeaking = false;
      this.currentUtterance = null;
      this._stopSimulatedAudioMeter();
      this._stopKeepAlive();
      this.onSpeakingEnd();
      this.onStateChange('IDLE');
      return;
    }

    const textToSpeak = this.queue.shift();
    if (!textToSpeak || textToSpeak.trim().length === 0) {
      this._playNext();
      return;
    }

    try {
      const utterance = new SpeechSynthesisUtterance(textToSpeak);
      const voiceConfig = this._pickVoiceForText(textToSpeak);
      if (voiceConfig) {
        if (voiceConfig.voice) utterance.voice = voiceConfig.voice;
        if (voiceConfig.lang) utterance.lang = voiceConfig.lang;
      }
      utterance.rate = 1.05;
      utterance.pitch = 1.0;

      // Keep strong reference so Chromium GC doesn't kill playback
      this.currentUtterance = utterance;
      this.activeUtterances.add(utterance);

      utterance.onstart = () => {
        this.isSpeaking = true;
        this.onSpeakingStart();
        this.onStateChange('SPEAKING');
        this._startSimulatedAudioMeter();
        this._startKeepAlive();
      };

      utterance.onend = () => {
        this.activeUtterances.delete(utterance);
        if (this.currentUtterance === utterance) {
          this.currentUtterance = null;
        }
        this._playNext();
      };

      utterance.onerror = (e) => {
        this.activeUtterances.delete(utterance);
        if (this.currentUtterance === utterance) {
          this.currentUtterance = null;
        }
        if (e.error !== 'canceled' && e.error !== 'interrupted') {
          console.warn('[VoiceOutputProvider] TTS playback error:', e.error);
        }
        this._playNext();
      };

      if (this.synth.paused) {
        this.synth.resume();
      }
      this.synth.speak(utterance);
    } catch (err) {
      this.currentUtterance = null;
      console.warn('[VoiceOutputProvider] SpeechSynthesis speak failed:', err);
      this._playNext();
    }
  }

  stop() {
    this.queue = [];
    this.isSpeaking = false;
    this.activeUtterances.clear();
    this.currentUtterance = null;
    this._stopSimulatedAudioMeter();
    this._stopKeepAlive();
    if (this.synth) {
      try {
        this.synth.cancel();
      } catch (e) {}
    }
    this.onSpeakingEnd();
  }

  pause() {
    if (this.synth) {
      try {
        this.synth.pause();
      } catch (e) {}
    }
  }

  resume() {
    if (this.synth) {
      try {
        this.synth.resume();
      } catch (e) {}
    }
  }

  destroy() {
    this.stop();
  }
}
