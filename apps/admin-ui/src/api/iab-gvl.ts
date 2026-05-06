import apiClient from './client';

/** Singleton metadata for the currently-cached IAB Global Vendor List. */
export interface GvlMeta {
  gvl_specification_version: number;
  vendor_list_version: number;
  tcf_policy_version: number;
  last_updated: string;
  synced_at: string;
}

/** A single IAB-registered vendor as cached locally from the GVL. */
export interface IabVendor {
  id: number;
  name: string;
  purposes: number[] | null;
  leg_int_purposes: number[] | null;
  flexible_purposes: number[] | null;
  special_purposes: number[] | null;
  features: number[] | null;
  special_features: number[] | null;
  policy_url: string | null;
  deleted_date: string | null;
  uses_cookies: boolean | null;
  cookie_refresh: boolean | null;
  uses_non_cookie_access: boolean | null;
  cookie_max_age_seconds: number | null;
}

export interface IabVendorListResponse {
  items: IabVendor[];
  total: number;
  limit: number;
  offset: number;
}

export interface ListVendorsParams {
  q?: string;
  include_deleted?: boolean;
  limit?: number;
  offset?: number;
}

export async function getGvlMeta(): Promise<GvlMeta | null> {
  try {
    const { data } = await apiClient.get<GvlMeta>('/iab/gvl-meta');
    return data;
  } catch (err) {
    // 404 means the GVL hasn't been synced yet — surface as null so
    // the UI can render a "not synced" state instead of an error.
    const status = (err as { response?: { status?: number } }).response?.status;
    if (status === 404) return null;
    throw err;
  }
}

export async function listVendors(params: ListVendorsParams = {}): Promise<IabVendorListResponse> {
  const { data } = await apiClient.get<IabVendorListResponse>('/iab/vendors', { params });
  return data;
}

export async function getVendor(id: number): Promise<IabVendor> {
  const { data } = await apiClient.get<IabVendor>(`/iab/vendors/${id}`);
  return data;
}
