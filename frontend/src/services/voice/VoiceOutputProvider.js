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
    this.selectedVoice = null;
    this.animFrameId = null;
    this.isMuted = false;

    this._initVoices();
  }

  isSupported() {
    return typeof window !== 'undefined' && 'speechSynthesis' in window;
  }

  _initVoices() {
    if (!this.synth) return;

    const updateVoices = () => {
      const voices = this.synth.getVoices();
      if (!voices || voices.length === 0) return;

      // Prefer natural English voices (Google, Microsoft, Apple, Samantha, Daniel)
      const preferred = voices.find(
        (v) =>
          v.lang.startsWith('en') &&
          (v.name.includes('Natural') ||
            v.name.includes('Google') ||
            v.name.includes('Samantha') ||
            v.name.includes('Daniel') ||
            v.name.includes('Karen') ||
            v.name.includes('Premium'))
      );

      this.selectedVoice = preferred || voices.find((v) => v.lang.startsWith('en')) || voices[0];
    };

    updateVoices();
    if (this.synth.onvoiceschanged !== undefined) {
      this.synth.onvoiceschanged = updateVoices;
    }
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
      // Generate dynamic audio level oscillation
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

  speakSentence(text) {
    if (!this.isSupported() || this.isMuted) return;

    const cleaned = this._cleanTextForSpeech(text);
    if (!cleaned) return;

    this.queue.push(cleaned);
    if (!this.isSpeaking) {
      this._playNext();
    }
  }

  _cleanTextForSpeech(text) {
    if (!text) return '';
    // Strip markdown formatting, code blocks, URLs, and JSON tags
    let cleaned = text
      .replace(/```[\s\S]*?```/g, 'Here is the code.')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/https?:\/\/\S+/g, '')
      .replace(/<[^>]+>/g, '')
      .replace(/[*_#~]/g, '')
      .trim();

    return cleaned;
  }

  _playNext() {
    if (this.queue.length === 0) {
      this.isSpeaking = false;
      this._stopSimulatedAudioMeter();
      this.onSpeakingEnd();
      this.onStateChange('IDLE');
      return;
    }

    const textToSpeak = this.queue.shift();
    if (!textToSpeak) {
      this._playNext();
      return;
    }

    const utterance = new SpeechSynthesisUtterance(textToSpeak);
    if (this.selectedVoice) {
      utterance.voice = this.selectedVoice;
    }
    utterance.rate = 1.05;
    utterance.pitch = 1.0;

    utterance.onstart = () => {
      this.isSpeaking = true;
      this.onSpeakingStart();
      this.onStateChange('SPEAKING');
      this._startSimulatedAudioMeter();
    };

    utterance.onend = () => {
      this._playNext();
    };

    utterance.onerror = (e) => {
      if (e.error !== 'canceled' && e.error !== 'interrupted') {
        console.warn('[VoiceOutputProvider] TTS playback error:', e.error);
      }
      this._playNext();
    };

    try {
      this.synth.speak(utterance);
    } catch (err) {
      console.warn('[VoiceOutputProvider] SpeechSynthesis speak failed:', err);
      this._playNext();
    }
  }

  stop() {
    this.queue = [];
    this.isSpeaking = false;
    this._stopSimulatedAudioMeter();
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
