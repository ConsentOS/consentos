import { beforeEach, describe, expect, it, vi } from 'vitest';

type AnalyticsModule = typeof import('../services/analytics');

describe('analytics service', () => {
  let analytics: AnalyticsModule;
  let received: Record<string, unknown>[];

  beforeEach(async () => {
    // The sink list and buffer are module-level state, so each test
    // gets a fresh copy of the module.
    vi.resetModules();
    analytics = await import('../services/analytics');
    received = [];
  });

  function registerCollector(): void {
    analytics.registerAnalyticsSink((event) => received.push(event));
  }

  it('creates no GTM dataLayer when no sink is registered', () => {
    analytics.trackPageView('/sites');

    expect('dataLayer' in window).toBe(false);
  });

  it('identifies the user by ID without personal data', () => {
    registerCollector();

    analytics.initAnalytics({
      id: 'u1',
      email: 'test@example.com',
      role: 'admin',
      organisation_id: 'org1',
      full_name: 'Test User',
    } as Parameters<AnalyticsModule['initAnalytics']>[0]);

    expect(received).toEqual([
      { event: 'user_identified', user_id: 'u1', user_role: 'admin', org_id: 'org1' },
    ]);
  });

  it('delivers page_view events', () => {
    registerCollector();

    analytics.trackPageView('/sites', 'Sites');

    expect(received).toEqual([{ event: 'page_view', page_path: '/sites', page_title: 'Sites' }]);
  });

  it('delivers auth_event events', () => {
    registerCollector();

    analytics.trackAuthEvent('login', 'u1');

    expect(received).toEqual([{ event: 'auth_event', auth_action: 'login', user_id: 'u1' }]);
  });

  it('delivers config_change events', () => {
    registerCollector();

    analytics.trackConfigChange('site_config', { site_id: 's1' });

    expect(received).toEqual([
      { event: 'config_change', change_type: 'site_config', site_id: 's1' },
    ]);
  });

  it('delivers feature_usage events', () => {
    registerCollector();

    analytics.trackFeatureUsage('scan', 'trigger', { site_id: 's1' });

    expect(received).toEqual([
      { event: 'feature_usage', feature: 'scan', feature_action: 'trigger', site_id: 's1' },
    ]);
  });

  it('replays events emitted before the first sink registers', () => {
    analytics.trackPageView('/login');
    analytics.trackAuthEvent('login', 'u1');

    registerCollector();

    expect(received.map((e) => e.event)).toEqual(['page_view', 'auth_event']);
  });

  it('caps the pre-registration buffer and keeps the newest events', () => {
    for (let i = 0; i < 60; i++) analytics.trackPageView(`/page/${i}`);

    registerCollector();

    expect(received).toHaveLength(50);
    expect(received[0]).toMatchObject({ page_path: '/page/10' });
    expect(received[49]).toMatchObject({ page_path: '/page/59' });
  });

  it('delivers to every registered sink', () => {
    const second: Record<string, unknown>[] = [];
    registerCollector();
    analytics.registerAnalyticsSink((event) => second.push(event));

    analytics.trackPageView('/sites');

    expect(received).toHaveLength(1);
    expect(second).toHaveLength(1);
  });

  it('ignores a sink registered twice', () => {
    const sink = vi.fn();
    analytics.registerAnalyticsSink(sink);
    analytics.registerAnalyticsSink(sink);

    analytics.trackPageView('/sites');

    expect(sink).toHaveBeenCalledTimes(1);
  });

  it('keeps delivering when one sink throws', () => {
    analytics.registerAnalyticsSink(() => {
      throw new Error('destination down');
    });
    registerCollector();

    expect(() => analytics.trackPageView('/sites')).not.toThrow();
    expect(received).toHaveLength(1);
  });
});
