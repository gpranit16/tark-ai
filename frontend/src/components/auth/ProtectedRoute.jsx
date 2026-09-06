import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../../stores/useAuthStore';

export default function ProtectedRoute({ children }) {
  const { isAuthenticated, isInitialized } = useAuthStore();
  const location = useLocation();

  const token = localStorage.getItem('tarkai_access_token');

  // If no token in storage or explicit unauthenticated state after initialization
  if (!isAuthenticated && !token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (isInitialized && !isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}

