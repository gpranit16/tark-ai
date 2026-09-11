import React, { useState, useEffect } from 'react';
import { X, Calendar, Clock, Repeat, Bell, Tag, Sparkles } from 'lucide-react';
import clsx from 'clsx';

export default function TaskModal({
  isOpen,
  onClose,
  onSave,
  task = null,
  categories = [],
}) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [dueTime, setDueTime] = useState('');
  const [priority, setPriority] = useState('medium');
  const [estimatedDuration, setEstimatedDuration] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [isRecurring, setIsRecurring] = useState(false);
  const [recurrenceRule, setRecurrenceRule] = useState('daily');
  const [reminderOption, setReminderOption] = useState('none');

  useEffect(() => {
    if (task) {
      setTitle(task.title || '');
      setDescription(task.description || '');
      setDueDate(task.due_date || '');
      setDueTime(task.due_time || '');
      setPriority(task.priority || 'medium');
      setEstimatedDuration(task.estimated_duration ? String(task.estimated_duration) : '');
      setCategoryId(task.category_id || (task.category ? task.category.id : ''));
      setIsRecurring(task.is_recurring || false);
      setRecurrenceRule(task.recurrence_rule || 'daily');
      setReminderOption('none');
    } else {
      setTitle('');
      setDescription('');
      // Default due date to today
      const today = new Date().toISOString().split('T')[0];
      setDueDate(today);
      setDueTime('');
      setPriority('medium');
      setEstimatedDuration('30');
      setCategoryId(categories.length > 0 ? categories[0].id : '');
      setIsRecurring(false);
      setRecurrenceRule('daily');
      setReminderOption('none');
    }
  }, [task, categories, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!title.trim()) return;

    let reminderTime = null;
    if (reminderOption === 'due_time' && dueDate && dueTime) {
      reminderTime = new Date(`${dueDate}T${dueTime}:00`).toISOString();
    } else if (reminderOption === '15_min_before' && dueDate && dueTime) {
      const dt = new Date(`${dueDate}T${dueTime}:00`);
      dt.setMinutes(dt.getMinutes() - 15);
      reminderTime = dt.toISOString();
    } else if (reminderOption === '1_hour_before' && dueDate && dueTime) {
      const dt = new Date(`${dueDate}T${dueTime}:00`);
      dt.setHours(dt.getHours() - 1);
      reminderTime = dt.toISOString();
    }

    const payload = {
      title: title.trim(),
      description: description.trim() || null,
      due_date: dueDate || null,
      due_time: dueTime || null,
      priority,
      estimated_duration: estimatedDuration ? parseInt(estimatedDuration, 10) : null,
      category_id: categoryId || null,
      is_recurring: isRecurring,
      recurrence_rule: isRecurring ? recurrenceRule : null,
      ...(reminderTime ? { reminder_time: reminderTime } : {}),
    };

    onSave(payload);
  };

  const priorityOptions = [
    { value: 'low', label: 'Low', color: 'border-blue-500/30 text-blue-400 bg-blue-500/10' },
    { value: 'medium', label: 'Medium', color: 'border-[#D6B56A]/30 text-[#D6B56A] bg-[#D6B56A]/10' },
    { value: 'high', label: 'High', color: 'border-amber-500/30 text-amber-400 bg-amber-500/10' },
    { value: 'urgent', label: 'Urgent', color: 'border-red-500/30 text-red-400 bg-red-500/10' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[#0D0D10] border border-white/[0.08] w-full max-w-lg rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-5 py-4 border-b border-white/[0.06] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
            <h3 className="text-sm font-semibold text-[#EDE8DF]">
              {task ? 'Edit Task' : 'New Task'}
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-[#8E8B85] hover:text-[#EDE8DF] hover:bg-white/[0.06] transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="p-5 overflow-y-auto space-y-4 text-xs">
          {/* Title */}
          <div>
            <label className="block text-[11px] font-medium text-[#8E8B85] mb-1.5 uppercase tracking-wider">
              Title *
            </label>
            <input
              type="text"
              placeholder="e.g. Finish DBMS study session"
              value={title}
              autoFocus
              onChange={(e) => setTitle(e.target.value)}
              className="w-full px-3 py-2.5 bg-[#141418] border border-white/[0.08] focus:border-accent/40 rounded-xl text-sm text-[#EDE8DF] placeholder-[#555562] focus:outline-none transition-colors"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-[11px] font-medium text-[#8E8B85] mb-1.5 uppercase tracking-wider">
              Description / Notes
            </label>
            <textarea
              rows={2}
              placeholder="Add extra context, links, or sub-points..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full px-3 py-2 bg-[#141418] border border-white/[0.08] focus:border-accent/40 rounded-xl text-xs text-[#EDE8DF] placeholder-[#555562] focus:outline-none transition-colors resize-none"
            />
          </div>

          {/* Due Date & Time */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-medium text-[#8E8B85] mb-1.5 uppercase tracking-wider flex items-center gap-1">
                <Calendar size={11} />
                <span>Due Date</span>
              </label>
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="w-full px-3 py-2 bg-[#141418] border border-white/[0.08] focus:border-accent/40 rounded-xl text-xs text-[#EDE8DF] focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-[11px] font-medium text-[#8E8B85] mb-1.5 uppercase tracking-wider flex items-center gap-1">
                <Clock size={11} />
                <span>Due Time (Optional)</span>
              </label>
              <input
                type="time"
                value={dueTime}
                onChange={(e) => setDueTime(e.target.value)}
                className="w-full px-3 py-2 bg-[#141418] border border-white/[0.08] focus:border-accent/40 rounded-xl text-xs text-[#EDE8DF] focus:outline-none"
              />
            </div>
          </div>

          {/* Priority */}
          <div>
            <label className="block text-[11px] font-medium text-[#8E8B85] mb-1.5 uppercase tracking-wider">
              Priority
            </label>
            <div className="grid grid-cols-4 gap-2">
              {priorityOptions.map((opt) => (
                <button
                  type="button"
                  key={opt.value}
                  onClick={() => setPriority(opt.value)}
                  className={clsx(
                    'py-2 rounded-xl font-medium border text-center transition-all duration-150 text-[11px]',
                    priority === opt.value
                      ? opt.color + ' shadow-[0_0_12px_rgba(214,181,106,0.1)] font-semibold'
                      : 'bg-[#141418] border-white/[0.05] text-[#8E8B85] hover:text-[#EDE8DF]'
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Duration & Category */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-medium text-[#8E8B85] mb-1.5 uppercase tracking-wider flex items-center gap-1">
                <Clock size={11} />
                <span>Est. Duration</span>
              </label>
              <select
                value={estimatedDuration}
                onChange={(e) => setEstimatedDuration(e.target.value)}
                className="w-full px-3 py-2 bg-[#141418] border border-white/[0.08] focus:border-accent/40 rounded-xl text-xs text-[#EDE8DF] focus:outline-none"
              >
                <option value="">None</option>
                <option value="15">15 minutes</option>
                <option value="30">30 minutes</option>
                <option value="45">45 minutes</option>
                <option value="60">1 hour (60 min)</option>
                <option value="90">1.5 hours (90 min)</option>
                <option value="120">2 hours (120 min)</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-medium text-[#8E8B85] mb-1.5 uppercase tracking-wider flex items-center gap-1">
                <Tag size={11} />
                <span>Category</span>
              </label>
              <select
                value={categoryId}
                onChange={(e) => setCategoryId(e.target.value)}
                className="w-full px-3 py-2 bg-[#141418] border border-white/[0.08] focus:border-accent/40 rounded-xl text-xs text-[#EDE8DF] focus:outline-none"
              >
                <option value="">No Category</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Recurrence & Reminder Controls */}
          <div className="pt-2 border-t border-white/[0.04] space-y-3">
            {/* Recurring toggle */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Repeat size={13} className="text-[#8E8B85]" />
                <span className="text-xs text-[#EDE8DF] font-medium">Recurring Task</span>
              </div>
              <input
                type="checkbox"
                checked={isRecurring}
                onChange={(e) => setIsRecurring(e.target.checked)}
                className="rounded bg-[#141418] border-white/[0.2] text-accent focus:ring-0 cursor-pointer"
              />
            </div>

            {isRecurring && (
              <div className="pl-5">
                <select
                  value={recurrenceRule}
                  onChange={(e) => setRecurrenceRule(e.target.value)}
                  className="w-full px-3 py-1.5 bg-[#141418] border border-purple-500/30 rounded-lg text-xs text-purple-300 focus:outline-none"
                >
                  <option value="daily">Every Day</option>
                  <option value="weekdays">Weekdays (Mon-Fri)</option>
                  <option value="weekly">Every Week</option>
                  <option value="monthly">Every Month</option>
                </select>
              </div>
            )}

            {/* Reminder */}
            {!task && dueTime && (
              <div>
                <label className="block text-[11px] font-medium text-[#8E8B85] mb-1 flex items-center gap-1">
                  <Bell size={11} />
                  <span>Reminder</span>
                </label>
                <select
                  value={reminderOption}
                  onChange={(e) => setReminderOption(e.target.value)}
                  className="w-full px-3 py-2 bg-[#141418] border border-white/[0.08] focus:border-accent/40 rounded-xl text-xs text-[#EDE8DF] focus:outline-none"
                >
                  <option value="none">No reminder</option>
                  <option value="due_time">At time of event</option>
                  <option value="15_min_before">15 minutes before</option>
                  <option value="1_hour_before">1 hour before</option>
                </select>
              </div>
            )}
          </div>

          {/* Footer Buttons */}
          <div className="pt-3 border-t border-white/[0.06] flex items-center justify-end gap-2.5">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs text-[#8E8B85] hover:text-[#EDE8DF] hover:bg-white/[0.05] transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!title.trim()}
              className="px-5 py-2 rounded-xl text-xs font-semibold bg-accent text-black hover:bg-accent/90 disabled:opacity-50 transition-all shadow-[0_0_15px_rgba(214,181,106,0.25)] flex items-center gap-1.5"
            >
              <span>{task ? 'Update Task' : 'Create Task'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
