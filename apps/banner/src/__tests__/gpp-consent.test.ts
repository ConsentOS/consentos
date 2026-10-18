import { describe, expect, it } from 'vitest';

import { GppFieldValue, US_CALIFORNIA, US_NATIONAL, decodeGppString, encodeGppString } from '../gpp';
import { buildGppFromConsent } from '../gpp-consent';

const { YES, NO, NOT_APPLICABLE } = GppFieldValue;

function usnat(accepted: Parameters<typeof buildGppFromConsent>[0], gpc = false) {
  const gpp = buildGppFromConsent(accepted, ['usnat'], gpc);
  return gpp.sections.get(US_NATIONAL.id)!;
}

describe('buildGppFromConsent', () => {
  it('records no opt-out when marketing is accepted', () => {
    const { data } = usnat(['necessary', 'analytics', 'marketing']);
    expect(data.SaleOptOut).toBe(NO);
    expect(data.SharingOptOut).toBe(NO);
    expect(data.TargetedAdvertisingOptOut).toBe(NO);
  });

  it('records an opt-out when marketing is not accepted', () => {
    const { data } = usnat(['necessary', 'analytics']);
    expect(data.SaleOptOut).toBe(YES);
    expect(data.SharingOptOut).toBe(YES);
    expect(data.TargetedAdvertisingOptOut).toBe(YES);
  });

  it('marks every notice field as provided', () => {
    const { data } = usnat(['necessary']);
    for (const field of US_NATIONAL.coreFields.filter((f) => f.name.endsWith('Notice'))) {
      expect(data[field.name]).toBe(YES);
    }
  });

  it('leaves fields the category model cannot answer as not applicable', () => {
    const { data } = usnat(['necessary', 'marketing']);
    expect(data.PersonalDataConsents).toBe(NOT_APPLICABLE);
    expect(data.MspaCoveredTransaction).toBe(NOT_APPLICABLE);
    expect(data.SensitiveDataProcessing).toEqual(new Array(12).fill(NOT_APPLICABLE));
  });

  it('records the GPC signal in the sub-section', () => {
    expect(usnat(['necessary'], true).gpcSubsection).toEqual({ gpc: true });
    expect(usnat(['necessary'], false).gpcSubsection).toEqual({ gpc: false });
  });

  it('encodes each supported section, in id order, and skips unknown prefixes', () => {
    const gpp = buildGppFromConsent(['necessary'], ['usca', 'nope', 'usnat', 'usnat'], false);
    expect(gpp.header.sectionIds).toEqual([US_NATIONAL.id, US_CALIFORNIA.id]);
    expect(gpp.header.applicableSections).toEqual([US_NATIONAL.id, US_CALIFORNIA.id]);
  });

  it('defaults to the US national section when the site lists none', () => {
    const gpp = buildGppFromConsent(['necessary'], [], false);
    expect(gpp.header.sectionIds).toEqual([US_NATIONAL.id]);
  });

  it('round-trips through the GPP string encoder', () => {
    const gpp = buildGppFromConsent(['necessary'], ['usnat', 'usca'], true);
    const decoded = decodeGppString(encodeGppString(gpp));
    expect(decoded.header.sectionIds).toEqual(gpp.header.sectionIds);
    expect(decoded.sections.get(US_NATIONAL.id)!.data.SaleOptOut).toBe(YES);
    expect(decoded.sections.get(US_CALIFORNIA.id)!.data.SaleOptOut).toBe(YES);
  });
});
