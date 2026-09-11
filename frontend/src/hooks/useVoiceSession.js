import { useState, useEffect, useRef, useCallback } from 'react';
import { BrowserWebSpeechInputProvider } from '../services/voice/VoiceInputProvider';
import { BrowserSpeechSynthesisOutputProvider } from '../services/voice/VoiceOutputProvider';

/**
 * Custom React Hook managing full Voice Mode lifecycle, state machine,
 * streaming sentence-level playback, and true barge-in / interrupt support.
 */
export function useVoiceSession({
  isOpen,
  onSendMessage,
  isStreaming,
  streamingDisplay,
  stopStreaming,
}) {
  const [voiceState, setVoiceState] = useState('IDLE'); // IDLE, LISTENING, PROCESSING, THINKING, SPEAKING, MUTED, ERROR, DISCONNECTED
  const [audioLevel, setAudioLevel] = useState(0);
  const [userTranscript, setUserTranscript] = useState('');
  const [interimText, setInterimText] = useState('');
  const [assistantTranscript, setAssistantTranscript] = useState('');
  const [isMicMuted, setIsMicMuted] = useState(false);
  const [isSpeakerMuted, setIsSpeakerMuted] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);

  const inputProviderRef = useRef(null);
  const outputProviderRef = useRef(null);
  const sentenceBufferRef = useRef('');
  const isStreamingRef = useRef(isStreaming);
  const voiceStateRef = useRef(voiceState);

  isStreamingRef.current = isStreaming;
  voiceStateRef.current = voiceState;

  // Initialize providers
  useEffect(() => {
    outputProviderRef.current = new BrowserSpeechSynthesisOutputProvider({
      onSpeakingStart: () => {
        setVoiceState('SPEAKING');
      },
      onSpeakingEnd: () => {
        if (!isStreamingRef.current) {
          setVoiceState('LISTENING');
          // Resume listening once speech finishes
          if (inputProviderRef.current && !isMicMuted) {
            inputProviderRef.current.start().catch((err) => console.warn('Speech resume error:', err));
          }
        }
      },
      onAudioLevel: (lvl) => {
        if (voiceStateRef.current === 'SPEAKING') {
          setAudioLevel(lvl);
        }
      },
      onStateChange: (state) => {
        if (state === 'SPEAKING') setVoiceState('SPEAKING');
      },
    });

    inputProviderRef.current = new BrowserWebSpeechInputProvider({
      onTranscript: ({ text, isFinal }) => {
        // BARGE-IN: If user speaks while assistant is speaking or streaming, interrupt immediately!
        if (voiceStateRef.current === 'SPEAKING' || isStreamingRef.current) {
          if (outputProviderRef.current) outputProviderRef.current.stop();
          if (stopStreaming) stopStreaming();
          setVoiceState('LISTENING');
        }

        if (isFinal) {
          setInterimText('');
          setUserTranscript(text);
          if (text.trim().length > 0) {
            handleFinalUserSpeech(text.trim());
          }
        } else {
          setInterimText(text);
        }
      },
      onError: (err) => {
        if (err === 'not-allowed' || err === 'permission-denied') {
          setErrorMessage('Microphone access denied. Please enable microphone permissions in your browser.');
        } else {
          setErrorMessage(`Speech recognition error: ${err}`);
        }
        setVoiceState('ERROR');
      },
      onAudioLevel: (lvl) => {
        if (voiceStateRef.current === 'LISTENING') {
          setAudioLevel(lvl);
        }
      },
      onStateChange: (state) => {
        if (state === 'LISTENING' && voiceStateRef.current !== 'SPEAKING' && voiceStateRef.current !== 'THINKING') {
          setVoiceState('LISTENING');
        }
      },
    });

    return () => {
      if (inputProviderRef.current) inputProviderRef.current.destroy();
      if (outputProviderRef.current) outputProviderRef.current.destroy();
    };
  }, [stopStreaming, isMicMuted]);

  // Handle final speech -> Send to existing chat pipeline
  const handleFinalUserSpeech = useCallback(
    async (text) => {
      if (!text) return;
      setVoiceState('THINKING');
      setAssistantTranscript('');
      sentenceBufferRef.current = '';

      // Pause microphone listening while model generates
      if (inputProviderRef.current) {
        inputProviderRef.current.stop();
      }

      try {
        await onSendMessage(text);
      } catch (err) {
        setErrorMessage(err.message || 'Failed to process voice request');
        setVoiceState('ERROR');
      }
    },
    [onSendMessage]
  );

  // Stream sentence chunker: Watch streamingDisplay to extract sentences and pass to TTS
  useEffect(() => {
    if (!isOpen) return;

    if (streamingDisplay) {
      setAssistantTranscript(streamingDisplay);
      const newContent = streamingDisplay.slice(sentenceBufferRef.current.length);

      // Look for sentence terminators (. ! ? \n)
      const match = newContent.match(/([^\.\!\?\n]+[\.\!\?\n]+)/);
      if (match) {
        const sentence = match[0].trim();
        if (sentence.length > 0 && outputProviderRef.current) {
          outputProviderRef.current.speakSentence(sentence);
          sentenceBufferRef.current += match[0];
        }
      }
    }
  }, [streamingDisplay, isOpen]);

  // When streaming finishes, speak any remaining tail in the buffer
  useEffect(() => {
    if (!isOpen) return;

    if (!isStreaming && streamingDisplay && sentenceBufferRef.current.length < streamingDisplay.length) {
      const remaining = streamingDisplay.slice(sentenceBufferRef.current.length).trim();
      if (remaining.length > 0 && outputProviderRef.current) {
        outputProviderRef.current.speakSentence(remaining);
        sentenceBufferRef.current = streamingDisplay;
      }
    }
  }, [isStreaming, streamingDisplay, isOpen]);

  // Start session when modal opens
  useEffect(() => {
    if (isOpen) {
      setErrorMessage(null);
      setVoiceState('LISTENING');
      if (inputProviderRef.current && !isMicMuted) {
        inputProviderRef.current.start().catch((err) => {
          setErrorMessage(err.message || 'Microphone error');
          setVoiceState('ERROR');
        });
      }
    } else {
      // Modal closed -> Full cleanup
      setVoiceState('IDLE');
      setAudioLevel(0);
      setUserTranscript('');
      setInterimText('');
      setAssistantTranscript('');
      if (inputProviderRef.current) inputProviderRef.current.stop();
      if (outputProviderRef.current) outputProviderRef.current.stop();
    }
  }, [isOpen, isMicMuted]);

  // Mute / Unmute controls
  const toggleMicMute = useCallback(() => {
    setIsMicMuted((prev) => {
      const next = !prev;
      if (next) {
        if (inputProviderRef.current) inputProviderRef.current.stop();
        setVoiceState('MUTED');
      } else {
        if (inputProviderRef.current && isOpen) {
          inputProviderRef.current.start().catch(() => {});
        }
        setVoiceState('LISTENING');
      }
      return next;
    });
  }, [isOpen]);

  const toggleSpeakerMute = useCallback(() => {
    setIsSpeakerMuted((prev) => {
      const next = !prev;
      if (outputProviderRef.current) {
        outputProviderRef.current.setMuted(next);
      }
      return next;
    });
  }, []);

  const interrupt = useCallback(() => {
    if (outputProviderRef.current) outputProviderRef.current.stop();
    if (stopStreaming) stopStreaming();
    if (inputProviderRef.current && !isMicMuted) {
      inputProviderRef.current.start().catch(() => {});
    }
    setVoiceState('LISTENING');
  }, [stopStreaming, isMicMuted]);

  return {
    voiceState,
    audioLevel,
    userTranscript: interimText || userTranscript,
    assistantTranscript,
    isMicMuted,
    isSpeakerMuted,
    errorMessage,
    toggleMicMute,
    toggleSpeakerMute,
    interrupt,
  };
}
