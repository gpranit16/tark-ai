import React, { useState } from 'react';
import {
  Sparkles,
  Calendar,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Flame,
  ArrowRight,
  RefreshCw,
  CalendarCheck,
} from 'lucide-react';
import clsx from 'clsx';
import { taskApi } from '../../api/taskApi';

export default function DailyPlannerView({
  planData,
  isLoadingPlan,
  onRefreshPlan,
  onScheduleBlock,
}) {
  const [selectedDate, setSelectedDate] = useState('today');

  const handleDateChange = (date) => {
    setSelectedDate(date);
    onRefreshPlan(date);
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Header Banner */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-[#111115] via-[#16161B] to-[#121215] border border-white/[0.08] p-6 shadow-xl">
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1.5">
              <Sparkles size={16} className="text-accent" />
              <span className="text-xs font-semibold text-accent uppercase tracking-widest">
                TARK Intelligent Daily Planner
              </span>
            </div>
            <h2 className="text-xl font-bold text-[#EDE8DF] tracking-tight">
              {planData ? planData.target_date : "Today's Agenda & Time-Blocks"}
            </h2>
            <p className="text-xs text-[#8E8B85] mt-1 max-w-xl">
              Synthesized by cross-referencing your live Google Calendar events, top-priority tasks, user goals, and available daylight focus slots.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <div className="bg-[#0B0B0E] p-1 rounded-xl border border-white/[0.06] flex items-center gap-1 text-xs">
              <button
                onClick={() => handleDateChange('today')}
                className={clsx(
                  'px-3 py-1.5 rounded-lg font-medium transition-all',
                  selectedDate === 'today'
                    ? 'bg-accent/15 text-accent border border-accent/30'
                    : 'text-[#8E8B85] hover:text-[#EDE8DF]'
                )}
              >
                Today
              </button>
              <button
                onClick={() => handleDateChange('tomorrow')}
                className={clsx(
                  'px-3 py-1.5 rounded-lg font-medium transition-all',
                  selectedDate === 'tomorrow'
                    ? 'bg-accent/15 text-accent border border-accent/30'
                    : 'text-[#8E8B85] hover:text-[#EDE8DF]'
                )}
              >
                Tomorrow
              </button>
            </div>

            <button
              onClick={() => onRefreshPlan(selectedDate)}
              disabled={isLoadingPlan}
              className="px-4 py-2 bg-accent text-black font-semibold rounded-xl text-xs hover:bg-accent/90 transition-all flex items-center gap-2 disabled:opacity-50 shadow-[0_0_15px_rgba(214,181,106,0.25)]"
            >
              <RefreshCw size={13} className={clsx(isLoadingPlan && 'animate-spin')} />
              <span>{isLoadingPlan ? 'Synthesizing...' : 'Replan'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Summary Stat Cards */}
      {planData && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="bg-[#0D0D10] border border-white/[0.06] rounded-xl p-4 flex items-center gap-3.5">
            <div className="p-2.5 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20">
              <Calendar size={18} />
            </div>
            <div>
              <div className="text-xl font-bold text-[#EDE8DF]">
                {planData.calendar_events_count}
              </div>
              <div className="text-[11px] text-[#8E8B85]">Google Calendar Events</div>
            </div>
          </div>

          <div className="bg-[#0D0D10] border border-white/[0.06] rounded-xl p-4 flex items-center gap-3.5">
            <div className="p-2.5 rounded-xl bg-accent/10 text-accent border border-accent/20">
              <CheckCircle2 size={18} />
            </div>
            <div>
              <div className="text-xl font-bold text-[#EDE8DF]">
                {planData.tasks_count}
              </div>
              <div className="text-[11px] text-[#8E8B85]">Prioritized Tasks</div>
            </div>
          </div>

          <div className="bg-[#0D0D10] border border-white/[0.06] rounded-xl p-4 flex items-center gap-3.5">
            <div className="p-2.5 rounded-xl bg-red-500/10 text-red-400 border border-red-500/20">
              <AlertTriangle size={18} />
            </div>
            <div>
              <div className="text-xl font-bold text-[#EDE8DF]">
                {planData.overdue_count}
              </div>
              <div className="text-[11px] text-[#8E8B85]">Overdue Deadlines</div>
            </div>
          </div>
        </div>
      )}

      {/* Top Priorities Focus */}
      {planData && planData.top_priorities && planData.top_priorities.length > 0 && (
        <div className="bg-[#0D0D10] border border-accent/20 rounded-xl p-4 shadow-[0_0_20px_rgba(214,181,106,0.05)]">
          <div className="flex items-center gap-2 mb-3">
            <Flame size={14} className="text-accent" />
            <h4 className="text-xs font-semibold text-[#EDE8DF] uppercase tracking-wider">
              Top Focus & Priorities
            </h4>
          </div>
          <div className="flex flex-wrap gap-2">
            {planData.top_priorities.map((item, idx) => (
              <span
                key={idx}
                className="px-3 py-1.5 rounded-lg bg-accent/10 text-accent border border-accent/20 text-xs font-medium"
              >
                {item}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Structured Time Blocks Timeline */}
      <div className="bg-[#0D0D10] border border-white/[0.06] rounded-2xl p-5 space-y-4">
        <h3 className="text-sm font-semibold text-[#EDE8DF] flex items-center gap-2">
          <Clock size={15} className="text-accent" />
          <span>Scheduled Day Timeline</span>
        </h3>

        {isLoadingPlan ? (
          <div className="py-12 text-center text-xs text-[#8E8B85] space-y-2">
            <div className="w-6 h-6 border-2 border-accent/30 border-t-accent rounded-full animate-spin mx-auto" />
            <p>Analyzing Google Calendar events and allocating focus slots...</p>
          </div>
        ) : !planData || !planData.time_blocks || planData.time_blocks.length === 0 ? (
          <div className="py-12 text-center text-xs text-[#8E8B85]">
            No schedule blocks created yet. Click "Replan" to synthesize today's schedule!
          </div>
        ) : (
          <div className="space-y-3">
            {planData.time_blocks.map((block, idx) => {
              const isCal = block.type === 'calendar_event';
              const isTask = block.type === 'task';
              const isRoutine = block.type === 'routine';

              return (
                <div
                  key={idx}
                  className={clsx(
                    'group relative p-3.5 rounded-xl border transition-all duration-150 flex items-center justify-between gap-4',
                    isCal
                      ? 'bg-blue-950/20 border-blue-500/20 hover:border-blue-500/40'
                      : isTask
                      ? 'bg-[#121216] border-white/[0.06] hover:border-white/[0.14]'
                      : 'bg-white/[0.02] border-dashed border-white/[0.05]'
                  )}
                >
                  <div className="flex items-center gap-4 flex-1 min-w-0">
                    {/* Time Pill */}
                    <div className="text-xs font-mono font-medium text-accent shrink-0 min-w-[130px] bg-[#09090B] px-2.5 py-1.5 rounded-lg border border-white/[0.05] text-center">
                      {block.start_time} — {block.end_time}
                    </div>

                    {/* Block Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h4 className="text-xs font-semibold text-[#EDE8DF] truncate">
                          {block.title}
                        </h4>
                        <span
                          className={clsx(
                            'text-[9px] uppercase px-1.5 py-0.5 rounded font-medium tracking-wider',
                            isCal
                              ? 'bg-blue-500/15 text-blue-400 border border-blue-500/20'
                              : isTask
                              ? 'bg-accent/15 text-accent border border-accent/25'
                              : 'bg-white/[0.05] text-[#8E8B85]'
                          )}
                        >
                          {isCal ? 'Calendar Event' : isTask ? 'Task Block' : 'Routine'}
                        </span>
                      </div>
                      {block.notes && (
                        <p className="text-[11px] text-[#8E8B85] mt-0.5 truncate">
                          {block.notes}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  {isTask && block.task_id && onScheduleBlock && (
                    <button
                      onClick={() => onScheduleBlock(block)}
                      className="opacity-0 group-hover:opacity-100 px-3 py-1.5 rounded-lg bg-accent/10 hover:bg-accent/20 text-accent border border-accent/20 text-xs font-medium flex items-center gap-1.5 transition-all"
                      title="Sync this time block to Google Calendar"
                    >
                      <CalendarCheck size={12} />
                      <span>Sync to Calendar</span>
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
