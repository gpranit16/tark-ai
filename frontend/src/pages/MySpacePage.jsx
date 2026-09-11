import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Sparkles,
  CheckSquare,
  Calendar as CalendarIcon,
  Bell,
  Target,
  Clock,
  ArrowRight,
  Plus,
  AlertCircle,
  ExternalLink,
  CheckCircle2,
  Circle,
  RefreshCw,
  Zap,
  Flame,
  ChevronRight,
  TrendingUp,
  X,
  Volume2,
  CalendarCheck,
  Compass,
} from 'lucide-react';
import clsx from 'clsx';

import { taskApi } from '../api/taskApi';
import { integrationsApi } from '../api/integrationsApi';
import { listMemories } from '../api/memoryApi';
import { useAuthStore } from '../stores/useAuthStore';
import { useTaskStore } from '../stores/taskStore';
import TaskModal from '../components/tasks/TaskModal';
import { playReminderChime } from '../components/tasks/ReminderNotificationListener';

export default function MySpacePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const { isTaskModalOpen, editingTask, openCreateModal, closeTaskModal } = useTaskStore();

  // Local States
  const [isReminderModalOpen, setIsReminderModalOpen] = useState(false);
  const [reminderTitle, setReminderTitle] = useState('');
  const [reminderOffsetMinutes, setReminderOffsetMinutes] = useState(15);
  const [isCreatingReminder, setIsCreatingReminder] = useState(false);
  const [isConnectingCalendar, setIsConnectingCalendar] = useState(false);

  // Time & Greeting
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000 * 60);
    return () => clearInterval(timer);
  }, []);

  const getGreeting = () => {
    const hour = currentTime.getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
  };

  const formattedDate = currentTime.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  });

  // Calculate day bounds for calendar
  const startOfDay = new Date();
  startOfDay.setHours(0, 0, 0, 0);
  const endOfDay = new Date();
  endOfDay.setHours(23, 59, 59, 999);

  // 1. Fetch Today's Tasks
  const { data: todayTasks = [], isLoading: isLoadingTodayTasks } = useQuery({
    queryKey: ['tasks', 'today'],
    queryFn: () => taskApi.getTasks({ time_frame: 'today' }),
  });

  // 2. Fetch Overdue Tasks
  const { data: overdueTasks = [] } = useQuery({
    queryKey: ['tasks', 'overdue'],
    queryFn: () => taskApi.getTasks({ time_frame: 'overdue' }),
  });

  // 3. Fetch Task Categories for TaskModal
  const { data: categories = [] } = useQuery({
    queryKey: ['task-categories'],
    queryFn: () => taskApi.getCategories(),
  });

  // 4. Fetch Reminders (Active / Scheduled)
  const { data: activeReminders = [], isLoading: isLoadingReminders } = useQuery({
    queryKey: ['reminders', 'scheduled'],
    queryFn: () => taskApi.getReminders({ status: 'scheduled' }),
    refetchInterval: 15000,
  });

  // 5. Fetch Google Calendar Connection Status
  const { data: calendarStatus, isLoading: isLoadingCalStatus } = useQuery({
    queryKey: ['integration-google-calendar-status'],
    queryFn: () => integrationsApi.getGoogleCalendarStatus(),
    staleTime: 30000,
  });

  const isCalendarConnected = !!(calendarStatus?.connected || calendarStatus?.is_connected);
  const accountEmail = calendarStatus?.account_email;

  // 6. Fetch Today's Google Calendar Events
  const { data: calendarData, isLoading: isLoadingEvents } = useQuery({
    queryKey: ['integration-google-calendar-events-today', isCalendarConnected],
    queryFn: () =>
      integrationsApi.getUpcomingEvents({
        timeMin: startOfDay.toISOString(),
        timeMax: endOfDay.toISOString(),
        maxResults: 20,
      }),
    enabled: isCalendarConnected,
    refetchInterval: 30000,
  });

  const todayEvents = Array.isArray(calendarData) ? calendarData : (calendarData?.events || []);

  // 7. Fetch Goals from Memory API
  const { data: memoryData, isLoading: isLoadingGoals } = useQuery({
    queryKey: ['memories', 'goal'],
    queryFn: () => listMemories({ category: 'goal', limit: 10 }),
    staleTime: 60000,
  });

  const goals = memoryData?.memories || (Array.isArray(memoryData) ? memoryData : []);

  // 8. AI Daily Plan Query & Mutation
  const {
    data: dailyPlan,
    isLoading: isLoadingPlan,
    refetch: refetchDailyPlan,
    isFetching: isFetchingPlan,
  } = useQuery({
    queryKey: ['daily-plan', 'today'],
    queryFn: () => taskApi.generateDailyPlan('today', 'Asia/Kolkata'),
    staleTime: 1000 * 60 * 10,
    retry: false,
  });

  const planMutation = useMutation({
    mutationFn: () => taskApi.generateDailyPlan('today', 'Asia/Kolkata'),
    onSuccess: (data) => {
      queryClient.setQueryData(['daily-plan', 'today'], data);
    },
  });

  // Task Mutations
  const toggleTaskMutation = useMutation({
    mutationFn: async ({ taskId, isCompleted }) => {
      if (isCompleted) {
        return taskApi.reopenTask(taskId);
      } else {
        return taskApi.completeTask(taskId);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
  });

  const createTaskMutation = useMutation({
    mutationFn: (taskData) => taskApi.createTask(taskData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      closeTaskModal();
    },
  });

  // Reminder Mutation
  const createReminderMutation = useMutation({
    mutationFn: (data) => taskApi.createReminder(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reminders'] });
      setIsReminderModalOpen(false);
      setReminderTitle('');
    },
  });

  const handleCreateReminderSubmit = async (e) => {
    e.preventDefault();
    if (!reminderTitle.trim()) return;
    try {
      setIsCreatingReminder(true);
      const targetTime = new Date(Date.now() + reminderOffsetMinutes * 60 * 1000);
      await createReminderMutation.mutateAsync({
        title: reminderTitle.trim(),
        reminder_time: targetTime.toISOString(),
        delivery_channel: 'in_app',
      });
    } catch (err) {
      alert(`Could not schedule reminder: ${err?.message || 'Unknown error'}`);
    } finally {
      setIsCreatingReminder(false);
    }
  };

  const handleConnectCalendar = async () => {
    try {
      setIsConnectingCalendar(true);
      const res = await integrationsApi.getGoogleCalendarAuthUrl(true);
      if (res?.authorization_url) {
        window.location.href = res.authorization_url;
      }
    } catch (err) {
      alert('Failed to initiate Google Calendar connection.');
    } finally {
      setIsConnectingCalendar(false);
    }
  };

  // Format Helper for Time String
  const formatEventTime = (timeStr) => {
    if (!timeStr) return '';
    try {
      const d = new Date(timeStr);
      return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    } catch {
      return timeStr;
    }
  };

  const formatRelativeReminder = (dateStr) => {
    if (!dateStr) return '';
    const diffMs = new Date(dateStr) - new Date();
    const diffMins = Math.round(diffMs / 60000);
    if (diffMins <= 0) return 'Due now';
    if (diffMins < 60) return `in ${diffMins}m`;
    const diffHours = Math.floor(diffMins / 60);
    const remMins = diffMins % 60;
    return `in ${diffHours}h ${remMins > 0 ? `${remMins}m` : ''}`;
  };

  // Animation variants
  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: { staggerChildren: 0.08 },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 12 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: 'easeOut' } },
  };

  const pendingTasks = todayTasks.filter((t) => t.status !== 'completed');
  const completedTodayTasks = todayTasks.filter((t) => t.status === 'completed');

  return (
    <div className="flex-1 h-full w-full overflow-y-auto bg-[#060608] text-[#EDE8DF] selection:bg-accent/20 selection:text-accent font-sans">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 pb-24 space-y-8">
        {/* ========================================================================= */}
        {/* 1. HERO HEADER */}
        {/* ========================================================================= */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="relative overflow-hidden rounded-3xl bg-gradient-to-b from-[#121216] via-[#0E0E12] to-[#0A0A0D] border border-white/[0.07] p-6 sm:p-8 shadow-2xl"
        >
          {/* Subtle Ambient Gold Glow */}
          <div className="absolute top-0 right-1/4 w-96 h-48 bg-accent/5 rounded-full blur-3xl pointer-events-none" />
          <div className="absolute -bottom-10 right-10 w-64 h-40 bg-accent/5 rounded-full blur-2xl pointer-events-none" />

          <div className="relative z-10 flex flex-col lg:flex-row lg:items-center justify-between gap-6">
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs font-semibold tracking-wider text-accent uppercase">
                <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                <span>Personal OS • Command Center</span>
              </div>
              <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-[#F5F2EB]">
                Your space. Your day.
              </h1>
              <p className="text-sm text-[#8E8B85] max-w-2xl font-normal leading-relaxed">
                {getGreeting()}, <span className="text-[#EDE8DF] font-medium">{user?.name || user?.email?.split('@')[0] || 'Explorer'}</span>. 
                Today is {formattedDate}. Here is your synchronized intelligence pulse.
              </p>
            </div>

            {/* Quick Action Buttons */}
            <div className="flex flex-wrap items-center gap-2.5">
              <button
                onClick={() => planMutation.mutate()}
                disabled={planMutation.isPending || isFetchingPlan}
                className="px-4 py-2.5 bg-gradient-to-r from-accent via-[#E5C77E] to-accent text-black font-semibold rounded-xl text-xs hover:brightness-110 active:scale-[0.98] transition-all flex items-center gap-2 shadow-[0_0_20px_rgba(214,181,106,0.22)] disabled:opacity-50 cursor-pointer"
              >
                <Sparkles size={14} className={clsx((planMutation.isPending || isFetchingPlan) && 'animate-spin')} />
                <span>{planMutation.isPending || isFetchingPlan ? 'Synthesizing...' : 'Plan My Day'}</span>
              </button>

              <button
                onClick={openCreateModal}
                className="px-3.5 py-2.5 bg-[#141418] hover:bg-[#1C1C22] border border-white/[0.08] hover:border-accent/40 rounded-xl text-xs font-medium text-[#EDE8DF] hover:text-accent transition-all flex items-center gap-1.5 cursor-pointer"
              >
                <Plus size={13} />
                <span>Add Task</span>
              </button>

              <button
                onClick={() => setIsReminderModalOpen(true)}
                className="px-3.5 py-2.5 bg-[#141418] hover:bg-[#1C1C22] border border-white/[0.08] hover:border-accent/40 rounded-xl text-xs font-medium text-[#EDE8DF] hover:text-accent transition-all flex items-center gap-1.5 cursor-pointer"
              >
                <Bell size={13} />
                <span>Create Reminder</span>
              </button>

              <button
                onClick={() => {
                  if (isCalendarConnected) {
                    window.open('https://calendar.google.com', '_blank');
                  } else {
                    handleConnectCalendar();
                  }
                }}
                className="px-3.5 py-2.5 bg-[#141418] hover:bg-[#1C1C22] border border-white/[0.08] hover:border-accent/40 rounded-xl text-xs font-medium text-[#EDE8DF] hover:text-accent transition-all flex items-center gap-1.5 cursor-pointer"
              >
                <CalendarIcon size={13} />
                <span>{isCalendarConnected ? 'Open Calendar' : 'Connect Calendar'}</span>
              </button>

              <Link
                to="/memory"
                className="px-3.5 py-2.5 bg-[#141418] hover:bg-[#1C1C22] border border-white/[0.08] hover:border-accent/40 rounded-xl text-xs font-medium text-[#EDE8DF] hover:text-accent transition-all flex items-center gap-1.5"
              >
                <Target size={13} />
                <span>View Goals</span>
              </Link>
            </div>
          </div>
        </motion.div>

        {/* ========================================================================= */}
        {/* 2. TODAY OVERVIEW STATS CARDS */}
        {/* ========================================================================= */}
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
        >
          {/* Card 1: Today's Tasks */}
          <motion.div
            variants={itemVariants}
            onClick={() => navigate('/tasks')}
            className="group relative bg-[#0D0D10] hover:bg-[#121216] border border-white/[0.06] hover:border-accent/30 rounded-2xl p-5 transition-all duration-200 cursor-pointer shadow-lg"
          >
            <div className="flex items-center justify-between mb-3">
              <div className="p-2.5 rounded-xl bg-accent/10 text-accent border border-accent/20">
                <CheckSquare size={18} />
              </div>
              <ChevronRight size={14} className="text-[#666672] group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
            </div>
            <div className="space-y-1">
              <div className="text-2xl sm:text-3xl font-bold tracking-tight text-[#F5F2EB]">
                {isLoadingTodayTasks ? '–' : todayTasks.length}
              </div>
              <div className="text-xs text-[#8E8B85] font-medium flex items-center justify-between">
                <span>Today's Tasks</span>
                <span className="text-[10px] text-accent/80 font-mono">
                  {completedTodayTasks.length}/{todayTasks.length} done
                </span>
              </div>
            </div>
          </motion.div>

          {/* Card 2: Overdue Tasks */}
          <motion.div
            variants={itemVariants}
            onClick={() => navigate('/tasks')}
            className={clsx(
              'group relative bg-[#0D0D10] hover:bg-[#121216] border rounded-2xl p-5 transition-all duration-200 cursor-pointer shadow-lg',
              overdueTasks.length > 0
                ? 'border-red-500/30 hover:border-red-500/60 bg-red-950/10'
                : 'border-white/[0.06] hover:border-accent/30'
            )}
          >
            <div className="flex items-center justify-between mb-3">
              <div
                className={clsx(
                  'p-2.5 rounded-xl border',
                  overdueTasks.length > 0
                    ? 'bg-red-500/15 text-red-400 border-red-500/30'
                    : 'bg-white/[0.04] text-[#8E8B85] border-white/[0.08]'
                )}
              >
                <AlertCircle size={18} />
              </div>
              <ChevronRight size={14} className="text-[#666672] group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
            </div>
            <div className="space-y-1">
              <div
                className={clsx(
                  'text-2xl sm:text-3xl font-bold tracking-tight',
                  overdueTasks.length > 0 ? 'text-red-400' : 'text-[#F5F2EB]'
                )}
              >
                {overdueTasks.length}
              </div>
              <div className="text-xs text-[#8E8B85] font-medium flex items-center justify-between">
                <span>Overdue Deadlines</span>
                {overdueTasks.length > 0 && (
                  <span className="text-[10px] text-red-400 font-medium">Requires action</span>
                )}
              </div>
            </div>
          </motion.div>

          {/* Card 3: Upcoming Reminders */}
          <motion.div
            variants={itemVariants}
            onClick={() => navigate('/tasks')}
            className="group relative bg-[#0D0D10] hover:bg-[#121216] border border-white/[0.06] hover:border-accent/30 rounded-2xl p-5 transition-all duration-200 cursor-pointer shadow-lg"
          >
            <div className="flex items-center justify-between mb-3">
              <div className="p-2.5 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
                <Bell size={18} />
              </div>
              <ChevronRight size={14} className="text-[#666672] group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
            </div>
            <div className="space-y-1">
              <div className="text-2xl sm:text-3xl font-bold tracking-tight text-[#F5F2EB]">
                {isLoadingReminders ? '–' : activeReminders.length}
              </div>
              <div className="text-xs text-[#8E8B85] font-medium flex items-center justify-between">
                <span>Active Reminders</span>
                <span className="text-[10px] text-purple-300 font-mono">In-App Chime</span>
              </div>
            </div>
          </motion.div>

          {/* Card 4: Google Calendar Events */}
          <motion.div
            variants={itemVariants}
            onClick={() => {
              if (isCalendarConnected) {
                window.open('https://calendar.google.com', '_blank');
              } else {
                handleConnectCalendar();
              }
            }}
            className="group relative bg-[#0D0D10] hover:bg-[#121216] border border-white/[0.06] hover:border-accent/30 rounded-2xl p-5 transition-all duration-200 cursor-pointer shadow-lg"
          >
            <div className="flex items-center justify-between mb-3">
              <div className="p-2.5 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20">
                <CalendarIcon size={18} />
              </div>
              <ChevronRight size={14} className="text-[#666672] group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
            </div>
            <div className="space-y-1">
              <div className="text-2xl sm:text-3xl font-bold tracking-tight text-[#F5F2EB]">
                {isCalendarConnected ? (isLoadingEvents ? '–' : todayEvents.length) : 'Off'}
              </div>
              <div className="text-xs text-[#8E8B85] font-medium flex items-center justify-between">
                <span>Today's Calendar</span>
                <span className={clsx('text-[10px]', isCalendarConnected ? 'text-blue-400' : 'text-[#77736D]')}>
                  {isCalendarConnected ? 'Google Synced' : 'Click to connect'}
                </span>
              </div>
            </div>
          </motion.div>
        </motion.div>

        {/* ========================================================================= */}
        {/* 3. TWO COLUMN PERSONAL OS LAYOUT */}
        {/* ========================================================================= */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* ======================================================================= */}
          {/* LEFT / MAIN COLUMN (7 cols on large screens) */}
          {/* ======================================================================= */}
          <div className="lg:col-span-7 space-y-8">
            {/* 3.1 AI DAILY PLAN SUMMARY */}
            <motion.div
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.1 }}
              className="bg-[#0D0D10] border border-white/[0.07] rounded-3xl p-6 sm:p-7 shadow-xl relative overflow-hidden"
            >
              {/* Header */}
              <div className="flex items-center justify-between pb-5 border-b border-white/[0.06] mb-5">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 rounded-xl bg-accent/10 text-accent border border-accent/20">
                    <Sparkles size={16} />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-[#F5F2EB]">AI Daily Plan</h2>
                    <p className="text-xs text-[#8E8B85]">Optimized blueprint for peak focus & calendar balance</p>
                  </div>
                </div>

                <button
                  onClick={() => planMutation.mutate()}
                  disabled={planMutation.isPending || isFetchingPlan}
                  className="px-3 py-1.5 rounded-lg bg-[#141418] hover:bg-[#1A1A20] text-accent text-xs font-medium border border-accent/25 hover:border-accent/50 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  title="Regenerate Plan"
                >
                  <RefreshCw size={12} className={clsx((planMutation.isPending || isFetchingPlan) && 'animate-spin')} />
                  <span>{planMutation.isPending || isFetchingPlan ? 'Re-planning...' : 'Refresh'}</span>
                </button>
              </div>

              {/* Plan Content */}
              {isLoadingPlan || planMutation.isPending ? (
                <div className="py-12 text-center space-y-3">
                  <div className="w-8 h-8 border-2 border-accent/30 border-t-accent rounded-full animate-spin mx-auto" />
                  <p className="text-xs text-[#8E8B85]">Synthesizing calendar events, tasks, and energy curve...</p>
                </div>
              ) : dailyPlan ? (
                <div className="space-y-5">
                  {/* Top Priorities Pills */}
                  {dailyPlan.top_priorities && dailyPlan.top_priorities.length > 0 && (
                    <div className="space-y-2">
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-accent uppercase tracking-wider">
                        <Flame size={13} />
                        <span>Core Priorities</span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {dailyPlan.top_priorities.map((item, idx) => (
                          <div
                            key={idx}
                            className="px-3 py-1.5 rounded-xl bg-accent/10 text-accent border border-accent/20 text-xs font-medium flex items-center gap-1.5"
                          >
                            <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                            <span>{item}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Compact Time Block Preview */}
                  {dailyPlan.time_blocks && dailyPlan.time_blocks.length > 0 ? (
                    <div className="space-y-2.5">
                      <div className="flex items-center justify-between text-xs text-[#8E8B85] font-medium px-1">
                        <span>Day Schedule</span>
                        <Link to="/tasks" className="text-accent hover:underline flex items-center gap-1">
                          <span>Full timeline</span>
                          <ArrowRight size={11} />
                        </Link>
                      </div>

                      <div className="space-y-2">
                        {dailyPlan.time_blocks.slice(0, 4).map((block, idx) => {
                          const isCal = block.type === 'calendar_event';
                          const isTask = block.type === 'task';

                          return (
                            <div
                              key={idx}
                              className={clsx(
                                'p-3 rounded-xl border flex items-center justify-between text-xs transition-all',
                                isCal
                                  ? 'bg-blue-950/20 border-blue-500/25 text-blue-200'
                                  : isTask
                                  ? 'bg-accent/5 border-accent/20 text-[#EDE8DF]'
                                  : 'bg-[#121216] border-white/[0.06] text-[#EDE8DF]'
                              )}
                            >
                              <div className="flex items-center gap-3 truncate">
                                <span className="font-mono text-[11px] text-[#8E8B85] shrink-0 min-w-[85px]">
                                  {block.start_time} - {block.end_time}
                                </span>
                                <span className="truncate font-medium">{block.title}</span>
                              </div>
                              <span
                                className={clsx(
                                  'text-[10px] px-2 py-0.5 rounded-md uppercase font-semibold shrink-0',
                                  isCal
                                    ? 'bg-blue-500/20 text-blue-300'
                                    : isTask
                                    ? 'bg-accent/20 text-accent'
                                    : 'bg-white/[0.06] text-[#8E8B85]'
                                )}
                              >
                                {isCal ? 'Calendar' : isTask ? 'Task Focus' : 'Routine'}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : (
                    <p className="text-xs text-[#8E8B85] italic">No active time blocks generated.</p>
                  )}

                  {/* Summary / Notes footer */}
                  {dailyPlan.summary && (
                    <div className="p-3.5 rounded-xl bg-[#101014] border border-white/[0.05] text-xs text-[#9E9B95] leading-relaxed">
                      💡 <span className="text-[#EDE8DF] font-medium">Daily Strategy:</span> {dailyPlan.summary}
                    </div>
                  )}
                </div>
              ) : (
                <div className="py-8 text-center space-y-3">
                  <p className="text-xs text-[#8E8B85]">
                    No daily plan has been generated yet for today.
                  </p>
                  <button
                    onClick={() => planMutation.mutate()}
                    className="px-4 py-2 bg-accent text-black font-semibold rounded-xl text-xs hover:bg-accent/90 transition-all inline-flex items-center gap-2 cursor-pointer shadow-[0_0_15px_rgba(214,181,106,0.2)]"
                  >
                    <Sparkles size={13} />
                    <span>Plan My Day Now</span>
                  </button>
                </div>
              )}
            </motion.div>

            {/* 3.2 TODAY'S TASKS PREVIEW */}
            <motion.div
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.15 }}
              className="bg-[#0D0D10] border border-white/[0.07] rounded-3xl p-6 sm:p-7 shadow-xl space-y-5"
            >
              <div className="flex items-center justify-between pb-4 border-b border-white/[0.06]">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 rounded-xl bg-accent/10 text-accent border border-accent/20">
                    <CheckSquare size={16} />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-[#F5F2EB]">Today's Focus Tasks</h2>
                    <p className="text-xs text-[#8E8B85]">Top priority items with today's deadline</p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <button
                    onClick={openCreateModal}
                    className="text-xs text-accent hover:text-accent/80 font-medium flex items-center gap-1 cursor-pointer"
                  >
                    <Plus size={13} />
                    <span>New Task</span>
                  </button>
                  <Link
                    to="/tasks"
                    className="text-xs text-[#8E8B85] hover:text-[#EDE8DF] font-medium flex items-center gap-1 transition-colors"
                  >
                    <span>View all ({todayTasks.length})</span>
                    <ArrowRight size={12} />
                  </Link>
                </div>
              </div>

              {/* Task Items List */}
              {isLoadingTodayTasks ? (
                <div className="py-8 text-center text-xs text-[#8E8B85]">Loading tasks...</div>
              ) : todayTasks.length === 0 ? (
                <div className="py-10 text-center space-y-3 bg-[#111115] rounded-2xl border border-dashed border-white/[0.08]">
                  <CheckCircle2 size={24} className="text-accent/50 mx-auto" />
                  <div className="space-y-1">
                    <p className="text-xs text-[#EDE8DF] font-medium">No tasks due today!</p>
                    <p className="text-[11px] text-[#8E8B85]">You're all clear or haven't scheduled tasks for today.</p>
                  </div>
                  <button
                    onClick={openCreateModal}
                    className="px-3 py-1.5 bg-[#1C1C22] hover:bg-accent/10 hover:text-accent hover:border-accent/40 border border-white/[0.08] rounded-lg text-xs font-medium text-[#EDE8DF] transition-all"
                  >
                    + Create a Task
                  </button>
                </div>
              ) : (
                <div className="space-y-2.5">
                  {todayTasks.slice(0, 5).map((task) => {
                    const isDone = task.status === 'completed';

                    return (
                      <div
                        key={task.id}
                        className={clsx(
                          'group p-3.5 rounded-xl border transition-all flex items-center justify-between gap-3',
                          isDone
                            ? 'bg-[#101013] border-white/[0.04] opacity-60'
                            : 'bg-[#121216] border-white/[0.06] hover:border-accent/30'
                        )}
                      >
                        <div className="flex items-center gap-3 min-w-0 flex-1">
                          <button
                            onClick={() =>
                              toggleTaskMutation.mutate({ taskId: task.id, isCompleted: isDone })
                            }
                            className={clsx(
                              'w-5 h-5 rounded-lg border flex items-center justify-center transition-all shrink-0 cursor-pointer',
                              isDone
                                ? 'bg-accent/20 border-accent text-accent'
                                : 'border-white/[0.2] hover:border-accent text-transparent'
                            )}
                          >
                            <CheckCircle2 size={13} className={clsx(isDone ? 'opacity-100' : 'opacity-0')} />
                          </button>

                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span
                                className={clsx(
                                  'text-xs font-medium truncate',
                                  isDone ? 'line-through text-[#77736D]' : 'text-[#EDE8DF]'
                                )}
                              >
                                {task.title}
                              </span>
                              {task.category && (
                                <span
                                  className="text-[9.5px] px-1.5 py-0.5 rounded font-medium shrink-0"
                                  style={{
                                    backgroundColor: `${task.category.color || '#D6B56A'}15`,
                                    color: task.category.color || '#D6B56A',
                                  }}
                                >
                                  {task.category.name}
                                </span>
                              )}
                            </div>
                            {task.description && (
                              <p className="text-[11px] text-[#77736D] truncate mt-0.5">
                                {task.description}
                              </p>
                            )}
                          </div>
                        </div>

                        {/* Priority / Time Pill */}
                        <div className="flex items-center gap-2 shrink-0">
                          {task.due_time && (
                            <span className="text-[11px] font-mono text-[#8E8B85] flex items-center gap-1">
                              <Clock size={11} />
                              {task.due_time.slice(0, 5)}
                            </span>
                          )}
                          <span
                            className={clsx(
                              'text-[9.5px] px-2 py-0.5 rounded uppercase font-semibold',
                              task.priority === 'urgent'
                                ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                                : task.priority === 'high'
                                ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
                                : 'bg-white/[0.06] text-[#8E8B85]'
                            )}
                          >
                            {task.priority}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </motion.div>
          </div>

          {/* ======================================================================= */}
          {/* RIGHT COLUMN (5 cols on large screens) */}
          {/* ======================================================================= */}
          <div className="lg:col-span-5 space-y-8">
            {/* 3.3 GOOGLE CALENDAR WIDGET */}
            <motion.div
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.2 }}
              className="bg-[#0D0D10] border border-white/[0.07] rounded-3xl p-6 shadow-xl space-y-4"
            >
              <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20">
                    <CalendarIcon size={16} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-base font-bold text-[#F5F2EB]">Google Calendar</h2>
                      {isCalendarConnected && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20 font-mono">
                          Connected
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-[#8E8B85]">
                      {isCalendarConnected && accountEmail ? accountEmail : 'Real-time synchronized events'}
                    </p>
                  </div>
                </div>

                {isCalendarConnected && (
                  <button
                    onClick={() => window.open('https://calendar.google.com', '_blank')}
                    className="text-xs text-blue-400 hover:text-blue-300 font-medium flex items-center gap-1 cursor-pointer"
                  >
                    <span>Open</span>
                    <ExternalLink size={12} />
                  </button>
                )}
              </div>

              {!isCalendarConnected ? (
                <div className="p-5 rounded-2xl bg-[#111116] border border-white/[0.06] text-center space-y-3">
                  <CalendarCheck size={28} className="text-blue-400/60 mx-auto" />
                  <div className="space-y-1">
                    <p className="text-xs font-semibold text-[#EDE8DF]">Calendar Not Connected</p>
                    <p className="text-[11px] text-[#8E8B85] max-w-xs mx-auto">
                      Connect your Google Calendar to view upcoming events and enable AI daily schedule synthesis.
                    </p>
                  </div>
                  <button
                    onClick={handleConnectCalendar}
                    disabled={isConnectingCalendar}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white font-medium rounded-xl text-xs transition-all shadow-[0_0_15px_rgba(59,130,246,0.25)] flex items-center gap-2 mx-auto cursor-pointer"
                  >
                    <CalendarIcon size={13} />
                    <span>{isConnectingCalendar ? 'Connecting...' : 'Connect Google Calendar'}</span>
                  </button>
                </div>
              ) : isLoadingEvents ? (
                <div className="py-6 text-center text-xs text-[#8E8B85]">Loading calendar events...</div>
              ) : todayEvents.length === 0 ? (
                <div className="py-6 text-center text-xs text-[#8E8B85] bg-[#111115] rounded-xl border border-white/[0.04]">
                  No calendar events scheduled for today.
                </div>
              ) : (
                <div className="space-y-2">
                  {todayEvents.map((ev, idx) => {
                    const startStr = ev.start?.dateTime || ev.start?.date;
                    const endStr = ev.end?.dateTime || ev.end?.date;
                    const isAllDay = !ev.start?.dateTime;

                    return (
                      <div
                        key={ev.id || idx}
                        className="p-3 rounded-xl bg-[#121216] border border-blue-500/20 hover:border-blue-500/40 transition-all space-y-1.5"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-semibold text-[#EDE8DF] truncate">
                            {ev.summary || 'Busy'}
                          </span>
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-500/10 text-blue-300 shrink-0">
                            {isAllDay
                              ? 'All Day'
                              : `${formatEventTime(startStr)} - ${formatEventTime(endStr)}`}
                          </span>
                        </div>
                        {ev.location && (
                          <p className="text-[11px] text-[#77736D] truncate">📍 {ev.location}</p>
                        )}
                        {ev.hangoutLink && (
                          <a
                            href={ev.hangoutLink}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-[11px] text-blue-400 hover:underline pt-0.5"
                          >
                            <span>Join Google Meet</span>
                            <ExternalLink size={10} />
                          </a>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </motion.div>

            {/* 3.4 ACTIVE REMINDERS WIDGET */}
            <motion.div
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.25 }}
              className="bg-[#0D0D10] border border-white/[0.07] rounded-3xl p-6 shadow-xl space-y-4"
            >
              <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
                    <Bell size={16} />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-[#F5F2EB]">Upcoming Reminders</h2>
                    <p className="text-xs text-[#8E8B85]">Loud multi-harmonic sound alerts</p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => playReminderChime()}
                    title="Test audio chime"
                    className="p-1.5 rounded-lg bg-[#141418] hover:bg-[#1C1C22] text-[#8E8B85] hover:text-accent transition-colors"
                  >
                    <Volume2 size={13} />
                  </button>
                  <button
                    onClick={() => setIsReminderModalOpen(true)}
                    className="text-xs text-purple-400 hover:text-purple-300 font-medium flex items-center gap-1 cursor-pointer"
                  >
                    <Plus size={13} />
                    <span>Set</span>
                  </button>
                </div>
              </div>

              {isLoadingReminders ? (
                <div className="py-6 text-center text-xs text-[#8E8B85]">Checking reminders...</div>
              ) : activeReminders.length === 0 ? (
                <div className="py-6 text-center text-xs text-[#8E8B85] bg-[#111115] rounded-xl border border-white/[0.04]">
                  No pending reminders right now.
                </div>
              ) : (
                <div className="space-y-2">
                  {activeReminders.slice(0, 4).map((rem) => (
                    <div
                      key={rem.id}
                      className="p-3 rounded-xl bg-[#121216] border border-purple-500/20 flex items-center justify-between gap-3 text-xs"
                    >
                      <div className="flex items-center gap-2.5 truncate">
                        <span className="w-2 h-2 rounded-full bg-purple-400 animate-pulse shrink-0" />
                        <span className="text-[#EDE8DF] font-medium truncate">{rem.title}</span>
                      </div>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/15 text-purple-300 shrink-0">
                        {formatRelativeReminder(rem.reminder_time)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>

            {/* 3.5 GOALS & AMBITIONS WIDGET */}
            <motion.div
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.3 }}
              className="bg-[#0D0D10] border border-white/[0.07] rounded-3xl p-6 shadow-xl space-y-4"
            >
              <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 rounded-xl bg-accent/10 text-accent border border-accent/20">
                    <Target size={16} />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-[#F5F2EB]">Goals & Objectives</h2>
                    <p className="text-xs text-[#8E8B85]">Long-term memory vectors</p>
                  </div>
                </div>

                <Link
                  to="/memory"
                  className="text-xs text-accent hover:text-accent/80 font-medium flex items-center gap-1"
                >
                  <span>View Goals</span>
                  <ArrowRight size={12} />
                </Link>
              </div>

              {isLoadingGoals ? (
                <div className="py-6 text-center text-xs text-[#8E8B85]">Loading goals...</div>
              ) : goals.length === 0 ? (
                <div className="py-6 text-center space-y-2 bg-[#111115] rounded-xl border border-white/[0.04]">
                  <p className="text-xs text-[#8E8B85]">No goals registered in Memory yet.</p>
                  <Link
                    to="/memory"
                    className="text-xs text-accent hover:underline inline-block font-medium"
                  >
                    + Define your goals in Memory
                  </Link>
                </div>
              ) : (
                <div className="space-y-2.5">
                  {goals.slice(0, 4).map((goal, idx) => (
                    <div
                      key={goal.id || idx}
                      className="p-3.5 rounded-xl bg-[#121216] border border-white/[0.06] hover:border-accent/30 transition-all space-y-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-[#EDE8DF] truncate">
                          {goal.key || goal.content || 'Goal'}
                        </span>
                        <span className="text-[10px] text-accent/80 bg-accent/10 px-2 py-0.5 rounded-md font-mono shrink-0">
                          {Math.round((goal.confidence || 0.9) * 100)}% active
                        </span>
                      </div>
                      {goal.value && (
                        <p className="text-[11px] text-[#8E8B85] line-clamp-2">{goal.value}</p>
                      )}
                      <div className="w-full bg-white/[0.05] h-1.5 rounded-full overflow-hidden">
                        <div
                          className="bg-accent h-full rounded-full transition-all duration-500"
                          style={{ width: `${Math.min(100, Math.round((goal.confidence || 0.8) * 100))}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 4. MODALS (Task Modal & Reminder Modal) */}
      {/* ========================================================================= */}
      {/* Task Creation Modal */}
      <TaskModal
        isOpen={isTaskModalOpen}
        onClose={closeTaskModal}
        onSave={(taskData) => createTaskMutation.mutate(taskData)}
        task={editingTask}
        categories={categories}
      />

      {/* Quick Reminder Creation Modal */}
      <AnimatePresence>
        {isReminderModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-[#111115] border border-white/[0.1] rounded-2xl w-full max-w-md p-6 space-y-4 shadow-2xl"
            >
              <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
                <div className="flex items-center gap-2 text-sm font-bold text-[#F5F2EB]">
                  <Bell size={16} className="text-purple-400" />
                  <span>Create Quick Reminder</span>
                </div>
                <button
                  onClick={() => setIsReminderModalOpen(false)}
                  className="text-[#77736D] hover:text-[#EDE8DF]"
                >
                  <X size={16} />
                </button>
              </div>

              <form onSubmit={handleCreateReminderSubmit} className="space-y-4">
                <div>
                  <label className="text-xs font-medium text-[#8E8B85] block mb-1.5">
                    What would you like to be reminded about?
                  </label>
                  <input
                    type="text"
                    required
                    value={reminderTitle}
                    onChange={(e) => setReminderTitle(e.target.value)}
                    placeholder="e.g. Call Rohit, Review quarterly budget, Take a water break"
                    className="w-full bg-[#16161C] border border-white/[0.08] focus:border-purple-500/50 rounded-xl px-3.5 py-2.5 text-xs text-[#EDE8DF] placeholder-[#666672] outline-none"
                    autoFocus
                  />
                </div>

                <div>
                  <label className="text-xs font-medium text-[#8E8B85] block mb-1.5">
                    Remind me in:
                  </label>
                  <div className="grid grid-cols-4 gap-2">
                    {[5, 15, 30, 60].map((mins) => (
                      <button
                        key={mins}
                        type="button"
                        onClick={() => setReminderOffsetMinutes(mins)}
                        className={clsx(
                          'py-2 rounded-xl text-xs font-medium border transition-all',
                          reminderOffsetMinutes === mins
                            ? 'bg-purple-500/20 text-purple-300 border-purple-500/50'
                            : 'bg-[#16161C] border-white/[0.06] text-[#8E8B85] hover:text-[#EDE8DF]'
                        )}
                      >
                        {mins < 60 ? `${mins}m` : '1h'}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsReminderModalOpen(false)}
                    className="px-4 py-2 rounded-xl text-xs font-medium text-[#8E8B85] hover:text-[#EDE8DF]"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isCreatingReminder || !reminderTitle.trim()}
                    className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white font-medium rounded-xl text-xs transition-all disabled:opacity-50 flex items-center gap-2 cursor-pointer shadow-[0_0_15px_rgba(168,85,247,0.25)]"
                  >
                    <Bell size={13} />
                    <span>{isCreatingReminder ? 'Setting...' : 'Set Reminder'}</span>
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
