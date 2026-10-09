/**
 * Admin UI product analytics.
 *
 * Core emits events but ships no destination for them: with no sink
 * registered, nothing leaves the browser. A deployment that wants
 * analytics registers a sink through the extension registry.
 */

/** A single analytics event: a name plus flat properties. */
export interface AnalyticsEvent {
  event: string;
  [key: string]: unknown;
}

/** Receives every analytics event the admin UI emits. */
export type AnalyticsSink = (event: AnalyticsEvent) => void;

const MAX_BUFFERED_EVENTS = 50;

const _sinks: AnalyticsSink[] = [];
const _buffered: AnalyticsEvent[] = [];

/**
 * Register a destination for analytics events.
 *
 * Events emitted before the first sink registers are replayed to it,
 * because the initial page view fires before extension discovery
 * settles.
 */
export function registerAnalyticsSink(sink: AnalyticsSink): void {
  if (_sinks.includes(sink)) return;
  _sinks.push(sink);
  for (const event of _buffered.splice(0)) {
    deliver(sink, event);
  }
}

function deliver(sink: AnalyticsSink, event: AnalyticsEvent): void {
  try {
    sink(event);
  } catch (error) {
    // A failing analytics destination must never break the admin UI.
    console.warn('[ConsentOS] Analytics sink failed', error);
  }
}

function emit(event: string, data?: Record<string, unknown>): void {
  const payload: AnalyticsEvent = { event, ...data };
  if (_sinks.length === 0) {
    if (_buffered.length >= MAX_BUFFERED_EVENTS) _buffered.shift();
    _buffered.push(payload);
    return;
  }
  for (const sink of _sinks) {
    deliver(sink, payload);
  }
}

/** Identify the signed-in user. Called once after auth. Carries IDs only, no personal data. */
export function initAnalytics(user: {
  id: string;
  role: string;
  organisation_id: string;
}): void {
  emit('user_identified', {
    user_id: user.id,
    user_role: user.role,
    org_id: user.organisation_id,
  });
}

/** Track a page view. */
export function trackPageView(path: string, title?: string): void {
  emit('page_view', { page_path: path, page_title: title });
}

/** Track auth events (login, logout). */
export function trackAuthEvent(
  action: 'login' | 'logout',
  userId?: string,
): void {
  emit('auth_event', { auth_action: action, user_id: userId });
}

/** Track config changes (site config saved, org config updated, etc.). */
export function trackConfigChange(
  changeType: string,
  details?: Record<string, unknown>,
): void {
  emit('config_change', { change_type: changeType, ...details });
}

/** Track feature usage (banner preview, compliance check, scan triggered, etc.). */
export function trackFeatureUsage(
  feature: string,
  action: string,
  details?: Record<string, unknown>,
): void {
  emit('feature_usage', { feature, feature_action: action, ...details });
}
