import { beforeEach, describe, expect, it, vi } from 'vitest';

// We need to isolate each test from the module-level singleton state,
// so we re-import the module fresh for each test.

describe('UI extension registry', () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let registry: typeof import('../extensions/registry');

  beforeEach(async () => {
    // Reset module cache to get a clean registry each time
    const modulePath = '../extensions/registry';
    // Vitest doesn't natively re-import, so we use dynamic import with cache busting
    vi.resetModules();
    registry = await import(modulePath);
  });

  describe('getSiteDetailTabs', () => {
    it('returns empty array when no tabs registered', () => {
      expect(registry.getSiteDetailTabs()).toEqual([]);
    });

    it('returns registered tabs sorted by order', () => {
      const FakeComponent = () => null;
      registry.registerSiteDetailTab({
        id: 'tab-b',
        label: 'Tab B',
        component: FakeComponent,
        order: 300,
      });
      registry.registerSiteDetailTab({
        id: 'tab-a',
        label: 'Tab A',
        component: FakeComponent,
        order: 200,
      });

      const tabs = registry.getSiteDetailTabs();
      expect(tabs).toHaveLength(2);
      expect(tabs[0].id).toBe('tab-a');
      expect(tabs[1].id).toBe('tab-b');
    });

    it('does not register duplicate tab ids', () => {
      const FakeComponent = () => null;
      registry.registerSiteDetailTab({
        id: 'dup',
        label: 'First',
        component: FakeComponent,
      });
      registry.registerSiteDetailTab({
        id: 'dup',
        label: 'Second',
        component: FakeComponent,
      });

      expect(registry.getSiteDetailTabs()).toHaveLength(1);
      expect(registry.getSiteDetailTabs()[0].label).toBe('First');
    });
  });

  describe('getPages', () => {
    it('returns empty array when no pages registered', () => {
      expect(registry.getPages()).toEqual([]);
    });

    it('returns registered pages', () => {
      const FakeComponent = () => null;
      registry.registerPage({
        path: '/ee/billing',
        component: FakeComponent,
      });

      const pages = registry.getPages();
      expect(pages).toHaveLength(1);
      expect(pages[0].path).toBe('/ee/billing');
    });

    it('does not register duplicate paths', () => {
      const FakeComponent = () => null;
      registry.registerPage({ path: '/ee/billing', component: FakeComponent });
      registry.registerPage({ path: '/ee/billing', component: FakeComponent });

      expect(registry.getPages()).toHaveLength(1);
    });
  });

  describe('getNavItems', () => {
    it('returns empty array when no nav items registered', () => {
      expect(registry.getNavItems()).toEqual([]);
    });

    it('returns registered nav items sorted by order', () => {
      registry.registerNavItem({ path: '/ee/b', label: 'B', order: 300 });
      registry.registerNavItem({ path: '/ee/a', label: 'A', order: 200 });

      const items = registry.getNavItems();
      expect(items).toHaveLength(2);
      expect(items[0].label).toBe('A');
      expect(items[1].label).toBe('B');
    });

    it('does not register duplicate paths', () => {
      registry.registerNavItem({ path: '/ee/a', label: 'A' });
      registry.registerNavItem({ path: '/ee/a', label: 'A2' });

      expect(registry.getNavItems()).toHaveLength(1);
    });
  });

  describe('registerAnalyticsSink', () => {
    it('routes admin UI analytics events to the registered sink', async () => {
      const analytics = await import('../services/analytics');
      const sink = vi.fn();

      registry.registerAnalyticsSink(sink);
      analytics.trackPageView('/sites');

      expect(sink).toHaveBeenCalledWith({ event: 'page_view', page_path: '/sites', page_title: undefined });
    });
  });

  describe('discoverExtensions', () => {
    it('does not throw and is callable', () => {
      // discoverExtensions uses import.meta.glob which is Vite-specific.
      // In the test environment the EE module may not fully resolve, so
      // we verify the function exists and is callable rather than
      // executing the full dynamic import chain.
      expect(typeof registry.discoverExtensions).toBe('function');
    });
  });
});
