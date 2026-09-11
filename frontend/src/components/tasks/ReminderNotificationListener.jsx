import React, { useEffect, useState, useRef } from 'react';
import { Bell, X, CheckCircle2, Volume2 } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { API_BASE_URL } from '../../api/apiClient';
import { useAuthStore } from '../../stores/useAuthStore';
import { taskApi } from '../../api/taskApi';

// Synthesize a loud, crisp, premium multi-tone crystal bell chime using Web Audio API
export function playReminderChime() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();

    // Master Compressor to prevent distortion while maximizing loudness
    const compressor = ctx.createDynamicsCompressor();
    compressor.threshold.setValueAtTime(-12, ctx.currentTime);
    compressor.knee.setValueAtTime(10, ctx.currentTime);
    compressor.ratio.setValueAtTime(8, ctx.currentTime);
    compressor.attack.setValueAtTime(0.003, ctx.currentTime);
    compressor.release.setValueAtTime(0.25, ctx.currentTime);
    compressor.connect(ctx.destination);

    // Master Gain (increased for high volume)
    const masterGain = ctx.createGain();
    masterGain.gain.setValueAtTime(0.85, ctx.currentTime);
    masterGain.connect(compressor);

    const playNote = (freq, startTime, duration, type = 'sine', volume = 1.0) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, ctx.currentTime + startTime);

      // Fast punchy attack, natural bell decay
      gain.gain.setValueAtTime(0.001, ctx.currentTime + startTime);
      gain.gain.linearRampToValueAtTime(volume, ctx.currentTime + startTime + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + startTime + duration);

      osc.connect(gain);
      gain.connect(masterGain);

      osc.start(ctx.currentTime + startTime);
      osc.stop(ctx.currentTime + startTime + duration);
    };

    // Note 1: Bright Chime (G5 - 784 Hz) + Harmonic (1568 Hz)
    playNote(783.99, 0.0, 0.45, 'sine', 0.8);
    playNote(1567.98, 0.0, 0.35, 'triangle', 0.5);

    // Note 2: Rising Harmonic (B5 - 987.77 Hz)
    playNote(987.77, 0.12, 0.55, 'sine', 0.85);
    playNote(1975.53, 0.12, 0.4, 'triangle', 0.55);

    // Note 3: High Crystal Bell Ring (E6 - 1318.51 Hz) + High Overtone (2637 Hz)
    playNote(1318.51, 0.24, 0.9, 'sine', 1.0);
    playNote(2637.02, 0.24, 0.7, 'triangle', 0.6);
    playNote(659.25, 0.24, 0.9, 'sine', 0.5); // Warm root tone (E5)
  } catch (err) {
    console.warn('[ReminderListener] Audio chime error:', err);
  }
}


export default function ReminderNotificationListener() {
  const [activeNotification, setActiveNotification] = useState(null);
  const token = useAuthStore((s) => s.token) || localStorage.getItem('tarkai_access_token');
  const user = useAuthStore((s) => s.user);
  const queryClient = useQueryClient();
  const seenIdsRef = useRef(new Set());

  const triggerNotification = (reminder) => {
    if (!reminder || !reminder.id) return;
    if (seenIdsRef.current.has(reminder.id)) return;
    seenIdsRef.current.add(reminder.id);

    const nowStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const notif = {
      id: reminder.id,
      title: reminder.title || 'Reminder Alert',
      time: nowStr,
    };

    setActiveNotification(notif);
    playReminderChime();

    // Native browser notification
    if ('Notification' in window && Notification.permission === 'granted') {
      try {
        new Notification(`TARK Reminder: ${notif.title}`, {
          body: `Scheduled alert triggered at ${nowStr}`,
          icon: '/vite.svg',
        });
      } catch (_) {}
    }

    // Invalidate caches to refresh UI
    queryClient.invalidateQueries({ queryKey: ['reminders'] });
    queryClient.invalidateQueries({ queryKey: ['tasks'] });
    queryClient.invalidateQueries({ queryKey: ['daily-plan'] });

    // Auto dismiss after 10s
    setTimeout(() => {
      setActiveNotification((prev) => (prev?.id === notif.id ? null : prev));
    }, 10000);
  };

  // Request browser notification permission once on mount
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission().catch(() => {});
    }
  }, []);

  // 1. SSE Real-time stream subscription
  useEffect(() => {
    if (!token) return;

    const sseUrl = `${API_BASE_URL}/api/v1/tasks/reminders/stream?token=${encodeURIComponent(token)}`;
    const es = new EventSource(sseUrl);

    es.onmessage = (event) => {
      try {
        if (!event.data) return;
        const data = JSON.parse(event.data);
        if (data.event === 'reminder_due' || data.title) {
          triggerNotification({
            id: data.reminder_id || data.id,
            title: data.title,
          });
        }
      } catch (_) {}
    };

    return () => {
      es.close();
    };
  }, [token]);

  // 2. Fallback polling check every 8 seconds for newly delivered reminders
  useEffect(() => {
    if (!token) return;

    // Seed initially with already delivered IDs so they don't pop up on fresh load
    taskApi.getReminders({ status: 'sent' }).then((data) => {
      if (Array.isArray(data)) {
        data.forEach((r) => seenIdsRef.current.add(r.id));
      }
    }).catch(() => {});

    const interval = setInterval(async () => {
      try {
        const sentReminders = await taskApi.getReminders({ status: 'sent' });
        if (Array.isArray(sentReminders)) {
          const now = Date.now();
          for (const rem of sentReminders) {
            if (!seenIdsRef.current.has(rem.id)) {
              // Check if delivered in the last 45 seconds
              const delTime = rem.delivered_at ? new Date(rem.delivered_at).getTime() : 0;
              if (delTime && (now - delTime) < 45000) {
                triggerNotification(rem);
              } else {
                seenIdsRef.current.add(rem.id);
              }
            }
          }
        }
      } catch (_) {}
    }, 8000);

    return () => clearInterval(interval);
  }, [token]);

  if (!activeNotification) return null;

  return (
    <div className="fixed top-5 right-5 z-50 animate-in fade-in slide-in-from-top-4 duration-300">
      <div className="flex items-start gap-3.5 p-4 bg-[#111116]/95 border border-accent/40 rounded-2xl shadow-[0_10px_35px_rgba(0,0,0,0.6),0_0_25px_rgba(214,181,106,0.25)] text-[#EDE8DF] max-w-sm backdrop-blur-xl">
        <div className="w-10 h-10 rounded-xl bg-accent/20 border border-accent/40 flex items-center justify-center text-accent shrink-0 animate-bounce">
          <Bell size={20} />
        </div>

        <div className="flex-1 pr-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] font-bold text-accent uppercase tracking-wider flex items-center gap-1">
              <Volume2 size={11} />
              TARK Reminder Alert
            </span>
            <span className="text-[10px] text-[#8E8B85]">{activeNotification.time}</span>
          </div>
          <h4 className="text-xs font-semibold text-white mt-1 leading-snug">
            {activeNotification.title}
          </h4>
          <p className="text-[11px] text-emerald-400 mt-1 flex items-center gap-1">
            <CheckCircle2 size={11} />
            Delivered via TARK Background Worker
          </p>
        </div>

        <button
          onClick={() => setActiveNotification(null)}
          className="text-[#8E8B85] hover:text-white p-1 hover:bg-white/[0.05] rounded-lg transition-all"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
