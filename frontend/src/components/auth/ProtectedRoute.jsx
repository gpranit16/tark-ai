import React, { useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../../stores/useAuthStore';

export default function ProtectedRoute({ children }) {
  const { isAuthenticated, isLoading, initialize } = useAuthStore();
  const location = useLocation();

  useEffect(() => {
    initialize();
  }, [initialize]);

  if (isLoading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-black">
        <div className="flex flex-col items-center gap-4">
          <div className="relative flex items-center justify-center">
            <div className="h-12 w-12 rounded-full border border-champagne/30 border-t-champagne animate-spin" />
            <div className="absolute h-6 w-6 rounded-full bg-champagne/10 blur-[6px]" />
          </div>
          <div className="font-sans text-xs tracking-widest text-white/40 uppercase">
            Authenticating Session
          </div>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}
