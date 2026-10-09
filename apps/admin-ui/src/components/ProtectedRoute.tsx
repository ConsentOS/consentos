import { Navigate } from 'react-router-dom';

import { useAuthStore } from '../stores/auth';
import { LoadingState } from './ui/loading-state.tsx';

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuthStore();

  if (!isAuthenticated && isLoading) {
    return <LoadingState message="Loading..." />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
