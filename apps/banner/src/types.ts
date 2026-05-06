/** Consent category slugs. */
export type CategorySlug =
  | 'necessary'
  | 'functional'
  | 'analytics'
  | 'marketing'
  | 'personalisation';

/** Consent state stored in the first-party cookie. */
export interface ConsentState {
  /** Unique visitor identifier. */
  visitorId: string;
  /** Categories the visitor has accepted. */
  accepted: CategorySlug[];
  /** Categories the visitor has rejected. */
  rejected: CategorySlug[];
  /** ISO 8601 timestamp of consent. */
  consentedAt: string;
  /** Version of the banner that collected consent. */
  bannerVersion: string;
  /** TC string if TCF is enabled. */
  tcString?: string;
  /** GPP string if GPP is enabled. */
  gppString?: string;
  /** Google Consent Mode state at time of consent. */
  gcmState?: Record<string, 'granted' | 'denied'>;
  /** Config version (site_config ID) at time of consent, used for re-consent detection. */
  configVersion?: string;
  /** Whether GPC signal was detected in the browser. */
  gpcDetected?: boolean;
  /** Whether GPC signal was honoured (auto-opt-out applied). */
  gpcHonoured?: boolean;
}

/** Server-side consent profile returned by the sync API. */
export interface ServerConsentProfile {
  id: string;
  org_id: string;
  consent_group_id: string | null;
  user_identifier: string;
  categories_consented: string[];
  categories_rejected: string[];
  tc_string: string | null;
  gpp_string: string | null;
  gcm_state: Record<string, 'granted' | 'denied'> | null;
  last_updated_at: string;
  last_site_id: string | null;
  created_at: string;
}

/** A/B test variant as delivered in site config. */
export interface ABTestVariant {
  id: string;
  name: string;
  traffic_percentage: number;
  banner_config_override: Partial<BannerConfig> | null;
  is_control: boolean;
}

/** Active A/B test data included in site config. */
export interface ABTestConfig {
  id: string;
  name: string;
  variants: ABTestVariant[];
}

/** Site configuration fetched from the API/CDN. */
export interface SiteConfig {
  id: string;
  site_id: string;
  blocking_mode: 'opt_in' | 'opt_out' | 'informational';
  regional_modes: Record<string, string> | null;
  tcf_enabled: boolean;
  gpp_enabled: boolean;
  gpp_supported_apis: string[];
  gpc_enabled: boolean;
  gpc_jurisdictions: string[];
  gpc_global_honour: boolean;
  gcm_enabled: boolean;
  gcm_default: Record<string, 'granted' | 'denied'> | null;
  shopify_privacy_enabled: boolean;
  banner_config: BannerConfig | null;
  privacy_policy_url: string | null;
  terms_url: string | null;
  consent_expiry_days: number;
  /** Consent group ID for cross-domain sync (null if not in a group). */
  consent_group_id: string | null;
  /** Active A/B test (null if none running). */
  ab_test: ABTestConfig | null;
  /** Initiator map: root script URL → category for root-level blocking. */
  initiator_map: InitiatorMapping[] | null;
  /**
   * Cookie categories the banner should render. Always contains
   * ``necessary``; operators subset the remaining four via the config
   * cascade (site → group → org → system default of all five). Older
   * API responses may omit this field — callers should fall back to
   * every known category in that case.
   */
  enabled_categories?: CategorySlug[];
  /**
   * IAB vendor IDs disclosed to users in the CMP UI (TCF v2.3
   * DisclosedVendors segment). Empty / missing → no disclosure.
   */
  disclosed_vendor_ids?: number[];
  /** Bridge origin for cross-domain consent (e.g. ``https://cmp.consentos.dev``). */
  consent_bridge_url?: string | null;
}

/** Maps a root initiator script to the cookie category it ultimately sets. */
export interface InitiatorMapping {
  /** Root script URL pattern (matched against script src). */
  root_script: string;
  /** Category of cookies set by this initiator chain. */
  category: CategorySlug;
}

/** Per-button styling configuration. */
export interface ButtonConfig {
  backgroundColour?: string;
  textColour?: string;
  borderColour?: string;
  style?: 'filled' | 'outline' | 'text';
}

/** Text content configuration for the banner. */
export interface BannerTextConfig {
  title?: string;
  description?: string;
  acceptAll?: string;
  rejectAll?: string;
  managePreferences?: string;
  savePreferences?: string;
}

/** Visual configuration for the banner. */
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

/** Google Consent Mode consent types. */
export type GcmConsentType =
  | 'ad_storage'
  | 'ad_user_data'
  | 'ad_personalization'
  | 'analytics_storage'
  | 'functionality_storage'
  | 'personalization_storage'
  | 'security_storage';
