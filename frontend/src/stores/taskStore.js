import { create } from 'zustand';

export const useTaskStore = create((set) => ({
  activeTab: 'today', // today, upcoming, overdue, completed, all, daily_plan
  selectedCategoryId: null,
  selectedPriority: null,
  searchQuery: '',
  sortBy: 'due_time',
  isTaskModalOpen: false,
  editingTask: null,

  setActiveTab: (tab) => set({ activeTab: tab }),
  setSelectedCategoryId: (catId) => set({ selectedCategoryId: catId }),
  setSelectedPriority: (priority) => set({ selectedPriority: priority }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  setSortBy: (sortBy) => set({ sortBy }),
  
  openCreateModal: () => set({ isTaskModalOpen: true, editingTask: null }),
  openEditModal: (task) => set({ isTaskModalOpen: true, editingTask: task }),
  closeTaskModal: () => set({ isTaskModalOpen: false, editingTask: null }),
}));
