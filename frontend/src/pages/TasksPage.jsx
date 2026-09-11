import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  CheckSquare,
  Plus,
  Calendar,
  Clock,
  Search,
  Filter,
  Sparkles,
  AlertCircle,
  Layers,
  ArrowUpDown,
  CheckCircle2,
  CalendarDays,
  Bell,
} from 'lucide-react';
import clsx from 'clsx';

import { taskApi } from '../api/taskApi';
import { useTaskStore } from '../stores/taskStore';
import TaskCard from '../components/tasks/TaskCard';
import TaskModal from '../components/tasks/TaskModal';
import CategoryPills from '../components/tasks/CategoryPills';
import DailyPlannerView from '../components/tasks/DailyPlannerView';
import RemindersView from '../components/tasks/RemindersView';

export default function TasksPage() {
  const queryClient = useQueryClient();

  const {
    activeTab,
    setActiveTab,
    selectedCategoryId,
    setSelectedCategoryId,
    selectedPriority,
    setSelectedPriority,
    searchQuery,
    setSearchQuery,
    sortBy,
    setSortBy,
    isTaskModalOpen,
    editingTask,
    openCreateModal,
    openEditModal,
    closeTaskModal,
  } = useTaskStore();

  const [quickTitle, setQuickTitle] = useState('');
  const [syncingTaskId, setSyncingTaskId] = useState(null);

  // 1. Fetch Categories
  const { data: categories = [] } = useQuery({
    queryKey: ['task-categories'],
    queryFn: () => taskApi.getCategories(),
  });

  // 2. Fetch Tasks
  const { data: tasks = [], isLoading: isLoadingTasks } = useQuery({
    queryKey: ['tasks', activeTab, selectedCategoryId, selectedPriority, searchQuery, sortBy],
    queryFn: () =>
      taskApi.getTasks({
        time_frame: activeTab === 'all' || activeTab === 'daily_plan' ? undefined : activeTab,
        category_id: selectedCategoryId || undefined,
        priority: selectedPriority || undefined,
        search: searchQuery || undefined,
        sort_by: sortBy,
      }),
  });

  // 3. Fetch Daily Plan when on daily_plan tab
  const {
    data: planData,
    isLoading: isLoadingPlan,
    refetch: refetchPlan,
  } = useQuery({
    queryKey: ['daily-plan'],
    queryFn: () => taskApi.generateDailyPlan('today'),
    enabled: activeTab === 'daily_plan',
  });

  // Mutations
  const createCategoryMutation = useMutation({
    mutationFn: (catData) => taskApi.createCategory(catData),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['task-categories'] }),
  });

  const deleteCategoryMutation = useMutation({
    mutationFn: (catId) => taskApi.deleteCategory(catId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['task-categories'] }),
  });

  const createTaskMutation = useMutation({
    mutationFn: (taskData) => taskApi.createTask(taskData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['daily-plan'] });
      closeTaskModal();
    },
  });

  const updateTaskMutation = useMutation({
    mutationFn: ({ id, data }) => taskApi.updateTask(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['daily-plan'] });
      closeTaskModal();
    },
  });

  const deleteTaskMutation = useMutation({
    mutationFn: (id) => taskApi.deleteTask(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['daily-plan'] });
    },
  });

  const toggleCompleteMutation = useMutation({
    mutationFn: (task) =>
      task.status === 'completed' ? taskApi.reopenTask(task.id) : taskApi.completeTask(task.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['daily-plan'] });
    },
  });

  const syncCalendarMutation = useMutation({
    mutationFn: ({ taskId, payload }) => taskApi.syncToCalendar(taskId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['daily-plan'] });
      alert('Event successfully synced to your Google Calendar!');
    },
    onError: (err) => {
      alert(`Could not sync to Google Calendar: ${err?.response?.data?.detail || err.message}`);
    },
  });

  // Quick Task Creation handler
  const handleQuickAdd = async (e) => {
    e.preventDefault();
    if (!quickTitle.trim()) return;

    const today = new Date().toISOString().split('T')[0];
    await createTaskMutation.mutateAsync({
      title: quickTitle.trim(),
      due_date: activeTab === 'tomorrow' ? new Date(Date.now() + 86400000).toISOString().split('T')[0] : today,
      category_id: selectedCategoryId || null,
      priority: selectedPriority || 'medium',
    });
    setQuickTitle('');
  };

  const handleSyncToCalendar = (task) => {
    const today = task.due_date || new Date().toISOString().split('T')[0];
    const time = task.due_time || '10:00:00';
    const startIso = `${today}T${time}`;
    if (window.confirm(`Schedule "${task.title}" to Google Calendar on ${today} at ${time}?`)) {
      syncCalendarMutation.mutate({
        taskId: task.id,
        payload: { start_time: startIso, timezone: 'Asia/Kolkata' },
      });
    }
  };

  const tabs = [
    { id: 'today', label: 'Today', icon: Calendar },
    { id: 'upcoming', label: 'Upcoming', icon: CalendarDays },
    { id: 'overdue', label: 'Overdue', icon: AlertCircle },
    { id: 'completed', label: 'Completed', icon: CheckCircle2 },
    { id: 'all', label: 'All Tasks', icon: Layers },
    { id: 'reminders', label: 'Reminders', icon: Bell },
    { id: 'daily_plan', label: 'AI Daily Plan', icon: Sparkles, special: true },
  ];

  return (
    <div className="flex-1 h-full overflow-y-auto bg-[#060608] text-[#EDE8DF] p-6 lg:p-10 select-none">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header Title */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[11px] font-semibold text-accent uppercase tracking-widest">
                Personal OS
              </span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-[#EDE8DF] flex items-center gap-2.5">
              <CheckSquare size={24} className="text-accent" />
              <span>Tasks & Smart Planning</span>
            </h1>
          </div>

          <button
            onClick={openCreateModal}
            className="px-4 py-2.5 bg-accent hover:bg-accent/90 text-black font-semibold rounded-xl text-xs flex items-center gap-2 transition-all shadow-[0_0_20px_rgba(214,181,106,0.25)] hover:scale-[1.02] shrink-0"
          >
            <Plus size={15} />
            <span>New Task</span>
          </button>
        </div>

        {/* View Tabs */}
        <div className="flex items-center gap-1.5 p-1 bg-[#0D0D10] border border-white/[0.06] rounded-2xl overflow-x-auto text-xs scrollbar-none">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={clsx(
                  'px-3.5 py-2 rounded-xl font-medium transition-all duration-150 flex items-center gap-2 whitespace-nowrap',
                  isActive
                    ? tab.special
                      ? 'bg-gradient-to-r from-accent/20 to-accent/10 text-accent border border-accent/40 shadow-[0_0_15px_rgba(214,181,106,0.15)] font-semibold'
                      : 'bg-white/[0.08] text-[#EDE8DF] border border-white/[0.1] shadow-sm font-semibold'
                    : 'text-[#8E8B85] hover:text-[#EDE8DF] hover:bg-white/[0.03] border border-transparent'
                )}
              >
                <Icon size={14} className={clsx(tab.special && 'text-accent')} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Daily Plan View, Reminders View, or Task List View */}
        {activeTab === 'daily_plan' ? (
          <DailyPlannerView
            planData={planData}
            isLoadingPlan={isLoadingPlan}
            onRefreshPlan={(date) => taskApi.generateDailyPlan(date).then(() => refetchPlan())}
            onScheduleBlock={(block) => {
              if (block.task_id) {
                const foundTask = tasks.find((t) => String(t.id) === block.task_id);
                if (foundTask) handleSyncToCalendar(foundTask);
              }
            }}
          />
        ) : activeTab === 'reminders' ? (
          <RemindersView />
        ) : (
          <div className="space-y-5">
            {/* Category Filter Pills */}
            <CategoryPills
              categories={categories}
              selectedCategoryId={selectedCategoryId}
              onSelectCategory={setSelectedCategoryId}
              onCreateCategory={(data) => createCategoryMutation.mutateAsync(data)}
              onDeleteCategory={(id) => deleteCategoryMutation.mutateAsync(id)}
            />

            {/* Quick Add Bar */}
            <form onSubmit={handleQuickAdd} className="relative">
              <input
                type="text"
                placeholder="Quick add task: e.g. Revise DBMS queries for 45 mins (Press Enter)"
                value={quickTitle}
                onChange={(e) => setQuickTitle(e.target.value)}
                className="w-full pl-4 pr-24 py-3 bg-[#0D0D10] hover:bg-[#111115] focus:bg-[#111115] border border-white/[0.07] focus:border-accent/40 rounded-xl text-xs text-[#EDE8DF] placeholder-[#555562] focus:outline-none transition-all shadow-inner"
              />
              <button
                type="submit"
                disabled={!quickTitle.trim()}
                className="absolute right-2 top-2 px-3 py-1.5 bg-accent/15 hover:bg-accent text-accent hover:text-black font-semibold rounded-lg text-xs transition-all disabled:opacity-40"
              >
                Add
              </button>
            </form>

            {/* Search and Priority Filter Controls */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 text-xs">
              <div className="relative w-full sm:w-64">
                <Search size={13} className="absolute left-3 top-2.5 text-[#555562]" />
                <input
                  type="text"
                  placeholder="Search tasks..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-8 pr-3 py-1.5 bg-[#0D0D10] border border-white/[0.06] focus:border-accent/40 rounded-lg text-xs text-[#EDE8DF] focus:outline-none"
                />
              </div>

              <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
                {/* Priority Selector */}
                <select
                  value={selectedPriority || ''}
                  onChange={(e) => setSelectedPriority(e.target.value || null)}
                  className="px-2.5 py-1.5 bg-[#0D0D10] border border-white/[0.06] rounded-lg text-xs text-[#8E8B85] focus:outline-none"
                >
                  <option value="">All Priorities</option>
                  <option value="urgent">Urgent</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>

                {/* Sort Selector */}
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  className="px-2.5 py-1.5 bg-[#0D0D10] border border-white/[0.06] rounded-lg text-xs text-[#8E8B85] focus:outline-none"
                >
                  <option value="due_time">Sort by Due Time</option>
                  <option value="priority">Sort by Priority</option>
                  <option value="created_at">Sort by Created Date</option>
                  <option value="title">Sort by Title</option>
                </select>
              </div>
            </div>

            {/* Task Cards List */}
            {isLoadingTasks ? (
              <div className="py-16 text-center text-xs text-[#8E8B85] space-y-2">
                <div className="w-5 h-5 border-2 border-accent/30 border-t-accent rounded-full animate-spin mx-auto" />
                <p>Loading tasks...</p>
              </div>
            ) : tasks.length === 0 ? (
              <div className="py-16 text-center border border-dashed border-white/[0.06] rounded-2xl bg-[#0D0D10]/50 space-y-3">
                <CheckSquare size={28} className="text-[#555562] mx-auto stroke-[1.5]" />
                <div>
                  <h4 className="text-sm font-medium text-[#EDE8DF]">No tasks in this view</h4>
                  <p className="text-xs text-[#8E8B85] mt-1">
                    Add a new task above or ask TARK AI in chat to create one for you!
                  </p>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3">
                {tasks.map((task) => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    onToggleComplete={(t) => toggleCompleteMutation.mutate(t)}
                    onEdit={(t) => openEditModal(t)}
                    onDelete={(id) => deleteTaskMutation.mutate(id)}
                    onSyncCalendar={handleSyncToCalendar}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Task Creation & Edit Modal */}
        <TaskModal
          isOpen={isTaskModalOpen}
          onClose={closeTaskModal}
          task={editingTask}
          categories={categories}
          onSave={(data) => {
            if (editingTask) {
              updateTaskMutation.mutate({ id: editingTask.id, data });
            } else {
              createTaskMutation.mutate(data);
            }
          }}
        />
      </div>
    </div>
  );
}
