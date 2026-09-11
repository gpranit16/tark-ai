import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, MicOff, Volume2, VolumeX, X, MessageSquare, Sparkles, AlertCircle, RefreshCw } from 'lucide-react';
import clsx from 'clsx';
import VoiceVisualizer from './VoiceVisualizer';

export default function VoiceModeModal({
  isOpen,
  onClose,
  voiceState,
  audioLevel,
  userTranscript,
  assistantTranscript,
  isMicMuted,
  isSpeakerMuted,
  errorMessage,
  toggleMicMute,
  toggleSpeakerMute,
  interrupt,
  mode,
  model,
  provider,
}) {
  const [showTranscriptDrawer, setShowTranscriptDrawer] = useState(false);

  // Keyboard shortcut: Escape to close
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!isOpen) return;
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const getStatusLabel = () => {
    switch (voiceState) {
      case 'LISTENING':
        return 'Listening…';
      case 'THINKING':
        return 'Thinking…';
      case 'SPEAKING':
        return 'Speaking…';
      case 'MUTED':
        return 'Microphone Muted';
      case 'ERROR':
        return 'Microphone Error';
      default:
        return 'Ready';
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-[#080808]/90 backdrop-blur-2xl select-none"
      >
        {/* Top Header Bar */}
        <div className="absolute top-0 left-0 right-0 flex items-center justify-between p-6 z-10">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#141415] border border-white/[0.08] text-[12px] text-[#A3A09A]">
              <Sparkles size={13} className="text-[#C9A86A]" />
              <span className="font-medium text-[#F2F0EB]">TARK Voice</span>
              <span className="text-white/20">•</span>
              <span className="capitalize text-[#C9A86A]">{mode}</span>
              <span className="text-white/20">•</span>
              <span className="text-[11px] text-[#77736D] truncate max-w-[140px]">{model}</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowTranscriptDrawer((v) => !v)}
              className={clsx(
                "p-2.5 rounded-full border transition-all duration-150",
                showTranscriptDrawer
                  ? "bg-[#C9A86A]/15 text-[#C9A86A] border-[#C9A86A]/30"
                  : "bg-[#141415] text-[#A3A09A] hover:text-[#F2F0EB] border-white/[0.08]"
              )}
              title="Toggle text transcript view"
            >
              <MessageSquare size={16} />
            </button>
            <button
              onClick={onClose}
              className="p-2.5 rounded-full bg-[#141415] text-[#A3A09A] hover:text-[#F2F0EB] border border-white/[0.08] hover:border-white/20 transition-all duration-150"
              title="Exit Voice Mode (Esc)"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Central Content */}
        <div className="flex flex-col items-center justify-center max-w-xl w-full px-6 text-center">
          {/* Visualizer */}
          <VoiceVisualizer voiceState={voiceState} audioLevel={audioLevel} />

          {/* Status Label */}
          <motion.div
            key={voiceState}
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-6 text-[15px] font-medium tracking-wide text-[#A3A09A]"
          >
            {getStatusLabel()}
          </motion.div>

          {/* Error Message if any */}
          {errorMessage && (
            <div className="mt-4 flex items-center gap-2 px-4 py-2 bg-red-500/10 border border-red-500/20 rounded-xl text-[12px] text-red-400">
              <AlertCircle size={14} />
              <span>{errorMessage}</span>
            </div>
          )}

          {/* Live Subtitle Area */}
          <div className="mt-8 min-h-[90px] w-full flex flex-col items-center justify-center">
            {userTranscript && (
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-[17px] leading-relaxed text-[#F2F0EB] font-light italic max-w-lg"
              >
                "{userTranscript}"
              </motion.p>
            )}

            {voiceState === 'SPEAKING' && assistantTranscript && (
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-[14px] leading-relaxed text-[#C9A86A] mt-2 line-clamp-3 max-w-lg font-normal"
              >
                {assistantTranscript}
              </motion.p>
            )}
          </div>
        </div>

        {/* Bottom Floating Control Pill */}
        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex items-center gap-4 bg-[#121212]/90 backdrop-blur-xl border border-white/[0.08] px-6 py-3 rounded-full shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
          {/* Mute Mic Button */}
          <button
            onClick={toggleMicMute}
            className={clsx(
              "p-3 rounded-full transition-all duration-150",
              isMicMuted
                ? "bg-red-500/20 text-red-400 border border-red-500/30"
                : "bg-[#1C1C1E] text-[#F2F0EB] hover:bg-[#28282B]"
            )}
            title={isMicMuted ? 'Unmute microphone' : 'Mute microphone'}
          >
            {isMicMuted ? <MicOff size={18} /> : <Mic size={18} />}
          </button>

          {/* Tap to Interrupt / Speak */}
          <button
            onClick={interrupt}
            className="px-5 py-2.5 rounded-full bg-[#C9A86A] text-[#080808] font-medium text-[13px] hover:bg-[#D4B579] active:scale-95 transition-all shadow-[0_0_20px_rgba(201,168,106,0.3)]"
          >
            {voiceState === 'SPEAKING' ? 'Interrupt' : 'Tap to Speak'}
          </button>

          {/* Speaker Mute Button */}
          <button
            onClick={toggleSpeakerMute}
            className={clsx(
              "p-3 rounded-full transition-all duration-150",
              isSpeakerMuted
                ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                : "bg-[#1C1C1E] text-[#F2F0EB] hover:bg-[#28282B]"
            )}
            title={isSpeakerMuted ? 'Unmute assistant speaker' : 'Mute assistant speaker'}
          >
            {isSpeakerMuted ? <VolumeX size={18} /> : <Volume2 size={18} />}
          </button>
        </div>

        {/* Optional Transcript Side Drawer */}
        {showTranscriptDrawer && (
          <motion.div
            initial={{ x: 320 }}
            animate={{ x: 0 }}
            exit={{ x: 320 }}
            className="absolute top-20 bottom-24 right-6 w-80 bg-[#121212]/95 backdrop-blur-xl border border-white/[0.08] rounded-2xl p-4 overflow-y-auto flex flex-col gap-3 shadow-2xl"
          >
            <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
              <span className="text-[12px] font-medium text-[#C9A86A]">Live Voice Transcript</span>
              <button onClick={() => setShowTranscriptDrawer(false)} className="text-[#77736D] hover:text-[#F2F0EB]">
                <X size={14} />
              </button>
            </div>
            <div className="text-[13px] space-y-3 overflow-y-auto max-h-full">
              {userTranscript && (
                <div className="bg-[#1A1A1C] p-2.5 rounded-xl text-[#F2F0EB]">
                  <span className="text-[10px] text-[#77736D] uppercase block mb-1">You</span>
                  {userTranscript}
                </div>
              )}
              {assistantTranscript && (
                <div className="bg-[#181612] border border-[#C9A86A]/20 p-2.5 rounded-xl text-[#E6E1D8]">
                  <span className="text-[10px] text-[#C9A86A] uppercase block mb-1">TARK AI</span>
                  {assistantTranscript}
                </div>
              )}
              {!userTranscript && !assistantTranscript && (
                <p className="text-[12px] text-[#5A5752] italic text-center py-6">Speak to see real-time transcript…</p>
              )}
            </div>
          </motion.div>
        )}
      </motion.div>
    </AnimatePresence>
  );
}
