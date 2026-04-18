import { useMemo, useState } from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';

import { useAuthStore } from '../stores/auth';
import { getNavItems } from '../extensions/registry';

const CORE_NAV_ITEMS = [
  { path: '/sites', label: 'Sites', order: 10 },
  { path: '/consent', label: 'Consent Records', order: 15 },
  { path: '/settings', label: 'Settings', order: 90 },
];

export default function Layout() {
  const { user, logout } = useAuthStore();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  const NAV_ITEMS = useMemo(() => {
    const extensionItems = getNavItems().map((item) => ({
      path: item.path,
      label: item.label,
      order: item.order ?? 200,
    }));
    return [...CORE_NAV_ITEMS, ...extensionItems].sort(
      (a, b) => a.order - b.order,
    );
  }, []);

  return (
    <div className="min-h-screen bg-background">
      {/* Top nav */}
      <header className="sticky top-0 z-40 border-b border-border-subtle bg-card">
        <div className="flex h-14 items-center justify-between px-4 md:px-6">
          {/* Left: logo + desktop nav */}
          <div className="flex items-center gap-8">
            <Link to="/" className="flex items-center gap-2 font-heading text-lg font-semibold text-foreground">
              <img src="/logo-mark.svg" alt="" width="24" height="24" aria-hidden="true" />
              <span>
                <span className="text-primary">Consent</span>
                <span className="text-action">OS</span>
              </span>
            </Link>

            {/* Desktop nav */}
            <nav className="hidden items-center gap-6 md:flex">
              {NAV_ITEMS.map((item) => {
                const isActive = location.pathname.startsWith(item.path);
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={`relative pb-[17px] font-heading text-sm transition-colors ${
                      isActive
                        ? 'font-semibold text-foreground'
                        : 'font-medium text-text-tertiary hover:text-foreground'
                    }`}
                  >
                    {item.label}
                    {isActive && (
                      <span className="absolute bottom-0 left-0 right-0 h-0.5 rounded-full bg-copper" />
                    )}
                  </Link>
                );
              })}
            </nav>
          </div>

          {/* Right: user info + mobile hamburger */}
          <div className="flex items-center gap-4">
            <div className="hidden items-center gap-3 md:flex">
              <span className="text-sm text-text-secondary">
                {user?.full_name ?? user?.email}
              </span>
              <button
                onClick={logout}
                className="text-sm text-text-tertiary hover:text-foreground"
              >
                Sign out
              </button>
            </div>

            {/* Mobile hamburger */}
            <button
              onClick={() => setMobileOpen(!mobileOpen)}
              className="rounded-md p-1.5 text-text-tertiary hover:bg-mist md:hidden"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                {mobileOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
                )}
              </svg>
            </button>
          </div>
        </div>

        {/* Mobile slide-down nav */}
        {mobileOpen && (
          <nav className="border-t border-border-subtle bg-card px-4 py-3 md:hidden">
            {NAV_ITEMS.map((item) => {
              const isActive = location.pathname.startsWith(item.path);
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={() => setMobileOpen(false)}
                  className={`block rounded-md px-3 py-2 text-sm font-medium ${
                    isActive
                      ? 'bg-mist text-foreground'
                      : 'text-text-tertiary hover:bg-mist hover:text-foreground'
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
            <div className="mt-3 border-t border-border-subtle pt-3">
              <p className="px-3 text-sm text-text-secondary">
                {user?.full_name ?? user?.email}
              </p>
              <button
                onClick={logout}
                className="mt-1 w-full rounded-md px-3 py-2 text-left text-sm text-text-tertiary hover:bg-mist hover:text-foreground"
              >
                Sign out
              </button>
            </div>
          </nav>
        )}
      </header>

      {/* Main content */}
      <main className="w-full px-6 py-10 md:px-12">
        <div className="mx-auto max-w-7xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
