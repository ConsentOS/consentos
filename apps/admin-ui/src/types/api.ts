/** API response types matching the backend Pydantic schemas. */

export interface Organisation {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  role: 'owner' | 'admin' | 'editor' | 'viewer';
  is_active: boolean;
  organisation_id: string;
  created_at: string;
  updated_at: string;
}

export interface Site {
  id: string;
  organisation_id: string;
  domain: string;
  name: string | null;
  display_name: string;
  is_active: boolean;
  site_group_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface SiteGroup {
  id: string;
  organisation_id: string;
  name: string;
  description: string | null;
  site_count: number;
  created_at: string;
  updated_at: string;
}

export interface SiteGroupConfig {
  id: string;
  site_group_id: string;
  blocking_mode: 'opt_in' | 'opt_out' | 'informational' | null;
  regional_modes: Record<string, string> | null;
  tcf_enabled: boolean | null;
  tcf_publisher_cc: string | null;
  gcm_enabled: boolean | null;
  gcm_default: Record<string, 'granted' | 'denied'> | null;
  shopify_privacy_enabled: boolean | null;
  gpp_enabled: boolean | null;
  gpp_supported_apis: string[] | null;
  gpc_enabled: boolean | null;
  gpc_jurisdictions: string[] | null;
  gpc_global_honour: boolean | null;
  banner_config: BannerConfig | null;
  privacy_policy_url: string | null;
  terms_url: string | null;
  scan_schedule_cron: string | null;
  scan_max_pages: number | null;
  consent_expiry_days: number | null;
  consent_sharing_enabled: boolean | null;
  consent_bridge_url: string | null;
  created_at: string;
  updated_at: string;
}

export type ConfigSource = 'system' | 'org' | 'group' | 'site';

export interface ConfigFieldInheritance {
  resolved_value: unknown;
  source: ConfigSource;
  site_value: unknown;
  group_value: unknown;
  org_value: unknown;
  system_value: unknown;
}

export interface ConfigInheritanceResponse {
  site_id: string;
  site_group_id: string | null;
  fields: Record<string, ConfigFieldInheritance>;
}

export interface OrgConfig {
  id: string;
  organisation_id: string;
  blocking_mode: 'opt_in' | 'opt_out' | 'informational' | null;
  regional_modes: Record<string, string> | null;
  tcf_enabled: boolean | null;
  tcf_publisher_cc: string | null;
  gpp_enabled: boolean | null;
  gpp_supported_apis: string[] | null;
  gpc_enabled: boolean | null;
  gpc_jurisdictions: string[] | null;
  gpc_global_honour: boolean | null;
  gcm_enabled: boolean | null;
  gcm_default: Record<string, 'granted' | 'denied'> | null;
  shopify_privacy_enabled: boolean | null;
  banner_config: BannerConfig | null;
  privacy_policy_url: string | null;
  terms_url: string | null;
  scan_schedule_cron: string | null;
  scan_max_pages: number | null;
  consent_expiry_days: number | null;
  created_at: string;
  updated_at: string;
}

export interface SiteConfig {
  id: string;
  site_id: string;
  blocking_mode: 'opt_in' | 'opt_out' | 'informational';
  regional_modes: Record<string, string> | null;
  tcf_enabled: boolean;
  gpp_enabled: boolean;
  gpp_supported_apis: string[] | null;
  gpc_enabled: boolean;
  gpc_jurisdictions: string[] | null;
  gpc_global_honour: boolean;
  gcm_enabled: boolean;
  gcm_default: Record<string, 'granted' | 'denied'> | null;
  shopify_privacy_enabled: boolean;
  banner_config: BannerConfig | null;
  privacy_policy_url: string | null;
  terms_url: string | null;
  consent_expiry_days: number;
  scan_enabled: boolean;
  scan_frequency_hours: number;
  scan_max_pages: number;
  scan_schedule_cron: string | null;
  /**
   * Cookie categories the banner should display. ``null`` means
   * "inherit from the cascade" (group → org → system default of all
   * five). An explicit list overrides; ``necessary`` is always
   * implicit and re-added by the resolver if missing.
   */
  enabled_categories: CategorySlug[] | null;
  created_at: string;
  updated_at: string;
}

export type CategorySlug =
  | 'necessary'
  | 'functional'
  | 'analytics'
  | 'marketing'
  | 'personalisation';

export const ALL_COOKIE_CATEGORIES: {
  slug: CategorySlug;
  label: string;
  description: string;
  locked: boolean;
}[] = [
  {
    slug: 'necessary',
    label: 'Necessary',
    description: 'Essential for the website to function. Always active and cannot be disabled.',
    locked: true,
  },
  {
    slug: 'functional',
    label: 'Functional',
    description: 'Remember preferences and enable enhanced features (e.g. language, chat widgets).',
    locked: false,
  },
  {
    slug: 'analytics',
    label: 'Analytics',
    description: 'Measure traffic and interaction so you can understand how visitors use the site.',
    locked: false,
  },
  {
    slug: 'marketing',
    label: 'Marketing',
    description: 'Advertising, remarketing, and cross-site tracking.',
    locked: false,
  },
  {
    slug: 'personalisation',
    label: 'Personalisation',
    description: 'Tailor content, recommendations, and the banner appearance to the visitor.',
    locked: false,
  },
];

export interface ButtonConfig {
  backgroundColour?: string;
  textColour?: string;
  borderColour?: string;
  style?: 'filled' | 'outline' | 'text';
}

export interface BannerTextConfig {
  title?: string;
  description?: string;
  acceptAll?: string;
  rejectAll?: string;
  managePreferences?: string;
  savePreferences?: string;
}

export interface BannerConfig {
  displayMode?: 'bottom_banner' | 'top_banner' | 'overlay' | 'corner_popup';
  cornerPosition?: 'left' | 'right';
  primaryColour?: string;
  backgroundColour?: string;
  textColour?: string;
  buttonStyle?: 'filled' | 'outline';
  fontFamily?: string;
  customFontUrl?: string;
  borderRadius?: number;
  showLogo?: boolean;
  logoUrl?: string;
  showRejectAll?: boolean;
  showManagePreferences?: boolean;
  showCloseButton?: boolean;
  showCookieCount?: boolean;
  acceptButton?: ButtonConfig;
  rejectButton?: ButtonConfig;
  manageButton?: ButtonConfig;
  text?: BannerTextConfig;
}

export interface Translation {
  id: string;
  site_id: string;
  locale: string;
  strings: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface CookieCategory {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  is_essential: boolean;
  display_order: number;
  tcf_purpose_ids: number[] | null;
  gcm_consent_types: string[] | null;
  created_at: string;
  updated_at: string;
}

export interface Cookie {
  id: string;
  site_id: string;
  category_id: string | null;
  name: string;
  domain: string;
  storage_type: string;
  description: string | null;
  vendor: string | null;
  review_status: 'pending' | 'approved' | 'rejected';
  created_at: string;
  updated_at: string;
}

export interface AllowListEntry {
  id: string;
  site_id: string;
  category_id: string;
  name_pattern: string;
  domain_pattern: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface ScanJob {
  id: string;
  site_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  trigger: 'manual' | 'scheduled' | 'client_report';
  pages_scanned: number;
  pages_total: number | null;
  cookies_found: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScanResult {
  id: string;
  scan_job_id: string;
  page_url: string;
  cookie_name: string;
  cookie_domain: string;
  storage_type: string;
  attributes: Record<string, unknown> | null;
  script_source: string | null;
  auto_category: string | null;
  initiator_chain: string[] | null;
  found_at: string;
  created_at: string;
}

export interface ScanJobDetail extends ScanJob {
  results: ScanResult[];
}

export interface CookieDiffItem {
  name: string;
  domain: string;
  storage_type: string;
  diff_status: 'new' | 'removed' | 'changed';
  details: string | null;
}

export interface ScanDiff {
  current_scan_id: string;
  previous_scan_id: string | null;
  new_cookies: CookieDiffItem[];
  removed_cookies: CookieDiffItem[];
  changed_cookies: CookieDiffItem[];
  total_new: number;
  total_removed: number;
  total_changed: number;
}

// ── Cross-domain consent sync ────────────────────────────────────────

export interface ConsentGroup {
  id: string;
  org_id: string;
  name: string;
  description: string | null;
  merge_strategy: 'server_wins' | 'latest_wins';
  created_at: string;
  updated_at: string;
}

export interface ConsentGroupSite {
  id: string;
  domain: string;
  display_name: string;
}

export interface PublicKey {
  id: string;
  org_id: string;
  name: string;
  algorithm: 'RS256' | 'ES256';
  is_active: boolean;
  created_at: string;
}

// ── Compliance ──────────────────────────────────────────────────────

export type ComplianceFramework = 'gdpr' | 'cnil' | 'ccpa' | 'eprivacy' | 'lgpd';
export type ComplianceSeverity = 'critical' | 'warning' | 'info';
export type ComplianceStatus = 'compliant' | 'partial' | 'non_compliant';

export interface ComplianceIssue {
  rule_id: string;
  severity: ComplianceSeverity;
  message: string;
  recommendation: string;
}

export interface FrameworkResult {
  framework: ComplianceFramework;
  score: number;
  status: ComplianceStatus;
  issues: ComplianceIssue[];
  rules_checked: number;
  rules_passed: number;
}

export interface ComplianceCheckResponse {
  site_id: string;
  results: FrameworkResult[];
  overall_score: number;
}

// ── Analytics ───────────────────────────────────────────────────────

export interface ActionBreakdown {
  accept_all: number;
  reject_all: number;
  custom: number;
  withdraw: number;
}

export interface CategoryRate {
  category: string;
  accepted: number;
  rejected: number;
  rate: number;
}

export interface ConsentRatesResponse {
  site_id: string;
  total_records: number;
  consent_rate: number;
  action_breakdown: ActionBreakdown;
  category_rates: CategoryRate[];
  from_date: string;
  to_date: string;
}

export interface TrendPoint {
  period: string;
  total: number;
  accept_all: number;
  reject_all: number;
  custom: number;
  consent_rate: number;
}

export interface ConsentTrendsResponse {
  site_id: string;
  granularity: 'day' | 'week' | 'month';
  data: TrendPoint[];
  from_date: string;
  to_date: string;
}

export interface RegionMetric {
  country_code: string;
  region_code: string | null;
  total: number;
  accept_all: number;
  reject_all: number;
  custom: number;
  consent_rate: number;
}

export interface RegionalBreakdownResponse {
  site_id: string;
  regions: RegionMetric[];
  from_date: string;
  to_date: string;
}

export interface AnalyticsSummaryResponse {
  site_id: string;
  total_records: number;
  consent_rate: number;
  accept_all_rate: number;
  reject_all_rate: number;
  custom_rate: number;
  top_countries: RegionMetric[];
  from_date: string;
  to_date: string;
}

// ── A/B Testing ─────────────────────────────────────────────────────

export type ABTestStatus = 'draft' | 'running' | 'paused' | 'completed';

export interface ABTestVariant {
  id: string;
  ab_test_id: string;
  name: string;
  traffic_percentage: number;
  banner_config_override: Partial<BannerConfig> | null;
  is_control: boolean;
  created_at: string;
  updated_at: string;
}

export interface ABTest {
  id: string;
  site_id: string;
  created_by: string | null;
  name: string;
  description: string | null;
  status: ABTestStatus;
  start_date: string | null;
  end_date: string | null;
  variants: ABTestVariant[];
  created_at: string;
  updated_at: string;
}

export interface ABTestVariantCreate {
  name: string;
  traffic_percentage: number;
  banner_config_override?: Partial<BannerConfig> | null;
  is_control: boolean;
}

export interface ABTestCreate {
  name: string;
  description?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  variants: ABTestVariantCreate[];
}

// ── Preference Centre ──────────────────────────────────────────────

export type PreferenceCategory = 'cookie_consent' | 'communication' | 'data_sharing';

export interface PreferenceType {
  id: string;
  site_id: string;
  name: string;
  slug: string;
  description: string | null;
  category: PreferenceCategory;
  is_active: boolean;
  display_order: number;
  created_at: string;
  updated_at: string;
}

export interface PreferenceTypeCreate {
  name: string;
  slug: string;
  description?: string | null;
  category: PreferenceCategory;
  is_active?: boolean;
  display_order?: number;
}

export interface PreferenceTypeUpdate {
  name?: string;
  description?: string | null;
  category?: PreferenceCategory;
  is_active?: boolean;
  display_order?: number;
}

export interface UserPreferenceRecord {
  id: string;
  site_id: string;
  user_identifier_hash: string;
  preference_type_id: string;
  value: 'granted' | 'denied';
  source: 'banner' | 'preference_centre' | 'api';
  created_at: string;
  updated_at: string;
}

export interface PreferenceCentreConfig {
  site_id: string;
  site_name: string;
  preference_types: PreferenceType[];
  current_preferences: UserPreferenceRecord[];
}

export interface PreferenceHistoryEntry {
  preference_type_name: string;
  preference_type_slug: string;
  value: string;
  source: string;
  created_at: string;
}

export interface PreferenceHistoryResponse {
  site_id: string;
  user_identifier_hash: string;
  entries: PreferenceHistoryEntry[];
}

// ── Policy Documents ──────────────────────────────────────────────

export interface PolicyDocument {
  id: string;
  site_id: string;
  type: 'cookie_policy' | 'privacy_section';
  content_html: string | null;
  content_markdown: string | null;
  template_overrides: PolicyTemplateOverrides | null;
  generated_at: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PolicyTemplateOverrides {
  introduction_text?: string | null;
  additional_sections?: { title: string; content: string }[] | null;
  language?: string | null;
}

// ── Compliance Scores (server-side monitoring) ─────────────────────

export interface ComplianceScoreRecord {
  id: string;
  site_id: string;
  framework: string;
  score: number;
  status: ComplianceStatus;
  critical_count: number;
  warning_count: number;
  info_count: number;
  issues: unknown;
  scanned_at: string;
  created_at: string;
}

export interface ComplianceScoreSummary {
  site_id: string;
  overall_score: number;
  frameworks: ComplianceScoreRecord[];
}

export interface ComplianceScoreTrendPoint {
  framework: string;
  score: number;
  scanned_at: string;
}

export interface ComplianceScoreTrendResponse {
  site_id: string;
  framework: string | null;
  data_points: ComplianceScoreTrendPoint[];
}

export interface ValidationIssueResponse {
  check: string;
  severity: string;
  message: string;
  recommendation: string;
  details: Record<string, unknown>;
}

export interface ValidationResultResponse {
  url: string;
  pre_consent_issues: ValidationIssueResponse[];
  post_accept_issues: ValidationIssueResponse[];
  post_reject_issues: ValidationIssueResponse[];
  dark_pattern_issues: ValidationIssueResponse[];
  banner_found: boolean;
  errors: string[];
}

export interface ABTestComplianceResult {
  variant_id: string;
  variant_name: string;
  compliant: boolean;
  issues: {
    framework: string;
    severity: string;
    rule_id: string;
    message: string;
    recommendation: string;
  }[];
}

// ── DSAR & Retention ────────────────────────────────────────────────

export type DsarIdentifierType = 'email' | 'consent_id' | 'visitor_id';
export type DsarRequestType = 'access' | 'deletion';
export type DsarStatus = 'pending' | 'processing' | 'completed' | 'rejected';

export interface DsarRequestResponse {
  id: string;
  org_id: string;
  site_id: string | null;
  requester_identifier: string;
  requester_identifier_type: DsarIdentifierType;
  request_type: DsarRequestType;
  status: DsarStatus;
  submitted_at: string;
  processed_at: string | null;
  processed_by: string | null;
  notes: string | null;
  result_data: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface RetentionAuditLogResponse {
  id: string;
  site_id: string;
  records_anonymised: number;
  records_deleted: number;
  retention_days: number;
  purge_date: string;
  created_at: string;
  updated_at: string;
}

// ── Consent Receipts ────────────────────────────────────────────────

export interface ConsentReceiptResponse {
  id: string;
  consent_record_id: string;
  site_id: string;
  receipt_data: {
    receipt_id: string;
    version: string;
    timestamp: string;
    jurisdiction: { country_code: string | null; region_code: string | null };
    site: { id: string; domain: string | null; name: string | null };
    page_url: string | null;
    banner_version_hash: string;
    banner_content: {
      banner_config: Record<string, unknown> | null;
      translation_strings: Record<string, string> | null;
    };
    consent: {
      action: string;
      categories_accepted: string[];
      categories_rejected: string[];
    };
    signals: {
      tc_string: string | null;
      gpp_string: string | null;
      gcm_state: Record<string, string> | null;
      gpc_detected: boolean | null;
      gpc_honoured: boolean | null;
    };
    visitor: {
      visitor_id: string;
      ip_hash: string | null;
      user_agent_hash: string | null;
    };
  };
  banner_version_hash: string | null;
  created_at: string;
}

export interface ConsentRecord {
  id: string;
  site_id: string;
  visitor_id: string;
  action: string;
  categories_accepted: string[];
  categories_rejected: string[] | null;
  tc_string: string | null;
  gcm_state: Record<string, string> | null;
  gpp_string: string | null;
  gpc_detected: boolean | null;
  gpc_honoured: boolean | null;
  page_url: string | null;
  country_code: string | null;
  region_code: string | null;
  consented_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
