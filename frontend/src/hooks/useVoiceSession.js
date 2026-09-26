import { useState, useEffect, useRef, useCallback } from 'react';
import { BrowserWebSpeechInputProvider } from '../services/voice/VoiceInputProvider';
import { BrowserSpeechSynthesisOutputProvider } from '../services/voice/VoiceOutputProvider';

function stripThinking(text) {
  if (!text) return '';
  return text.replace(/<think>[\s\S]*?(?:<\/think>|$)/gi, '').trim();
}

// Splits on ., !, ?, newline, or Hindi purna viram (।)
const SENTENCE_SPLIT_REGEX = /([^\.\!\?\n\r।]+[\.\!\?\n\r।]+)/;

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
  const [voiceState, setVoiceState] = useState('IDLE'); // IDLE, LISTENING, PROCESSING, THINKING, SPEAKING, MUTED, ERROR
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
  const accumulatedStreamRef = useRef('');
  const wasStreamingRef = useRef(false);

  // Keep references to dynamic values so callbacks stay stable
  const onSendMessageRef = useRef(onSendMessage);
  const stopStreamingRef = useRef(stopStreaming);
  const isStreamingRef = useRef(isStreaming);
  const isMicMutedRef = useRef(isMicMuted);
  const isOpenRef = useRef(isOpen);
  const voiceStateRef = useRef(voiceState);

  onSendMessageRef.current = onSendMessage;
  stopStreamingRef.current = stopStreaming;
  isStreamingRef.current = isStreaming;
  isMicMutedRef.current = isMicMuted;
  isOpenRef.current = isOpen;
  voiceStateRef.current = voiceState;

  // Checks whether both LLM streaming and TTS audio playback are done
  const checkIfTurnComplete = useCallback(() => {
    const isAudioActive = outputProviderRef.current?.isSpeaking || false;
    const isStreamActive = isStreamingRef.current;

    if (!isAudioActive && !isStreamActive && isOpenRef.current) {
      sentenceBufferRef.current = '';
      setVoiceState('LISTENING');
      if (inputProviderRef.current && !isMicMutedRef.current) {
        inputProviderRef.current.start().catch((err) => console.warn('Speech resume error:', err));
      }
    }
  }, []);

  // Flush un-spoken tail text to TTS
  const flushRemainingSpeech = useCallback((text) => {
    if (!text || !outputProviderRef.current) return;
    const cleanStream = stripThinking(text);
    if (!cleanStream) return;
    setAssistantTranscript(cleanStream);

    if (sentenceBufferRef.current.length < cleanStream.length) {
      const remaining = cleanStream.slice(sentenceBufferRef.current.length).trim();
      if (remaining.length > 0) {
        outputProviderRef.current.speakSentence(remaining);
        sentenceBufferRef.current = cleanStream;
      }
    }
  }, []);

  // Handle final speech -> Send to existing chat pipeline
  const handleFinalUserSpeech = useCallback(
    async (text) => {
      if (!text || text.trim().length === 0) return;
      const cleanPrompt = text.trim();
      setVoiceState('THINKING');
      setAssistantTranscript('');
      sentenceBufferRef.current = '';
      accumulatedStreamRef.current = '';

      // Pause microphone listening while model generates
      if (inputProviderRef.current) {
        inputProviderRef.current.stop();
      }

      try {
        if (onSendMessageRef.current) {
          await onSendMessageRef.current(cleanPrompt);
        }
      } catch (err) {
        setErrorMessage(err.message || 'Failed to process voice request');
        setVoiceState('ERROR');
      }
    },
    []
  );

  // Initialize providers ONCE on mount and cleanup on unmount
  useEffect(() => {
    outputProviderRef.current = new BrowserSpeechSynthesisOutputProvider({
      onSpeakingStart: () => {
        setVoiceState('SPEAKING');
      },
      onSpeakingEnd: () => {
        checkIfTurnComplete();
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
        // BARGE-IN: If assistant is actively SPEAKING and user speaks, interrupt immediately!
        if (voiceStateRef.current === 'SPEAKING' && isFinal && text.trim().length > 0) {
          if (outputProviderRef.current) outputProviderRef.current.stop();
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
          setUserTranscript(text);
        }
      },
      onError: (err) => {
        if (err.includes('denied') || err.includes('not-allowed')) {
          setErrorMessage('Microphone access denied. Please allow microphone permissions in your browser.');
        } else {
          setErrorMessage(`Microphone note: ${err}`);
        }
        setVoiceState('ERROR');
      },
      onAudioLevel: (lvl) => {
        if (voiceStateRef.current === 'LISTENING') {
          setAudioLevel(lvl);
        }
      },
      onStateChange: (state) => {
        if (state === 'PROCESSING') {
          setVoiceState('PROCESSING');
        } else if (state === 'LISTENING' && voiceStateRef.current !== 'SPEAKING' && voiceStateRef.current !== 'THINKING') {
          setVoiceState('LISTENING');
        }
      },
    });

    return () => {
      if (inputProviderRef.current) inputProviderRef.current.destroy();
      if (outputProviderRef.current) outputProviderRef.current.destroy();
    };
  }, [checkIfTurnComplete, handleFinalUserSpeech]);

  // Stream sentence chunker: Watch streamingDisplay to extract clean sentences and pass to TTS
  useEffect(() => {
    if (!isOpen) return;

    if (streamingDisplay) {
      accumulatedStreamRef.current = streamingDisplay;
      const cleanStream = stripThinking(streamingDisplay);
      if (cleanStream) {
        setAssistantTranscript(cleanStream);
        const newContent = cleanStream.slice(sentenceBufferRef.current.length);
        let remainingToParse = newContent;
        while (true) {
          const match = remainingToParse.match(SENTENCE_SPLIT_REGEX);
          if (!match) break;
          const sentence = match[0].trim();
          if (sentence.length > 0 && outputProviderRef.current) {
            outputProviderRef.current.speakSentence(sentence);
          }
          sentenceBufferRef.current += match[0];
          remainingToParse = remainingToParse.slice(match[0].length);
        }
      }
    }
  }, [streamingDisplay, isOpen]);

  // When streaming finishes, speak any remaining tail in the buffer
  useEffect(() => {
    if (!isOpen) return;

    if (wasStreamingRef.current && !isStreaming) {
      const fullText = accumulatedStreamRef.current;
      flushRemainingSpeech(fullText);
      setTimeout(() => {
        checkIfTurnComplete();
      }, 150);
    }
    wasStreamingRef.current = isStreaming;
  }, [isStreaming, isOpen, flushRemainingSpeech, checkIfTurnComplete]);

  // Direct notification when ChatRoute finishes message generation
  const handleAssistantComplete = useCallback((finalContent) => {
    if (!isOpenRef.current) return;
    const textToSpeak = finalContent || accumulatedStreamRef.current;
    if (textToSpeak) {
      flushRemainingSpeech(textToSpeak);
    }
    setTimeout(() => {
      checkIfTurnComplete();
    }, 250);
  }, [flushRemainingSpeech, checkIfTurnComplete]);

  // Unlock browser audio context / speech synthesis on user click
  const warmup = useCallback(() => {
    if (outputProviderRef.current) {
      outputProviderRef.current.warmup();
    }
  }, []);

  // Modal open / close lifecycle
  useEffect(() => {
    if (isOpen) {
      setErrorMessage(null);
      setVoiceState('LISTENING');
      setUserTranscript('');
      setInterimText('');
      setAssistantTranscript('');
      sentenceBufferRef.current = '';
      accumulatedStreamRef.current = '';

      // Warm up audio synthesis
      if (outputProviderRef.current) {
        outputProviderRef.current.warmup();
      }

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
      sentenceBufferRef.current = '';
      accumulatedStreamRef.current = '';
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
        if (inputProviderRef.current && isOpenRef.current) {
          inputProviderRef.current.start().catch(() => {});
        }
        setVoiceState('LISTENING');
      }
      return next;
    });
  }, []);

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
    if (stopStreamingRef.current) stopStreamingRef.current();
    sentenceBufferRef.current = '';
    accumulatedStreamRef.current = '';
    if (inputProviderRef.current && !isMicMutedRef.current) {
      inputProviderRef.current.start().catch(() => {});
    }
    setVoiceState('LISTENING');
  }, []);

  const retry = useCallback(() => {
    setErrorMessage(null);
    setVoiceState('LISTENING');
    if (outputProviderRef.current) {
      outputProviderRef.current.warmup();
    }
    if (inputProviderRef.current && !isMicMutedRef.current) {
      inputProviderRef.current.start().catch((err) => {
        setErrorMessage(err.message || 'Microphone error');
        setVoiceState('ERROR');
      });
    }
  }, []);

  const sendSpeechOrToggle = useCallback(() => {
    if (outputProviderRef.current) {
      outputProviderRef.current.warmup();
    }
    if (voiceStateRef.current === 'SPEAKING' || isStreamingRef.current) {
      interrupt();
      return;
    }
    if (voiceStateRef.current === 'ERROR') {
      retry();
      return;
    }
    if (inputProviderRef.current && voiceStateRef.current === 'LISTENING') {
      inputProviderRef.current.finishAndSend();
    }
  }, [interrupt, retry]);

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
    retry,
    sendSpeechOrToggle,
    handleAssistantComplete,
    warmup,
  };
}
