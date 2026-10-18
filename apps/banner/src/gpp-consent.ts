/**
 * Build GPP section data from a visitor's category choices.
 *
 * Mapping, per US section the site lists in ``gpp_supported_apis``:
 *
 * - Every ``*Notice`` field is YES: the banner itself is the notice.
 * - ``SaleOptOut``, ``SharingOptOut`` and ``TargetedAdvertisingOptOut`` are
 *   NO (did not opt out) only when the marketing category is accepted,
 *   otherwise YES (opted out). A honoured GPC signal never reaches here
 *   with marketing accepted, so it is covered by the same rule.
 * - Sensitive data, known-child, personal-data and MSPA fields stay
 *   NOT_APPLICABLE: the category model carries no signal for them.
 */

import {
  GppFieldValue,
  createDefaultSectionData,
  getSectionByPrefix,
  type GppString,
  type SectionData,
} from './gpp';
import type { CategorySlug } from './types';

const OPT_OUT_FIELDS = ['SaleOptOut', 'SharingOptOut', 'TargetedAdvertisingOptOut'];

/** Sections encoded when the site lists none. */
const DEFAULT_APIS = ['usnat'];

function sectionData(
  fieldNames: string[],
  base: SectionData,
  marketingAccepted: boolean,
): SectionData {
  const data = { ...base };
  for (const name of fieldNames) {
    if (name.endsWith('Notice')) {
      data[name] = GppFieldValue.YES;
    } else if (OPT_OUT_FIELDS.includes(name)) {
      data[name] = marketingAccepted ? GppFieldValue.NO : GppFieldValue.YES;
    }
  }
  return data;
}

/**
 * Build a GPP string for the given choices.
 *
 * @param accepted Categories the visitor accepted.
 * @param supportedApis Section prefixes the site supports, e.g. ``['usnat', 'usca']``.
 *   Unknown prefixes are skipped.
 * @param gpcDetected Whether the browser sent a GPC signal, recorded in each
 *   section's GPC sub-section where the section has one.
 */
export function buildGppFromConsent(
  accepted: CategorySlug[],
  supportedApis: string[],
  gpcDetected: boolean,
): GppString {
  const marketingAccepted = accepted.includes('marketing');
  const sections: GppString['sections'] = new Map();

  for (const prefix of supportedApis.length > 0 ? supportedApis : DEFAULT_APIS) {
    const def = getSectionByPrefix(prefix);
    if (!def || sections.has(def.id)) continue;
    const data = sectionData(
      def.coreFields.map((f) => f.name),
      createDefaultSectionData(def),
      marketingAccepted,
    );
    sections.set(def.id, {
      data,
      gpcSubsection: def.hasGpcSubsection ? { gpc: gpcDetected } : undefined,
    });
  }

  const sectionIds = [...sections.keys()].sort((a, b) => a - b);
  return {
    header: { version: 1, sectionIds, applicableSections: sectionIds },
    sections,
  };
}
