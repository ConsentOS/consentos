import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';

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
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  // Close user menu on outside click
  useEffect(() => {
    if (!userMenuOpen) return;
    const handler = (e: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [userMenuOpen]);

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

          {/* Right: user menu + mobile hamburger */}
          <div className="flex items-center gap-4">
            <div className="relative hidden md:block" ref={userMenuRef}>
              <button
                type="button"
                onClick={() => setUserMenuOpen((v) => !v)}
                className="flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm text-text-secondary transition-colors hover:bg-mist hover:text-foreground"
              >
                <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-copper/10 font-heading text-xs font-semibold text-copper">
                  {(user?.full_name ?? user?.email ?? '?')[0].toUpperCase()}
                </span>
                {user?.full_name ?? user?.email}
                <svg className="h-4 w-4 text-text-tertiary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {userMenuOpen && (
                <div className="absolute right-0 mt-1 w-48 overflow-hidden rounded-lg border border-border bg-card shadow-lg">
                  <button
                    type="button"
                    onClick={() => { setUserMenuOpen(false); navigate('/account'); }}
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-foreground hover:bg-mist"
                  >
                    <svg className="h-4 w-4 text-text-tertiary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                    Account
                  </button>
                  <div className="border-t border-border" />
                  <button
                    type="button"
                    onClick={() => { setUserMenuOpen(false); logout(); }}
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-text-tertiary hover:bg-mist hover:text-foreground"
                  >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                    </svg>
                    Sign out
                  </button>
                </div>
              )}
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
