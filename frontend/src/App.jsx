import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Layout from './components/layout/Layout';
import ProtectedRoute from './components/auth/ProtectedRoute';
import AuthPage from './pages/AuthPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import VerifyEmailPage from './pages/VerifyEmailPage';
import ChatRoute from './pages/ChatRoute';
import MemoryPage from './pages/MemoryPage';
import ProjectsPage from './pages/ProjectsPage';
import KnowledgePage from './pages/KnowledgePage';
import ToolsPage from './pages/ToolsPage';
import SettingsPage from './pages/SettingsPage';
import TasksPage from './pages/TasksPage';
import MySpacePage from './pages/MySpacePage';
import { useAuthStore } from './stores/useAuthStore';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function AppRouter() {
  const initialize = useAuthStore((s) => s.initialize);

  useEffect(() => {
    initialize();
  }, [initialize]);

  return (
    <BrowserRouter>
      <Routes>
        {/* Public Auth Routes */}
        <Route path="/login" element={<AuthPage initialMode="login" />} />
        <Route path="/signup" element={<AuthPage initialMode="signup" />} />
        <Route path="/forgot-password" element={<Navigate to="/login" replace />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/verify-email" element={<VerifyEmailPage />} />

        {/* Application Layout: Public Home + Protected Sub-routes */}
        <Route path="/" element={<Layout />}>
          {/* Public Home Route (Viewing & exploring composer is public) */}
          <Route index element={<ChatRoute />} />

          {/* Protected Routes (Authentication Required) */}
          <Route
            path="chat/:threadId"
            element={
              <ProtectedRoute>
                <ChatRoute />
              </ProtectedRoute>
            }
          />
          <Route
            path="my-space"
            element={
              <ProtectedRoute>
                <MySpacePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="projects"
            element={
              <ProtectedRoute>
                <ProjectsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="projects/:projectId"
            element={
              <ProtectedRoute>
                <ProjectsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="tasks"
            element={
              <ProtectedRoute>
                <TasksPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="knowledge"
            element={
              <ProtectedRoute>
                <KnowledgePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="memory"
            element={
              <ProtectedRoute>
                <MemoryPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="tools"
            element={
              <ProtectedRoute>
                <ToolsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="research"
            element={
              <ProtectedRoute>
                <div className="p-8 text-muted-foreground">Deep Research (Coming Soon)</div>
              </ProtectedRoute>
            }
          />
          <Route
            path="settings"
            element={
              <ProtectedRoute>
                <SettingsPage />
              </ProtectedRoute>
            }
          />
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppRouter />
    </QueryClientProvider>
  );
}

export default App;
