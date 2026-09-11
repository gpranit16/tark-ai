import { fetchApi } from './apiClient';

export const taskApi = {
  // Tasks
  getTasks: async (params = {}) => {
    const query = new URLSearchParams();
    if (params.status) query.set('status', params.status);
    if (params.priority) query.set('priority', params.priority);
    if (params.category_id) query.set('category_id', params.category_id);
    if (params.time_frame) query.set('time_frame', params.time_frame);
    if (params.search) query.set('search', params.search);
    if (params.sort_by) query.set('sort_by', params.sort_by);
    if (params.order) query.set('order', params.order);

    const qs = query.toString();
    return fetchApi(`/api/v1/tasks${qs ? `?${qs}` : ''}`);
  },

  getTask: async (taskId) => {
    return fetchApi(`/api/v1/tasks/${taskId}`);
  },

  createTask: async (taskData) => {
    return fetchApi('/api/v1/tasks', {
      method: 'POST',
      body: JSON.stringify(taskData),
    });
  },

  updateTask: async (taskId, updateData) => {
    return fetchApi(`/api/v1/tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify(updateData),
    });
  },

  deleteTask: async (taskId) => {
    return fetchApi(`/api/v1/tasks/${taskId}`, {
      method: 'DELETE',
    });
  },

  completeTask: async (taskId) => {
    return fetchApi(`/api/v1/tasks/${taskId}/complete`, {
      method: 'POST',
    });
  },

  reopenTask: async (taskId) => {
    return fetchApi(`/api/v1/tasks/${taskId}/reopen`, {
      method: 'POST',
    });
  },

  syncToCalendar: async (taskId, payload) => {
    return fetchApi(`/api/v1/tasks/${taskId}/sync-calendar`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // Categories
  getCategories: async () => {
    return fetchApi('/api/v1/tasks/categories');
  },

  createCategory: async (categoryData) => {
    return fetchApi('/api/v1/tasks/categories', {
      method: 'POST',
      body: JSON.stringify(categoryData),
    });
  },

  deleteCategory: async (categoryId) => {
    return fetchApi(`/api/v1/tasks/categories/${categoryId}`, {
      method: 'DELETE',
    });
  },

  // Reminders
  getReminders: async (params = {}) => {
    const query = new URLSearchParams();
    if (params.status) query.set('status', params.status);
    if (params.time_frame) query.set('time_frame', params.time_frame);
    const qs = query.toString();
    return fetchApi(`/api/v1/tasks/reminders${qs ? `?${qs}` : ''}`);
  },

  createReminder: async (reminderData) => {
    return fetchApi('/api/v1/tasks/reminders', {
      method: 'POST',
      body: JSON.stringify(reminderData),
    });
  },

  cancelReminder: async (reminderId) => {
    return fetchApi(`/api/v1/tasks/reminders/${reminderId}`, {
      method: 'DELETE',
    });
  },

  // Smart Daily Planning
  generateDailyPlan: async (targetDate = 'today', timezone = 'Asia/Kolkata') => {
    const query = new URLSearchParams();
    query.set('target_date', targetDate);
    query.set('timezone', timezone);
    return fetchApi(`/api/v1/tasks/plan-day?${query.toString()}`, {
      method: 'POST',
    });
  },
};
