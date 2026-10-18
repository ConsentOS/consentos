/**
 * IAB Global Privacy Platform (GPP) string encoder/decoder.
 *
 * Implements GPP v1 specification for:
 * - GPP header encoding/decoding with Fibonacci-coded section ID ranges
 * - US National Privacy section (Section 7)
 * - US state-specific sections: CA (8), VA (9), CO (10), CT (11), FL (14)
 *
 * Adding a new state section requires only adding a new SectionDef object to
 * the SECTION_REGISTRY — no structural changes needed.
 *
 * @see https://github.com/InteractiveAdvertisingBureau/Global-Privacy-Platform
 */

import { BitWriter, BitReader, bytesToBase64url, base64urlToBytes } from './tcf';

// ── GPP consent field values ─────────────────────────────────────────

/** Standard 2-bit consent/notice field values used across all US sections. */
export const GppFieldValue = {
  /** Field is not applicable in this context. */
  NOT_APPLICABLE: 0,
  /** Notice was provided / user opted out. */
  YES: 1,
  /** Notice was not provided / user did not opt out. */
  NO: 2,
} as const;

// ── Fibonacci coding ─────────────────────────────────────────────────

/**
 * Pre-computed Fibonacci numbers for Zeckendorf representation.
 * F(2)=1, F(3)=2, F(4)=3, F(5)=5, ... — sufficient for any GPP section ID.
 */
const FIB: number[] = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597];

/**
 * Write a positive integer using Fibonacci coding (Zeckendorf + terminator).
 *
 * Bits are written LSB-first (position 0 = F(2)=1), with a trailing '1' bit
 * to mark the end of the code word (two consecutive 1s terminate).
 */
export function fibonacciEncode(writer: BitWriter, value: number): void {
  if (value < 1) {
    throw new Error('Fibonacci coding requires a positive integer (>= 1)');
  }

  // Find the highest Fibonacci index needed
  let maxIdx = 0;
  for (let i = FIB.length - 1; i >= 0; i--) {
    if (FIB[i] <= value) {
      maxIdx = i;
      break;
    }
  }

  // Build Zeckendorf representation
  const bits = new Array<boolean>(maxIdx + 1).fill(false);
  let remaining = value;

  for (let i = maxIdx; i >= 0; i--) {
    if (FIB[i] <= remaining) {
      bits[i] = true;
      remaining -= FIB[i];
    }
  }

  // Write bits from position 0 upward, then the terminator '1'
  for (const bit of bits) {
    writer.writeBool(bit);
  }
  writer.writeBool(true); // terminator — creates the '11' pattern
}

/**
 * Read a Fibonacci-coded integer.
 * Reads bits until two consecutive 1-bits are encountered.
 */
export function fibonacciDecode(reader: BitReader): number {
  let value = 0;
  let prevBit = false;
  let position = 0;

  while (true) {
    const bit = reader.readBool();
    if (bit && prevBit) {
      break; // Two consecutive 1s — terminator reached
    }
    if (bit) {
      if (position >= FIB.length) {
        throw new Error('Fibonacci decode: value exceeds supported range');
      }
      value += FIB[position];
    }
    prevBit = bit;
    position++;
  }

  return value;
}

// ── GPP Header ───────────────────────────────────────────────────────

/** GPP header type identifier (always 3). */
const GPP_HEADER_TYPE = 3;

/** Current GPP specification version. */
const GPP_VERSION = 1;

/** Decoded GPP header. */
export interface GppHeader {
  /** GPP spec version (currently 1). */
  version: number;
  /** Section IDs present in this GPP string, in order. */
  sectionIds: number[];
  /** Section IDs applicable to the current transaction. */
  applicableSections: number[];
}

/** Encode a GPP header to a base64url string segment. */
export function encodeGppHeader(header: GppHeader): string {
  const writer = new BitWriter();

  writer.writeInt(GPP_HEADER_TYPE, 6);
  writer.writeInt(header.version, 6);

  // Section IDs — range-encoded with Fibonacci
  writeIdRange(writer, header.sectionIds);

  // Applicable sections — range-encoded with Fibonacci
  writeIdRange(writer, header.applicableSections);

  return bytesToBase64url(writer.toBytes());
}

/** Decode a GPP header from a base64url string segment. */
export function decodeGppHeader(encoded: string): GppHeader {
  const bytes = base64urlToBytes(encoded);
  const reader = new BitReader(bytes);

  const type = reader.readInt(6);
  if (type !== GPP_HEADER_TYPE) {
    throw new Error(`Invalid GPP header type: ${type} (expected ${GPP_HEADER_TYPE})`);
  }

  const version = reader.readInt(6);
  const sectionIds = readIdRange(reader);
  const applicableSections = readIdRange(reader);

  return { version, sectionIds, applicableSections };
}

/**
 * Write a list of IDs using range encoding with Fibonacci integers.
 *
 * Format:
 *   NumEntries: Int(6) — number of range entries
 *   For each entry:
 *     IsGroup: Bool — false = single ID, true = contiguous range
 *     If single: Id as Fibonacci integer
 *     If group:  StartId + EndId as Fibonacci integers
 */
function writeIdRange(writer: BitWriter, ids: number[]): void {
  if (ids.length === 0) {
    writer.writeInt(0, 6);
    return;
  }

  // Collapse consecutive IDs into ranges
  const sorted = [...ids].sort((a, b) => a - b);
  const ranges: [number, number][] = [];
  let start = sorted[0];
  let end = sorted[0];

  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i] === end + 1) {
      end = sorted[i];
    } else {
      ranges.push([start, end]);
      start = sorted[i];
      end = sorted[i];
    }
  }
  ranges.push([start, end]);

  writer.writeInt(ranges.length, 6);
  for (const [s, e] of ranges) {
    if (s === e) {
      writer.writeBool(false); // single
      fibonacciEncode(writer, s);
    } else {
      writer.writeBool(true); // group/range
      fibonacciEncode(writer, s);
      fibonacciEncode(writer, e);
    }
  }
}

/** Read a range-encoded list of IDs with Fibonacci integers. */
function readIdRange(reader: BitReader): number[] {
  const numEntries = reader.readInt(6);
  const ids: number[] = [];

  for (let i = 0; i < numEntries; i++) {
    const isGroup = reader.readBool();
    if (isGroup) {
      const start = fibonacciDecode(reader);
      const end = fibonacciDecode(reader);
      for (let id = start; id <= end; id++) {
        ids.push(id);
      }
    } else {
      ids.push(fibonacciDecode(reader));
    }
  }

  return ids;
}

// ── Section field definitions ────────────────────────────────────────

/** A single field in a GPP section definition. */
export interface FieldDef {
  /** Field name (e.g. 'SaleOptOut'). */
  name: string;
  /** Bit width per value. */
  bits: number;
  /** Number of values — 1 for scalars, >1 for arrays (e.g. SensitiveDataProcessing). */
  count: number;
}

/** A complete GPP section definition. */
export interface SectionDef {
  /** IAB GPP section ID. */
  id: number;
  /** API prefix used in __gpp() calls (e.g. 'usnat', 'usca'). */
  apiPrefix: string;
  /** Section format version. */
  version: number;
  /** Ordered list of field definitions for the core segment. */
  coreFields: FieldDef[];
  /** Whether this section supports an optional GPC sub-section. */
  hasGpcSubsection: boolean;
}

/** Section data — all field values as numbers (scalars) or number arrays. */
export type SectionData = Record<string, number | number[]>;

// ── Field definition helpers ─────────────────────────────────────────

function field(name: string, bits: number): FieldDef {
  return { name, bits, count: 1 };
}

function arrayField(name: string, bits: number, count: number): FieldDef {
  return { name, bits, count };
}

// ── US section definitions ───────────────────────────────────────────

/** US National Privacy section (Section 7, usnat v1). */
export const US_NATIONAL: SectionDef = {
  id: 7,
  apiPrefix: 'usnat',
  version: 1,
  coreFields: [
    field('Version', 6),
    field('SharingNotice', 2),
    field('SaleOptOutNotice', 2),
    field('SharingOptOutNotice', 2),
    field('TargetedAdvertisingOptOutNotice', 2),
    field('SensitiveDataProcessingOptOutNotice', 2),
    field('SensitiveDataLimitUseNotice', 2),
    field('SaleOptOut', 2),
    field('SharingOptOut', 2),
    field('TargetedAdvertisingOptOut', 2),
    arrayField('SensitiveDataProcessing', 2, 12),
    arrayField('KnownChildSensitiveDataConsents', 2, 2),
    field('PersonalDataConsents', 2),
    field('MspaCoveredTransaction', 2),
    field('MspaOptOutOptionMode', 2),
    field('MspaServiceProviderMode', 2),
  ],
  hasGpcSubsection: true,
};

/** US California Privacy section (Section 8, usca v1). */
export const US_CALIFORNIA: SectionDef = {
  id: 8,
  apiPrefix: 'usca',
  version: 1,
  coreFields: [
    field('Version', 6),
    field('SaleOptOutNotice', 2),
    field('SharingOptOutNotice', 2),
    field('SensitiveDataLimitUseNotice', 2),
    field('SaleOptOut', 2),
    field('SharingOptOut', 2),
    arrayField('SensitiveDataProcessing', 2, 9),
    arrayField('KnownChildSensitiveDataConsents', 2, 2),
    field('PersonalDataConsents', 2),
    field('MspaCoveredTransaction', 2),
    field('MspaOptOutOptionMode', 2),
    field('MspaServiceProviderMode', 2),
  ],
  hasGpcSubsection: true,
};

/** US Virginia Privacy section (Section 9, usva v1). */
export const US_VIRGINIA: SectionDef = {
  id: 9,
  apiPrefix: 'usva',
  version: 1,
  coreFields: [
    field('Version', 6),
    field('SharingNotice', 2),
    field('SaleOptOutNotice', 2),
    field('TargetedAdvertisingOptOutNotice', 2),
    field('SaleOptOut', 2),
    field('TargetedAdvertisingOptOut', 2),
    arrayField('SensitiveDataProcessing', 2, 8),
    field('KnownChildSensitiveDataConsents', 2),
    field('MspaCoveredTransaction', 2),
    field('MspaOptOutOptionMode', 2),
    field('MspaServiceProviderMode', 2),
  ],
  hasGpcSubsection: false,
};

/** US Colorado Privacy section (Section 10, usco v1). */
export const US_COLORADO: SectionDef = {
  id: 10,
  apiPrefix: 'usco',
  version: 1,
  coreFields: [
    field('Version', 6),
    field('SharingNotice', 2),
    field('SaleOptOutNotice', 2),
    field('TargetedAdvertisingOptOutNotice', 2),
    field('SaleOptOut', 2),
    field('TargetedAdvertisingOptOut', 2),
    arrayField('SensitiveDataProcessing', 2, 7),
    field('KnownChildSensitiveDataConsents', 2),
    field('MspaCoveredTransaction', 2),
    field('MspaOptOutOptionMode', 2),
    field('MspaServiceProviderMode', 2),
  ],
  hasGpcSubsection: true,
};

/** US Connecticut Privacy section (Section 11, usct v1). */
export const US_CONNECTICUT: SectionDef = {
  id: 11,
  apiPrefix: 'usct',
  version: 1,
  coreFields: [
    field('Version', 6),
    field('SharingNotice', 2),
    field('SaleOptOutNotice', 2),
    field('TargetedAdvertisingOptOutNotice', 2),
    field('SaleOptOut', 2),
    field('TargetedAdvertisingOptOut', 2),
    arrayField('SensitiveDataProcessing', 2, 8),
    arrayField('KnownChildSensitiveDataConsents', 2, 3),
    field('MspaCoveredTransaction', 2),
    field('MspaOptOutOptionMode', 2),
    field('MspaServiceProviderMode', 2),
  ],
  hasGpcSubsection: true,
};

/** US Florida Privacy section (Section 14, usfl v1). */
export const US_FLORIDA: SectionDef = {
  id: 14,
  apiPrefix: 'usfl',
  version: 1,
  coreFields: [
    field('Version', 6),
    field('SharingNotice', 2),
    field('SaleOptOutNotice', 2),
    field('TargetedAdvertisingOptOutNotice', 2),
    field('SaleOptOut', 2),
    field('TargetedAdvertisingOptOut', 2),
    arrayField('SensitiveDataProcessing', 2, 8),
    arrayField('KnownChildSensitiveDataConsents', 2, 3),
    field('PersonalDataConsents', 2),
    field('MspaCoveredTransaction', 2),
    field('MspaOptOutOptionMode', 2),
    field('MspaServiceProviderMode', 2),
  ],
  hasGpcSubsection: true,
};

/** Registry of all known section definitions, keyed by section ID. */
export const SECTION_REGISTRY: Map<number, SectionDef> = new Map([
  [US_NATIONAL.id, US_NATIONAL],
  [US_CALIFORNIA.id, US_CALIFORNIA],
  [US_VIRGINIA.id, US_VIRGINIA],
  [US_COLORADO.id, US_COLORADO],
  [US_CONNECTICUT.id, US_CONNECTICUT],
  [US_FLORIDA.id, US_FLORIDA],
]);

// ── Section encoding/decoding ────────────────────────────────────────

/** GPC sub-section data (appended after a section's core segment). */
export interface GpcSubsection {
  /** Whether the browser's Global Privacy Control signal was detected. */
  gpc: boolean;
}

/** Encode a section's core fields to base64url. */
export function encodeSectionCore(def: SectionDef, data: SectionData): string {
  const writer = new BitWriter();

  for (const fieldDef of def.coreFields) {
    const value = data[fieldDef.name];
    if (fieldDef.count > 1) {
      const arr = (value as number[]) ?? new Array(fieldDef.count).fill(0);
      for (let i = 0; i < fieldDef.count; i++) {
        writer.writeInt(arr[i] ?? 0, fieldDef.bits);
      }
    } else {
      writer.writeInt((value as number) ?? 0, fieldDef.bits);
    }
  }

  return bytesToBase64url(writer.toBytes());
}

/** Encode a GPC sub-section to base64url. */
export function encodeGpcSubsection(gpc: GpcSubsection): string {
  const writer = new BitWriter();
  writer.writeInt(1, 2); // SubsectionType = 1 (GPC)
  writer.writeBool(gpc.gpc);
  return bytesToBase64url(writer.toBytes());
}

/**
 * Encode a full section (core + optional GPC sub-section).
 * Sub-sections are separated from the core by a '.' character.
 */
export function encodeSection(
  def: SectionDef,
  data: SectionData,
  gpcSubsection?: GpcSubsection,
): string {
  const core = encodeSectionCore(def, data);
  if (def.hasGpcSubsection && gpcSubsection) {
    return `${core}.${encodeGpcSubsection(gpcSubsection)}`;
  }
  return core;
}

/** Decode a section's core fields from base64url. */
export function decodeSectionCore(def: SectionDef, encoded: string): SectionData {
  const bytes = base64urlToBytes(encoded);
  const reader = new BitReader(bytes);
  const data: SectionData = {};

  for (const fieldDef of def.coreFields) {
    if (fieldDef.count > 1) {
      const arr: number[] = [];
      for (let i = 0; i < fieldDef.count; i++) {
        arr.push(reader.readInt(fieldDef.bits));
      }
      data[fieldDef.name] = arr;
    } else {
      data[fieldDef.name] = reader.readInt(fieldDef.bits);
    }
  }

  return data;
}

/** Decode a GPC sub-section from base64url. */
export function decodeGpcSubsection(encoded: string): GpcSubsection {
  const bytes = base64urlToBytes(encoded);
  const reader = new BitReader(bytes);
  reader.readInt(2); // SubsectionType — skip (always 1)
  return { gpc: reader.readBool() };
}

/**
 * Decode a full section (core + optional GPC sub-section).
 * Splits on '.' to separate core from sub-sections.
 */
export function decodeSection(
  def: SectionDef,
  encoded: string,
): { data: SectionData; gpcSubsection?: GpcSubsection } {
  const parts = encoded.split('.');
  const data = decodeSectionCore(def, parts[0]);
  let gpcSubsection: GpcSubsection | undefined;

  if (def.hasGpcSubsection && parts.length > 1) {
    gpcSubsection = decodeGpcSubsection(parts[1]);
  }

  return { data, gpcSubsection };
}

// ── Full GPP string encoding/decoding ────────────────────────────────

/** A fully decoded GPP string with header and section data. */
export interface GppString {
  header: GppHeader;
  sections: Map<number, { data: SectionData; gpcSubsection?: GpcSubsection }>;
}

/**
 * Encode a complete GPP string.
 * Format: `{header}~{section1}~{section2}~...`
 * Sections appear in the order listed in header.sectionIds.
 */
export function encodeGppString(gpp: GppString): string {
  const parts: string[] = [encodeGppHeader(gpp.header)];

  for (const sectionId of gpp.header.sectionIds) {
    const section = gpp.sections.get(sectionId);
    const def = SECTION_REGISTRY.get(sectionId);

    if (!section || !def) {
      throw new Error(`No data or definition for GPP section ${sectionId}`);
    }

    parts.push(encodeSection(def, section.data, section.gpcSubsection));
  }

  return parts.join('~');
}

/**
 * Decode a complete GPP string.
 * Splits on '~'; first segment is the header, subsequent segments are section payloads
 * matched against header.sectionIds in order.
 */
export function decodeGppString(gppString: string): GppString {
  const parts = gppString.split('~');

  if (parts.length < 1) {
    throw new Error('Invalid GPP string: empty');
  }

  const header = decodeGppHeader(parts[0]);
  const sections = new Map<number, { data: SectionData; gpcSubsection?: GpcSubsection }>();

  for (let i = 0; i < header.sectionIds.length; i++) {
    const sectionId = header.sectionIds[i];
    const sectionPayload = parts[i + 1];

    if (!sectionPayload) {
      throw new Error(`Missing payload for GPP section ${sectionId}`);
    }

    const def = SECTION_REGISTRY.get(sectionId);
    if (!def) {
      // Unknown section — skip (cannot decode without a definition)
      continue;
    }

    sections.set(sectionId, decodeSection(def, sectionPayload));
  }

  return { header, sections };
}

// ── Convenience helpers ──────────────────────────────────────────────

/** Create default (all-zero / N/A) data for a section, with Version pre-filled. */
export function createDefaultSectionData(def: SectionDef): SectionData {
  const data: SectionData = {};

  for (const fieldDef of def.coreFields) {
    if (fieldDef.name === 'Version') {
      data[fieldDef.name] = def.version;
    } else if (fieldDef.count > 1) {
      data[fieldDef.name] = new Array(fieldDef.count).fill(0);
    } else {
      data[fieldDef.name] = 0;
    }
  }

  return data;
}

/** Look up a section definition by API prefix (e.g. 'usnat', 'usca'). */
export function getSectionByPrefix(prefix: string): SectionDef | undefined {
  for (const def of SECTION_REGISTRY.values()) {
    if (def.apiPrefix === prefix) return def;
  }
  return undefined;
}

/**
 * Register a custom section definition (for new US states or non-US sections).
 * Overwrites any existing definition with the same section ID.
 */
export function registerSection(def: SectionDef): void {
  SECTION_REGISTRY.set(def.id, def);
}
