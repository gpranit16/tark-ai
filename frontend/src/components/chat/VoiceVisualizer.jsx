import { motion } from 'framer-motion';
import clsx from 'clsx';

/**
 * Luxury Champagne-Gold Voice Visualizer for TARK AI.
 * Reacts smoothly to microphone input, model thinking, and TTS speech playback.
 */
export default function VoiceVisualizer({ voiceState = 'IDLE', audioLevel = 0 }) {
  // Clamp level between 0 and 1
  const level = Math.max(0, Math.min(1, audioLevel));
  const scale = 1 + level * 0.45;
  const glowOpacity = 0.25 + level * 0.55;

  return (
    <div className="relative flex items-center justify-center w-64 h-64 select-none">
      {/* Outer Ambient Atmospheric Glow */}
      <motion.div
        animate={{
          scale: voiceState === 'LISTENING' || voiceState === 'SPEAKING' ? scale * 1.15 : 1,
          opacity: voiceState === 'THINKING' ? [0.3, 0.6, 0.3] : glowOpacity,
        }}
        transition={{
          duration: voiceState === 'THINKING' ? 1.8 : 0.1,
          repeat: voiceState === 'THINKING' ? Infinity : 0,
          ease: 'easeInOut',
        }}
        className={clsx(
          "absolute inset-0 rounded-full blur-3xl pointer-events-none transition-colors duration-500",
          voiceState === 'ERROR'
            ? 'bg-red-500/20'
            : voiceState === 'MUTED'
            ? 'bg-amber-500/15'
            : 'bg-[#C9A86A]/25'
        )}
      />

      {/* Concentric Orbital Rings */}
      <motion.div
        animate={{
          rotate: voiceState === 'THINKING' ? 360 : 0,
          scale: voiceState === 'SPEAKING' ? [1, 1.05, 1] : 1,
        }}
        transition={{
          rotate: { duration: 6, repeat: Infinity, ease: 'linear' },
          scale: { duration: 0.8, repeat: Infinity, ease: 'easeInOut' },
        }}
        className="absolute w-52 h-52 rounded-full border border-[#C9A86A]/20 border-dashed"
      />

      <motion.div
        animate={{
          scale: 1 + level * 0.2,
          opacity: 0.4 + level * 0.4,
        }}
        transition={{ duration: 0.08 }}
        className="absolute w-40 h-40 rounded-full border border-[#C9A86A]/30"
      />

      {/* Core Glowing Orb */}
      <motion.div
        animate={{
          scale: voiceState === 'LISTENING' || voiceState === 'SPEAKING' ? scale : 1,
        }}
        transition={{ duration: 0.08 }}
        className="relative flex items-center justify-center w-28 h-28 rounded-full bg-gradient-to-b from-[#1E1C18] to-[#0A0A0A] border border-[#C9A86A]/40 shadow-[0_0_30px_rgba(201,168,106,0.25)]"
      >
        {/* Dynamic Waveform Bars inside core */}
        <div className="flex items-center justify-center gap-1.5 h-12">
          {[0.6, 1.0, 1.4, 1.0, 0.6].map((multiplier, i) => {
            const barHeight =
              voiceState === 'LISTENING' || voiceState === 'SPEAKING'
                ? Math.max(8, level * 40 * multiplier)
                : voiceState === 'THINKING'
                ? 16 + Math.sin(Date.now() / 200 + i) * 10
                : 6;

            return (
              <motion.div
                key={i}
                animate={{ height: barHeight }}
                transition={{ duration: 0.06 }}
                className={clsx(
                  "w-1 rounded-full transition-colors duration-300",
                  voiceState === 'ERROR'
                    ? 'bg-red-400'
                    : voiceState === 'MUTED'
                    ? 'bg-amber-400/60'
                    : 'bg-[#C9A86A]'
                )}
              />
            );
          })}
        </div>
      </motion.div>
    </div>
  );
}
