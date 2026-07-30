import type { ConsentRatesResponse, ConsentTrendsResponse } from '../types/api';
import apiClient from './client';

/** Accept / partial / decline breakdown and per-category rates for a site. */
export async function getConsentRates(
  siteId: string,
  params?: { days?: number },
): Promise<ConsentRatesResponse> {
  const { data } = await apiClient.get<ConsentRatesResponse>(
    `/sites/${siteId}/consent-rates`,
    { params },
  );
  return data;
}

/** Consent decisions bucketed over time for charting. */
export async function getConsentTrends(
  siteId: string,
  params?: { days?: number; granularity?: 'day' | 'week' | 'month' },
): Promise<ConsentTrendsResponse> {
  const { data } = await apiClient.get<ConsentTrendsResponse>(
    `/sites/${siteId}/consent-trends`,
    { params },
  );
  return data;
}
