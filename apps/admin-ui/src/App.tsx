import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from 'react-router-dom';

import Layout from './components/Layout';
import { trackPageView } from './services/analytics';
import ProtectedRoute from './components/ProtectedRoute';
import LoginPage from './pages/LoginPage';
import SettingsPage from './pages/SettingsPage';
import SiteDetailPage from './pages/SiteDetailPage';
import SiteGroupDetailPage from './pages/SiteGroupDetailPage';
import SitesPage from './pages/SitesPage';
import { useAuthStore } from './stores/auth';
import { discoverExtensions, getPages } from './extensions/registry';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

function AppRoutes() {
  const { loadUser, isAuthenticated } = useAuthStore();
  const location = useLocation();
  const [extensionsReady, setExtensionsReady] = useState(false);

  useEffect(() => {
    loadUser();
    discoverExtensions().then(() => setExtensionsReady(true));
  }, [loadUser]);

  useEffect(() => {
    trackPageView(location.pathname);
  }, [location.pathname]);

  const extensionPages = extensionsReady ? getPages() : [];

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/sites" element={<SitesPage />} />
        <Route path="/sites/:siteId" element={<SiteDetailPage />} />
        <Route path="/groups/:groupId" element={<SiteGroupDetailPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        {extensionPages
          .filter((p) => p.protected !== false)
          .map((p) => (
            <Route key={p.path} path={p.path} element={<p.component />} />
          ))}
      </Route>
      {extensionPages
        .filter((p) => p.protected === false)
        .map((p) => (
          <Route key={p.path} path={p.path} element={<p.component />} />
        ))}
      <Route
        path="*"
        element={<Navigate to={isAuthenticated ? '/sites' : '/login'} replace />}
      />
    </Routes>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
