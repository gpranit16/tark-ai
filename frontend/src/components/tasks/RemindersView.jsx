import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Bell,
  Plus,
  Clock,
  CheckCircle2,
  Trash2,
  AlertCircle,
  Calendar,
  Sparkles,
  Zap,
  Volume2,
} from 'lucide-react';
import clsx from 'clsx';
import { taskApi } from '../../api/taskApi';
import { playReminderChime } from './ReminderNotificationListener';

export default function RemindersView() {
  const queryClient = useQueryClient();
  const [filterStatus, setFilterStatus] = useState('all'); // 'all' | 'scheduled' | 'sent'
  const [quickTitle, setQuickTitle] = useState('');
  const [quickOffsetMinutes, setQuickOffsetMinutes] = useState(2);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [soundTested, setSoundTested] = useState(false);

  const handleTestSound = () => {
    playReminderChime();
    setSoundTested(true);
    setTimeout(() => setSoundTested(false), 2000);
  };


  // 1. Fetch Reminders
  const { data: reminders = [], isLoading } = useQuery({
    queryKey: ['reminders', filterStatus],
    queryFn: () =>
      taskApi.getReminders({
        status: filterStatus === 'all' ? undefined : filterStatus,
      }),
    refetchInterval: 10000, // auto-refresh every 10s to reflect worker status updates
  });

  // 2. Mutations
  const createReminderMutation = useMutation({
    mutationFn: (data) => taskApi.createReminder(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reminders'] });
      setQuickTitle('');
    },
  });

  const cancelReminderMutation = useMutation({
    mutationFn: (id) => taskApi.cancelReminder(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reminders'] });
    },
  });

  const handleQuickCreate = async (e) => {
    e.preventDefault();
    if (!quickTitle.trim()) return;

    try {
      setIsSubmitting(true);
      const targetTime = new Date(Date.now() + quickOffsetMinutes * 60 * 1000);
      await createReminderMutation.mutateAsync({
        title: quickTitle.trim(),
        reminder_time: targetTime.toISOString(),
        delivery_channel: 'in_app',
      });
    } catch (err) {
      alert(`Could not create reminder: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const scheduledCount = reminders.filter((r) => r.status === 'scheduled').length;
  const sentCount = reminders.filter((r) => r.status === 'sent').length;

  const formatRelativeTime = (isoString) => {
    try {
      const dt = new Date(isoString);
      const now = new Date();
      const diffMs = dt - now;
      const diffMins = Math.round(diffMs / (60 * 1000));

      if (diffMins > 0) {
        if (diffMins < 60) return `In ${diffMins} min${diffMins > 1 ? 's' : ''}`;
        const hours = Math.floor(diffMins / 60);
        const remMins = diffMins % 60;
        return `In ${hours}h ${remMins > 0 ? `${remMins}m` : ''}`;
      } else if (diffMins === 0) {
        return 'Right now';
      } else {
        const pastMins = Math.abs(diffMins);
        if (pastMins < 60) return `${pastMins} min${pastMins > 1 ? 's' : ''} ago`;
        const pastHours = Math.floor(pastMins / 60);
        return `${pastHours}h ago`;
      }
    } catch {
      return '';
    }
  };

  const formatExactTime = (isoString) => {
    try {
      const dt = new Date(isoString);
      return dt.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoString;
    }
  };

  return (
    <div className="space-y-6">
      {/* Overview Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
        <div className="p-4 bg-[#0D0D10] border border-white/[0.07] rounded-2xl flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-xl bg-accent/10 border border-accent/20 flex items-center justify-center text-accent">
            <Bell size={18} />
          </div>
          <div>
            <div className="text-xl font-bold text-[#EDE8DF]">{scheduledCount}</div>
            <div className="text-[11px] text-[#8E8B85]">Active Scheduled</div>
          </div>
        </div>

        <div className="p-4 bg-[#0D0D10] border border-white/[0.07] rounded-2xl flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <CheckCircle2 size={18} />
          </div>
          <div>
            <div className="text-xl font-bold text-[#EDE8DF]">{sentCount}</div>
            <div className="text-[11px] text-[#8E8B85]">Delivered / Sent</div>
          </div>
        </div>

        <div className="p-4 bg-[#0D0D10] border border-white/[0.07] rounded-2xl flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
            <Zap size={18} />
          </div>
          <div>
            <div className="text-xl font-bold text-[#EDE8DF]">Live Poller</div>
            <div className="text-[11px] text-emerald-400 flex items-center gap-1 font-mono">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              15s Worker Active
            </div>
          </div>
        </div>
      </div>

      {/* Quick Reminder Creation Form */}
      <form
        onSubmit={handleQuickCreate}
        className="p-4 bg-[#0D0D10] border border-white/[0.07] rounded-2xl space-y-3"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-semibold text-[#EDE8DF]">
            <Sparkles size={14} className="text-accent" />
            <span>Quick Set Reminder</span>
          </div>

          <button
            type="button"
            onClick={handleTestSound}
            className="px-2.5 py-1 bg-white/[0.05] hover:bg-white/[0.1] text-accent text-[11px] font-medium rounded-lg flex items-center gap-1.5 transition-all border border-white/[0.06]"
          >
            <Volume2 size={12} />
            <span>{soundTested ? 'Playing Chime...' : 'Test Alert Sound'}</span>
          </button>
        </div>

        <div className="flex flex-col sm:flex-row items-center gap-2.5">
          <input
            type="text"
            placeholder="Reminder note: e.g. Test TARK reminder or Submit report"
            value={quickTitle}
            onChange={(e) => setQuickTitle(e.target.value)}
            className="flex-1 w-full px-3.5 py-2.5 bg-[#060608] border border-white/[0.08] focus:border-accent/40 rounded-xl text-xs text-[#EDE8DF] placeholder-[#555562] focus:outline-none transition-all"
          />

          <select
            value={quickOffsetMinutes}
            onChange={(e) => setQuickOffsetMinutes(Number(e.target.value))}
            className="w-full sm:w-44 px-3 py-2.5 bg-[#060608] border border-white/[0.08] rounded-xl text-xs text-[#EDE8DF] focus:outline-none"
          >
            <option value={1}>In 1 minute</option>
            <option value={2}>In 2 minutes</option>
            <option value={5}>In 5 minutes</option>
            <option value={10}>In 10 minutes</option>
            <option value={15}>In 15 minutes</option>
            <option value={30}>In 30 minutes</option>
            <option value={60}>In 1 hour</option>
            <option value={120}>In 2 hours</option>
          </select>

          <button
            type="submit"
            disabled={!quickTitle.trim() || isSubmitting}
            className="w-full sm:w-auto px-4 py-2.5 bg-accent hover:bg-accent/90 text-black font-semibold rounded-xl text-xs flex items-center justify-center gap-1.5 transition-all shadow-[0_0_15px_rgba(214,181,106,0.2)] disabled:opacity-40 shrink-0"
          >
            <Plus size={14} />
            <span>Set Reminder</span>
          </button>
        </div>
      </form>

      {/* Filter Tabs */}
      <div className="flex items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-1.5 p-1 bg-[#0D0D10] border border-white/[0.06] rounded-xl">
          {[
            { id: 'all', label: 'All Reminders' },
            { id: 'scheduled', label: 'Scheduled' },
            { id: 'sent', label: 'Delivered' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setFilterStatus(tab.id)}
              className={clsx(
                'px-3 py-1.5 rounded-lg font-medium transition-all text-xs',
                filterStatus === tab.id
                  ? 'bg-white/[0.08] text-[#EDE8DF] border border-white/[0.1] font-semibold'
                  : 'text-[#8E8B85] hover:text-[#EDE8DF]'
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="text-[11px] text-[#8E8B85]">
          PostgreSQL Synced • Real-time SSE
        </div>
      </div>

      {/* Reminders List */}
      {isLoading ? (
        <div className="py-16 text-center text-xs text-[#8E8B85] space-y-2">
          <div className="w-5 h-5 border-2 border-accent/30 border-t-accent rounded-full animate-spin mx-auto" />
          <p>Loading reminders...</p>
        </div>
      ) : reminders.length === 0 ? (
        <div className="py-16 text-center border border-dashed border-white/[0.06] rounded-2xl bg-[#0D0D10]/50 space-y-3">
          <Bell size={28} className="text-[#555562] mx-auto stroke-[1.5]" />
          <div>
            <h4 className="text-sm font-medium text-[#EDE8DF]">No reminders found</h4>
            <p className="text-xs text-[#8E8B85] mt-1">
              Create a quick reminder above or ask TARK AI in chat: &ldquo;Remind me in 2 minutes to test&rdquo;
            </p>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-2.5">
          {reminders.map((reminder) => {
            const isScheduled = reminder.status === 'scheduled';
            const isSent = reminder.status === 'sent';

            return (
              <div
                key={reminder.id}
                className={clsx(
                  'p-4 rounded-2xl border transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 group',
                  isScheduled
                    ? 'bg-[#0D0D10] border-white/[0.08] hover:border-accent/40 shadow-sm'
                    : 'bg-[#0A0A0D]/60 border-white/[0.04] opacity-80'
                )}
              >
                <div className="flex items-start sm:items-center gap-3.5">
                  <div
                    className={clsx(
                      'w-9 h-9 rounded-xl flex items-center justify-center shrink-0 mt-0.5 sm:mt-0',
                      isScheduled
                        ? 'bg-accent/15 border border-accent/30 text-accent'
                        : isSent
                        ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400'
                        : 'bg-white/[0.05] text-[#8E8B85]'
                    )}
                  >
                    <Bell size={16} className={clsx(isScheduled && 'animate-pulse')} />
                  </div>

                  <div>
                    <h4 className="text-xs font-semibold text-[#EDE8DF] flex items-center gap-2">
                      <span>{reminder.title}</span>
                      {isScheduled && (
                        <span className="px-2 py-0.5 bg-accent/10 border border-accent/25 text-accent text-[10px] rounded-full font-medium">
                          {formatRelativeTime(reminder.reminder_time)}
                        </span>
                      )}
                    </h4>
                    <div className="flex items-center gap-3 text-[11px] text-[#8E8B85] mt-1">
                      <span className="flex items-center gap-1">
                        <Clock size={11} />
                        {formatExactTime(reminder.reminder_time)}
                      </span>
                      <span>•</span>
                      <span className="capitalize">{reminder.delivery_channel || 'In-App SSE'}</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2.5 self-end sm:self-center">
                  <span
                    className={clsx(
                      'px-2.5 py-1 rounded-lg text-[10px] font-semibold uppercase tracking-wider',
                      isScheduled
                        ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                        : isSent
                        ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                        : 'bg-white/[0.06] text-[#8E8B85] border border-white/[0.08]'
                    )}
                  >
                    {reminder.status}
                  </span>

                  {isScheduled && (
                    <button
                      onClick={() => {
                        if (window.confirm(`Cancel reminder "${reminder.title}"?`)) {
                          cancelReminderMutation.mutate(reminder.id);
                        }
                      }}
                      className="p-1.5 text-[#555562] hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-all"
                      title="Cancel Reminder"
                    >
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
