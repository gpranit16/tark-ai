import React from 'react';
import {
  Calendar,
  CheckCircle2,
  Clock,
  Circle,
  Repeat,
  Trash2,
  Edit2,
  AlertCircle,
  ExternalLink,
  CalendarCheck,
} from 'lucide-react';
import clsx from 'clsx';

export default function TaskCard({
  task,
  onToggleComplete,
  onEdit,
  onDelete,
  onSyncCalendar,
}) {
  const isCompleted = task.status === 'completed';
  const isCancelled = task.status === 'cancelled';

  // Format priority colors
  const priorityConfig = {
    urgent: { label: 'Urgent', bg: 'bg-red-500/10 text-red-400 border-red-500/20' },
    high: { label: 'High', bg: 'bg-amber-500/10 text-amber-400 border-amber-500/20' },
    medium: { label: 'Medium', bg: 'bg-[#D6B56A]/10 text-[#D6B56A] border-[#D6B56A]/20' },
    low: { label: 'Low', bg: 'bg-blue-500/10 text-blue-400 border-blue-500/20' },
  };

  const pConfig = priorityConfig[task.priority] || priorityConfig.medium;

  // Check if overdue
  const isOverdue =
    !isCompleted &&
    !isCancelled &&
    task.due_date &&
    new Date(task.due_date).setHours(0, 0, 0, 0) < new Date().setHours(0, 0, 0, 0);

  return (
    <div
      className={clsx(
        'group relative bg-[#0D0D10] hover:bg-[#121216] border rounded-xl p-3.5 transition-all duration-200 flex flex-col gap-2.5',
        isCompleted
          ? 'border-white/[0.03] opacity-60'
          : isOverdue
          ? 'border-red-500/30 shadow-[0_0_15px_rgba(239,68,68,0.08)]'
          : 'border-white/[0.06] hover:border-white/[0.12] shadow-sm'
      )}
    >
      <div className="flex items-start justify-between gap-3">
        {/* Left: Checkbox + Title */}
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <button
            onClick={() => onToggleComplete(task)}
            className="mt-0.5 text-[#666675] hover:text-accent transition-colors shrink-0"
            title={isCompleted ? 'Mark pending' : 'Mark completed'}
          >
            {isCompleted ? (
              <CheckCircle2 size={18} className="text-accent fill-accent/10" />
            ) : (
              <Circle size={18} className="hover:scale-110 transition-transform" />
            )}
          </button>

          <div className="flex-1 min-w-0">
            <h4
              onClick={() => onEdit(task)}
              className={clsx(
                'text-sm font-medium tracking-tight cursor-pointer hover:text-accent transition-colors truncate',
                isCompleted ? 'line-through text-[#6F6B64]' : 'text-[#EDE8DF]'
              )}
            >
              {task.title}
            </h4>

            {task.description && (
              <p className="text-xs text-[#8A8780] line-clamp-2 mt-0.5 leading-relaxed">
                {task.description}
              </p>
            )}
          </div>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          {!task.synced_to_calendar && !isCompleted && onSyncCalendar && (
            <button
              onClick={() => onSyncCalendar(task)}
              className="p-1.5 hover:bg-white/[0.06] text-[#8E8B85] hover:text-accent rounded-lg transition-colors"
              title="Schedule to Google Calendar"
            >
              <CalendarCheck size={14} />
            </button>
          )}
          <button
            onClick={() => onEdit(task)}
            className="p-1.5 hover:bg-white/[0.06] text-[#8E8B85] hover:text-[#EDE8DF] rounded-lg transition-colors"
            title="Edit task"
          >
            <Edit2 size={13} />
          </button>
          <button
            onClick={() => onDelete(task.id)}
            className="p-1.5 hover:bg-red-500/10 text-[#8E8B85] hover:text-red-400 rounded-lg transition-colors"
            title="Delete task"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {/* Metadata Badges Footer */}
      <div className="flex items-center justify-between gap-2 pt-1 border-t border-white/[0.03] text-[11px]">
        <div className="flex items-center gap-2 flex-wrap">
          {/* Priority */}
          <span
            className={clsx(
              'px-2 py-0.5 rounded-full font-medium border text-[10px] uppercase tracking-wider',
              pConfig.bg
            )}
          >
            {pConfig.label}
          </span>

          {/* Due Date & Time */}
          {task.due_date && (
            <span
              className={clsx(
                'flex items-center gap-1 px-2 py-0.5 rounded-md border font-mono',
                isOverdue
                  ? 'bg-red-500/10 text-red-400 border-red-500/20'
                  : 'bg-white/[0.03] text-[#8E8B85] border-white/[0.05]'
              )}
            >
              {isOverdue ? <AlertCircle size={11} /> : <Calendar size={11} />}
              <span>{task.due_date}</span>
              {task.due_time && <span>• {task.due_time}</span>}
            </span>
          )}

          {/* Duration */}
          {task.estimated_duration && (
            <span className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-white/[0.03] text-[#8E8B85] border border-white/[0.05]">
              <Clock size={11} />
              <span>{task.estimated_duration}m</span>
            </span>
          )}

          {/* Recurrence */}
          {task.is_recurring && (
            <span className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">
              <Repeat size={11} />
              <span className="capitalize">{task.recurrence_rule || 'Recurring'}</span>
            </span>
          )}

          {/* Category */}
          {task.category && (
            <span className="flex items-center gap-1 text-[#8E8B85]">
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ backgroundColor: task.category.color || '#D6B56A' }}
              />
              <span>{task.category.name}</span>
            </span>
          )}
        </div>

        {/* Calendar Linked Indicator */}
        {task.synced_to_calendar && (
          <span className="flex items-center gap-1 text-[10px] text-accent/90 bg-accent/10 px-2 py-0.5 rounded border border-accent/20">
            <CalendarCheck size={11} />
            <span>Calendar</span>
          </span>
        )}
      </div>
    </div>
  );
}
