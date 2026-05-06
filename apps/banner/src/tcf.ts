/**
 * IAB TCF v2.3 — TC string encoder/decoder and __tcfapi interface.
 *
 * Implements the Transparency & Consent Framework v2.3 specification:
 * - Encode 3-segment TC strings (Core + DisclosedVendors). The
 *   DisclosedVendors segment became mandatory for any TC string created
 *   on or after 1 March 2026 per the IAB Europe v2.3 transition.
 * - Decode is read-compatible with legacy single-segment v2.2 strings;
 *   missing DisclosedVendors yields an empty disclosure set.
 * - Standard __tcfapi interface (getTCData, ping, addEventListener,
 *   removeEventListener) with the v2.3 ``disclosedVendors`` field on
 *   TCData and ``apiVersion: '2.3'`` on ping.
 *
 * Note on tcfPolicyVersion: remains 4 in v2.3. The IAB Tech Lab spec
 * change (PR #404) is structural — a new mandatory segment plus an
 * additive TCData field — not a policy version bump.
 *
 * @see https://github.com/InteractiveAdvertisingBureau/GDPR-Transparency-and-Consent-Framework
 * @see https://iabeurope.eu/all-you-need-to-know-about-the-transition-to-tcf-v2-3/
 */

declare global {
  interface Window {
    __tcfapi?: (
      command: string,
      version: number,
      callback: TcfApiCallback,
      parameter?: unknown
    ) => void;
    __tcfapiQueue?: unknown[][];
  }
}

// ── Types ────────────────────────────────────────────────────────────

/** Core TC string data model. */
export interface TCModel {
  /** TC string format version — always 2 for TCF v2.x. */
  version: number;
  /** Deciseconds since epoch when consent was first created. */
  created: number;
  /** Deciseconds since epoch when consent was last updated. */
  lastUpdated: number;
  /** Registered CMP ID from the IAB CMP List. */
  cmpId: number;
  /** CMP version. */
  cmpVersion: number;
  /** Screen number in the CMP where consent was collected. */
  consentScreen: number;
  /** ISO 639-1 two-letter language code (upper-case). */
  consentLanguage: string;
  /** Version of the GVL used to create this TC string. */
  vendorListVersion: number;
  /** TCF policy version — 4 (unchanged in v2.3; structural changes only). */
  tcfPolicyVersion: number;
  /** Whether this TC string is specific to this service. */
  isServiceSpecific: boolean;
  /** Whether non-standard texts were used (deprecated in 2.2). */
  useNonStandardTexts: boolean;
  /** Opted-in special feature IDs (1-indexed). */
  specialFeatureOptIns: Set<number>;
  /** Consented purpose IDs (1-indexed, up to 24). */
  purposeConsents: Set<number>;
  /** Purpose IDs for which legitimate interest is established. */
  purposeLegitimateInterests: Set<number>;
  /** Whether Purpose 1 was NOT disclosed at time of consent (EU-specific). */
  purposeOneTreatment: boolean;
  /** ISO 3166-1 alpha-2 publisher country code. */
  publisherCC: string;
  /** Vendor IDs for which consent is given. */
  vendorConsents: Set<number>;
  /** Vendor IDs for which legitimate interest is established. */
  vendorLegitimateInterests: Set<number>;
  /** Publisher restrictions by purpose. */
  publisherRestrictions: PublisherRestriction[];
  /**
   * Vendor IDs disclosed to the user in the CMP UI (TCF v2.3).
   * Mandatory in TC strings created on or after 1 March 2026.
   */
  disclosedVendors: Set<number>;
}

/** A publisher restriction entry. */
export interface PublisherRestriction {
  purposeId: number;
  restrictionType: RestrictionType;
  vendorIds: Set<number>;
}

/** Restriction type values per the TCF spec. */
export enum RestrictionType {
  /** Purpose is flatly not allowed by publisher. */
  NOT_ALLOWED = 0,
  /** Require consent (override LI). */
  REQUIRE_CONSENT = 1,
  /** Require legitimate interest (override consent). */
  REQUIRE_LEGITIMATE_INTEREST = 2,
}

/** Return type for the __tcfapi getTCData command. */
export interface TCData {
  tcString: string;
  tcfPolicyVersion: number;
  cmpId: number;
  cmpVersion: number;
  gdprApplies: boolean;
  eventStatus: 'tcloaded' | 'cmpuishown' | 'useractioncomplete';
  cmpStatus: 'loaded' | 'error';
  listenerId?: number;
  isServiceSpecific: boolean;
  useNonStandardTexts: boolean;
  publisherCC: string;
  purposeOneTreatment: boolean;
  purpose: {
    consents: Record<string, boolean>;
    legitimateInterests: Record<string, boolean>;
  };
  vendor: {
    consents: Record<string, boolean>;
    legitimateInterests: Record<string, boolean>;
  };
  specialFeatureOptins: Record<string, boolean>;
  /** Vendor IDs disclosed in the CMP UI (TCF v2.3+). */
  disclosedVendors: Record<string, boolean>;
}

/** Return type for the __tcfapi ping command. */
export interface PingReturn {
  gdprApplies: boolean;
  cmpLoaded: boolean;
  cmpStatus: 'loaded' | 'error' | 'stub';
  displayStatus: 'visible' | 'hidden' | 'disabled';
  apiVersion: string;
  cmpVersion: number;
  cmpId: number;
  gvlVersion: number;
  tcfPolicyVersion: number;
}

/** Callback type for __tcfapi commands. */
export type TcfApiCallback = (result: TCData | PingReturn | boolean, success: boolean) => void;

// ── Bit manipulation ─────────────────────────────────────────────────

/** Writes bits sequentially into a byte buffer. */
export class BitWriter {
  private bytes: number[] = [];
  private currentByte = 0;
  private bitIndex = 0;

  /** Write `length` bits from `value` (MSB first). */
  writeInt(value: number, length: number): void {
    for (let i = length - 1; i >= 0; i--) {
      const bit = (value >>> i) & 1;
      this.currentByte = (this.currentByte << 1) | bit;
      this.bitIndex++;
      if (this.bitIndex === 8) {
        this.bytes.push(this.currentByte);
        this.currentByte = 0;
        this.bitIndex = 0;
      }
    }
  }

  /** Write a single boolean bit. */
  writeBool(value: boolean): void {
    this.writeInt(value ? 1 : 0, 1);
  }

  /** Write a Set of IDs as a bitfield of `maxId` bits. */
  writeBitfield(ids: Set<number>, maxId: number): void {
    for (let i = 1; i <= maxId; i++) {
      this.writeBool(ids.has(i));
    }
  }

  /** Write a two-letter code as 2 × 6-bit values (A=0, B=1, ...). */
  writeLetters(code: string): void {
    const upper = code.toUpperCase();
    this.writeInt(upper.charCodeAt(0) - 65, 6);
    this.writeInt(upper.charCodeAt(1) - 65, 6);
  }

  /** Finalise and return the accumulated bytes (padding the last byte). */
  toBytes(): Uint8Array {
    const result = new Uint8Array(this.bytes.length + (this.bitIndex > 0 ? 1 : 0));
    for (let i = 0; i < this.bytes.length; i++) {
      result[i] = this.bytes[i];
    }
    if (this.bitIndex > 0) {
      result[this.bytes.length] = this.currentByte << (8 - this.bitIndex);
    }
    return result;
  }
}

/** Reads bits sequentially from a byte buffer. */
export class BitReader {
  private bytes: Uint8Array;
  private bitOffset = 0;

  constructor(bytes: Uint8Array) {
    this.bytes = bytes;
  }

  /** Read `length` bits as an unsigned integer. */
  readInt(length: number): number {
    let value = 0;
    for (let i = 0; i < length; i++) {
      const byteIndex = (this.bitOffset + i) >> 3;
      const bitPosition = 7 - ((this.bitOffset + i) & 7);
      if (byteIndex < this.bytes.length) {
        value = (value << 1) | ((this.bytes[byteIndex] >> bitPosition) & 1);
      } else {
        value = value << 1;
      }
    }
    this.bitOffset += length;
    return value;
  }

  /** Read a single bit as boolean. */
  readBool(): boolean {
    return this.readInt(1) === 1;
  }

  /** Read a bitfield of `maxId` bits into a Set. */
  readBitfield(maxId: number): Set<number> {
    const ids = new Set<number>();
    for (let i = 1; i <= maxId; i++) {
      if (this.readBool()) {
        ids.add(i);
      }
    }
    return ids;
  }

  /** Read 2 × 6-bit letters as a two-char string. */
  readLetters(): string {
    const a = this.readInt(6);
    const b = this.readInt(6);
    return String.fromCharCode(a + 65, b + 65);
  }

  /** Check whether there are at least `bits` remaining. */
  hasRemaining(bits: number): boolean {
    return this.bitOffset + bits <= this.bytes.length * 8;
  }
}

// ── Base64url encoding ───────────────────────────────────────────────

const B64_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';

/** Encode bytes to websafe base64 (no padding). */
export function bytesToBase64url(bytes: Uint8Array): string {
  let result = '';
  for (let i = 0; i < bytes.length; i += 3) {
    const b0 = bytes[i];
    const b1 = i + 1 < bytes.length ? bytes[i + 1] : 0;
    const b2 = i + 2 < bytes.length ? bytes[i + 2] : 0;
    const triple = (b0 << 16) | (b1 << 8) | b2;

    result += B64_CHARS[(triple >> 18) & 0x3f];
    result += B64_CHARS[(triple >> 12) & 0x3f];
    if (i + 1 < bytes.length) result += B64_CHARS[(triple >> 6) & 0x3f];
    if (i + 2 < bytes.length) result += B64_CHARS[triple & 0x3f];
  }
  return result;
}

/** Decode websafe base64 (no padding) to bytes. */
export function base64urlToBytes(str: string): Uint8Array {
  const lookup = new Uint8Array(128);
  for (let i = 0; i < B64_CHARS.length; i++) {
    lookup[B64_CHARS.charCodeAt(i)] = i;
  }

  // Calculate output length (account for missing padding)
  const paddedLen = str.length + ((4 - (str.length % 4)) % 4);
  const byteLen = (paddedLen * 3) / 4 - (paddedLen - str.length);
  const bytes = new Uint8Array(byteLen);

  let j = 0;
  for (let i = 0; i < str.length; i += 4) {
    const a = lookup[str.charCodeAt(i)] ?? 0;
    const b = i + 1 < str.length ? (lookup[str.charCodeAt(i + 1)] ?? 0) : 0;
    const c = i + 2 < str.length ? (lookup[str.charCodeAt(i + 2)] ?? 0) : 0;
    const d = i + 3 < str.length ? (lookup[str.charCodeAt(i + 3)] ?? 0) : 0;

    if (j < byteLen) bytes[j++] = (a << 2) | (b >> 4);
    if (j < byteLen) bytes[j++] = ((b & 0xf) << 4) | (c >> 2);
    if (j < byteLen) bytes[j++] = ((c & 0x3) << 6) | d;
  }
  return bytes;
}

// ── Encoding ─────────────────────────────────────────────────────────

/** Number of purpose bits defined by the TCF spec. */
const NUM_PURPOSES = 24;
/** Number of special feature bits. */
const NUM_SPECIAL_FEATURES = 12;

/** Convert a JS timestamp (ms) to TCF deciseconds. */
export function msToDeciseconds(ms: number): number {
  return Math.round(ms / 100);
}

/** Convert TCF deciseconds to a JS timestamp (ms). */
export function decisecondsToMs(ds: number): number {
  return ds * 100;
}

/** Create a default (empty) TCModel with sensible defaults. */
export function createTCModel(overrides?: Partial<TCModel>): TCModel {
  const now = msToDeciseconds(Date.now());
  return {
    version: 2,
    created: now,
    lastUpdated: now,
    cmpId: 0,
    cmpVersion: 1,
    consentScreen: 1,
    consentLanguage: 'EN',
    vendorListVersion: 0,
    tcfPolicyVersion: 4,
    isServiceSpecific: true,
    useNonStandardTexts: false,
    specialFeatureOptIns: new Set(),
    purposeConsents: new Set(),
    purposeLegitimateInterests: new Set(),
    purposeOneTreatment: false,
    publisherCC: 'GB',
    vendorConsents: new Set(),
    vendorLegitimateInterests: new Set(),
    publisherRestrictions: [],
    disclosedVendors: new Set(),
    ...overrides,
  };
}

// ── TCF v2.3 segment types ───────────────────────────────────────────

/**
 * Non-core TC string segments. Each non-core segment is prefixed by a
 * 3-bit SegmentType field per the IAB Tech Lab "Consent string and
 * vendor list formats v2" spec.
 */
export enum SegmentType {
  /** DisclosedVendors — required in TCF v2.3. */
  DisclosedVendors = 1,
  /** AllowedVendors — service-specific OOB; not currently emitted. */
  AllowedVendors = 2,
  /** Publisher TC — optional publisher purpose data. */
  PublisherTC = 3,
}

/**
 * Encode a TCModel into a TCF v2.3 TC string.
 *
 * Output format: ``<core>.<disclosedVendors>`` — both segments are
 * mandatory under TCF v2.3 for any string created on or after
 * 1 March 2026. The DisclosedVendors segment is allowed to be empty
 * (``maxVendorId = 0``) but the segment itself must be present.
 */
export function encodeTCString(model: TCModel): string {
  const core = encodeCoreSegment(model);
  const disclosed = encodeDisclosedVendorsSegment(model.disclosedVendors);
  return `${core}.${disclosed}`;
}

/** Encode just the Core segment (without segment type prefix). */
function encodeCoreSegment(model: TCModel): string {
  const writer = new BitWriter();

  // Core segment
  writer.writeInt(model.version, 6);
  writer.writeInt(model.created, 36);
  writer.writeInt(model.lastUpdated, 36);
  writer.writeInt(model.cmpId, 12);
  writer.writeInt(model.cmpVersion, 12);
  writer.writeInt(model.consentScreen, 6);
  writer.writeLetters(model.consentLanguage);
  writer.writeInt(model.vendorListVersion, 12);
  writer.writeInt(model.tcfPolicyVersion, 6);
  writer.writeBool(model.isServiceSpecific);
  writer.writeBool(model.useNonStandardTexts);
  writer.writeBitfield(model.specialFeatureOptIns, NUM_SPECIAL_FEATURES);
  writer.writeBitfield(model.purposeConsents, NUM_PURPOSES);
  writer.writeBitfield(model.purposeLegitimateInterests, NUM_PURPOSES);
  writer.writeBool(model.purposeOneTreatment);
  writer.writeLetters(model.publisherCC);

  // Vendor consent section (bitfield encoding)
  const maxVendorConsent = maxId(model.vendorConsents);
  writer.writeInt(maxVendorConsent, 16);
  if (maxVendorConsent > 0) {
    writer.writeBool(false); // IsRangeEncoding = false (bitfield)
    writer.writeBitfield(model.vendorConsents, maxVendorConsent);
  }

  // Vendor legitimate interest section (bitfield encoding)
  const maxVendorLI = maxId(model.vendorLegitimateInterests);
  writer.writeInt(maxVendorLI, 16);
  if (maxVendorLI > 0) {
    writer.writeBool(false); // IsRangeEncoding = false (bitfield)
    writer.writeBitfield(model.vendorLegitimateInterests, maxVendorLI);
  }

  // Publisher restrictions
  writer.writeInt(model.publisherRestrictions.length, 12);
  for (const restriction of model.publisherRestrictions) {
    writer.writeInt(restriction.purposeId, 6);
    writer.writeInt(restriction.restrictionType, 2);
    // Encode vendor IDs as ranges
    const sortedVendors = [...restriction.vendorIds].sort((a, b) => a - b);
    const ranges = toRanges(sortedVendors);
    writer.writeInt(ranges.length, 12);
    for (const [start, end] of ranges) {
      const isRange = start !== end;
      writer.writeBool(isRange);
      writer.writeInt(start, 16);
      if (isRange) {
        writer.writeInt(end, 16);
      }
    }
  }

  return bytesToBase64url(writer.toBytes());
}

/**
 * Encode a DisclosedVendors segment (TCF v2.3).
 *
 * Layout: ``SegmentType (3 bits) | MaxVendorId (16 bits) | [IsRange + entries]``.
 * Uses bitfield encoding (range encoding is permitted by spec but
 * bitfield is what the rest of the encoder uses for vendor sections).
 */
export function encodeDisclosedVendorsSegment(disclosedVendors: Set<number>): string {
  const writer = new BitWriter();
  writer.writeInt(SegmentType.DisclosedVendors, 3);
  const max = maxId(disclosedVendors);
  writer.writeInt(max, 16);
  if (max > 0) {
    writer.writeBool(false); // IsRangeEncoding = false (bitfield)
    writer.writeBitfield(disclosedVendors, max);
  }
  return bytesToBase64url(writer.toBytes());
}

/**
 * Decode a single non-core segment.
 *
 * Returns the parsed disclosed vendors when the segment is a
 * DisclosedVendors segment; returns ``null`` for any other segment
 * type (AllowedVendors, PublisherTC) which we currently ignore.
 */
function decodeSegment(segment: string): { disclosedVendors: Set<number> } | null {
  if (segment.length === 0) return null;
  const bytes = base64urlToBytes(segment);
  if (bytes.length === 0) return null;

  const reader = new BitReader(bytes);
  const segmentType = reader.readInt(3);

  if (segmentType !== SegmentType.DisclosedVendors) {
    // Skip AllowedVendors (2) and PublisherTC (3) — not currently consumed.
    return null;
  }

  const max = reader.readInt(16);
  if (max === 0) return { disclosedVendors: new Set() };

  const isRange = reader.readBool();
  if (isRange) {
    return { disclosedVendors: readRangeEntries(reader) };
  }
  return { disclosedVendors: reader.readBitfield(max) };
}

/**
 * Decode a TC string back into a TCModel.
 *
 * Read-compatible with both legacy v2.2 (single Core segment) and
 * v2.3 (Core + DisclosedVendors) strings. Cached strings created
 * before the v2.3 deadline remain valid per the IAB Europe transition
 * note and decode to a model with empty ``disclosedVendors``.
 */
export function decodeTCString(tcString: string): TCModel {
  const segments = tcString.split('.');
  const coreSegment = segments[0];
  const bytes = base64urlToBytes(coreSegment);
  const reader = new BitReader(bytes);

  const version = reader.readInt(6);
  const created = reader.readInt(36);
  const lastUpdated = reader.readInt(36);
  const cmpId = reader.readInt(12);
  const cmpVersion = reader.readInt(12);
  const consentScreen = reader.readInt(6);
  const consentLanguage = reader.readLetters();
  const vendorListVersion = reader.readInt(12);
  const tcfPolicyVersion = reader.readInt(6);
  const isServiceSpecific = reader.readBool();
  const useNonStandardTexts = reader.readBool();
  const specialFeatureOptIns = reader.readBitfield(NUM_SPECIAL_FEATURES);
  const purposeConsents = reader.readBitfield(NUM_PURPOSES);
  const purposeLegitimateInterests = reader.readBitfield(NUM_PURPOSES);
  const purposeOneTreatment = reader.readBool();
  const publisherCC = reader.readLetters();

  // Vendor consents
  let vendorConsents = new Set<number>();
  const maxVendorConsent = reader.readInt(16);
  if (maxVendorConsent > 0) {
    const isRange = reader.readBool();
    if (isRange) {
      vendorConsents = readRangeEntries(reader);
    } else {
      vendorConsents = reader.readBitfield(maxVendorConsent);
    }
  }

  // Vendor legitimate interests
  let vendorLegitimateInterests = new Set<number>();
  const maxVendorLI = reader.readInt(16);
  if (maxVendorLI > 0) {
    const isRange = reader.readBool();
    if (isRange) {
      vendorLegitimateInterests = readRangeEntries(reader);
    } else {
      vendorLegitimateInterests = reader.readBitfield(maxVendorLI);
    }
  }

  // Publisher restrictions
  const publisherRestrictions: PublisherRestriction[] = [];
  if (reader.hasRemaining(12)) {
    const numRestrictions = reader.readInt(12);
    for (let i = 0; i < numRestrictions; i++) {
      const purposeId = reader.readInt(6);
      const restrictionType = reader.readInt(2) as RestrictionType;
      const numRanges = reader.readInt(12);
      const vendorIds = new Set<number>();
      for (let j = 0; j < numRanges; j++) {
        const isRangeEntry = reader.readBool();
        const startId = reader.readInt(16);
        if (isRangeEntry) {
          const endId = reader.readInt(16);
          for (let v = startId; v <= endId; v++) vendorIds.add(v);
        } else {
          vendorIds.add(startId);
        }
      }
      publisherRestrictions.push({ purposeId, restrictionType, vendorIds });
    }
  }

  // Parse any non-core segments (DisclosedVendors / AllowedVendors /
  // PublisherTC). Legacy v2.2 strings have only one segment so this
  // loop is a no-op for them and ``disclosedVendors`` stays empty.
  let disclosedVendors = new Set<number>();
  for (let i = 1; i < segments.length; i++) {
    const parsed = decodeSegment(segments[i]);
    if (parsed?.disclosedVendors) {
      disclosedVendors = parsed.disclosedVendors;
    }
  }

  return {
    version,
    created,
    lastUpdated,
    cmpId,
    cmpVersion,
    consentScreen,
    consentLanguage,
    vendorListVersion,
    tcfPolicyVersion,
    isServiceSpecific,
    useNonStandardTexts,
    specialFeatureOptIns,
    purposeConsents,
    purposeLegitimateInterests,
    purposeOneTreatment,
    publisherCC,
    vendorConsents,
    vendorLegitimateInterests,
    publisherRestrictions,
    disclosedVendors,
  };
}

// ── Range helpers ────────────────────────────────────────────────────

/** Read range-encoded vendor entries from a BitReader. */
function readRangeEntries(reader: BitReader): Set<number> {
  const ids = new Set<number>();
  const numEntries = reader.readInt(12);
  for (let i = 0; i < numEntries; i++) {
    const isRange = reader.readBool();
    const startId = reader.readInt(16);
    if (isRange) {
      const endId = reader.readInt(16);
      for (let v = startId; v <= endId; v++) ids.add(v);
    } else {
      ids.add(startId);
    }
  }
  return ids;
}

/** Convert sorted vendor IDs to contiguous [start, end] ranges. */
function toRanges(sorted: number[]): [number, number][] {
  if (sorted.length === 0) return [];
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
  return ranges;
}

/** Get the maximum ID from a Set, or 0 if empty. */
function maxId(ids: Set<number>): number {
  let max = 0;
  ids.forEach((id) => {
    if (id > max) max = id;
  });
  return max;
}

// ── __tcfapi interface ───────────────────────────────────────────────

interface TcfApiState {
  cmpId: number;
  cmpVersion: number;
  gdprApplies: boolean;
  tcModel: TCModel | null;
  tcString: string;
  displayStatus: 'visible' | 'hidden' | 'disabled';
  listeners: Map<number, TcfApiCallback>;
  nextListenerId: number;
}

let apiState: TcfApiState | null = null;

/** Build a TCData response from the current state. */
function buildTCData(
  state: TcfApiState,
  eventStatus: TCData['eventStatus'],
  listenerId?: number
): TCData {
  const model = state.tcModel;
  const purposeConsents: Record<string, boolean> = {};
  const purposeLI: Record<string, boolean> = {};
  const vendorConsents: Record<string, boolean> = {};
  const vendorLI: Record<string, boolean> = {};
  const specialFeatures: Record<string, boolean> = {};
  const disclosedVendors: Record<string, boolean> = {};

  if (model) {
    for (let i = 1; i <= NUM_PURPOSES; i++) {
      purposeConsents[String(i)] = model.purposeConsents.has(i);
      purposeLI[String(i)] = model.purposeLegitimateInterests.has(i);
    }
    const maxVC = maxId(model.vendorConsents);
    const maxVLI = maxId(model.vendorLegitimateInterests);
    const maxDV = maxId(model.disclosedVendors);
    const vendorMax = Math.max(maxVC, maxVLI);
    for (let i = 1; i <= vendorMax; i++) {
      vendorConsents[String(i)] = model.vendorConsents.has(i);
      vendorLI[String(i)] = model.vendorLegitimateInterests.has(i);
    }
    for (let i = 1; i <= maxDV; i++) {
      disclosedVendors[String(i)] = model.disclosedVendors.has(i);
    }
    for (let i = 1; i <= NUM_SPECIAL_FEATURES; i++) {
      specialFeatures[String(i)] = model.specialFeatureOptIns.has(i);
    }
  }

  return {
    tcString: state.tcString,
    tcfPolicyVersion: model?.tcfPolicyVersion ?? 4,
    cmpId: state.cmpId,
    cmpVersion: state.cmpVersion,
    gdprApplies: state.gdprApplies,
    eventStatus,
    cmpStatus: 'loaded',
    listenerId,
    isServiceSpecific: model?.isServiceSpecific ?? true,
    useNonStandardTexts: model?.useNonStandardTexts ?? false,
    publisherCC: model?.publisherCC ?? 'GB',
    purposeOneTreatment: model?.purposeOneTreatment ?? false,
    purpose: {
      consents: purposeConsents,
      legitimateInterests: purposeLI,
    },
    vendor: {
      consents: vendorConsents,
      legitimateInterests: vendorLI,
    },
    specialFeatureOptins: specialFeatures,
    disclosedVendors,
  };
}

/** The __tcfapi function handler. */
function tcfApiHandler(
  command: string,
  version: number,
  callback: TcfApiCallback,
  _parameter?: unknown
): void {
  if (!apiState) {
    callback(false, false);
    return;
  }

  if (version !== 2) {
    callback(false, false);
    return;
  }

  switch (command) {
    case 'ping': {
      const pingReturn: PingReturn = {
        gdprApplies: apiState.gdprApplies,
        cmpLoaded: true,
        cmpStatus: 'loaded',
        displayStatus: apiState.displayStatus,
        apiVersion: '2.3',
        cmpVersion: apiState.cmpVersion,
        cmpId: apiState.cmpId,
        gvlVersion: apiState.tcModel?.vendorListVersion ?? 0,
        tcfPolicyVersion: apiState.tcModel?.tcfPolicyVersion ?? 4,
      };
      callback(pingReturn, true);
      break;
    }

    case 'getTCData': {
      const eventStatus = apiState.tcString ? 'tcloaded' : 'cmpuishown';
      callback(buildTCData(apiState, eventStatus), true);
      break;
    }

    case 'addEventListener': {
      const listenerId = apiState.nextListenerId++;
      apiState.listeners.set(listenerId, callback);
      const eventStatus = apiState.tcString ? 'tcloaded' : 'cmpuishown';
      try {
        callback(buildTCData(apiState, eventStatus, listenerId), true);
      } catch {
        // Swallow listener errors during initial notification
      }
      break;
    }

    case 'removeEventListener': {
      // _parameter is the listenerId to remove
      const id = _parameter as number;
      const removed = apiState.listeners.delete(id);
      callback(removed, removed);
      break;
    }

    default:
      callback(false, false);
  }
}

// ── Cross-frame __tcfapi (postMessage proxy + locator iframe) ────────

/** Active message listener — kept so we can remove it on tear-down. */
let messageListener: ((event: MessageEvent) => void) | null = null;
/** The hidden ``__tcfapiLocator`` iframe vendors detect via frame walking. */
let locatorFrame: HTMLIFrameElement | null = null;

/** Cross-frame message envelope sent by vendor iframes to call __tcfapi. */
interface TcfApiCall {
  command: string;
  parameter?: unknown;
  version: number;
  callId: unknown;
}

/**
 * Create the ``__tcfapiLocator`` iframe.
 *
 * Vendors running inside iframes walk up the parent chain looking for a
 * window that has a child iframe named ``__tcfapiLocator``. That window
 * is the one running the CMP, and they then ``postMessage`` to it with
 * an ``__tcfapiCall`` envelope. Without this iframe vendors can't find
 * the CMP from inside an ad iframe.
 */
function installLocatorFrame(): void {
  if (typeof document === 'undefined') return;
  if (document.querySelector('iframe[name="__tcfapiLocator"]')) return;

  const frame = document.createElement('iframe');
  frame.name = '__tcfapiLocator';
  frame.style.cssText =
    'display:none;position:absolute;top:0;left:0;border:0;width:1px;height:1px';
  frame.setAttribute('aria-hidden', 'true');
  frame.tabIndex = -1;

  if (document.body) {
    document.body.appendChild(frame);
  } else {
    // Mount once the body exists; head-time installs (loader) need this.
    document.addEventListener(
      'DOMContentLoaded',
      () => {
        if (
          document.body &&
          !document.querySelector('iframe[name="__tcfapiLocator"]')
        ) {
          document.body.appendChild(frame);
        }
      },
      { once: true }
    );
  }

  locatorFrame = frame;
}

/** Remove the locator iframe (idempotent). */
function removeLocatorFrame(): void {
  if (locatorFrame && locatorFrame.parentNode) {
    locatorFrame.parentNode.removeChild(locatorFrame);
  }
  locatorFrame = null;
}

/** Pull a TcfApiCall envelope out of a postMessage payload, if present. */
function extractCall(data: unknown): TcfApiCall | undefined {
  if (typeof data === 'string') {
    try {
      const parsed = JSON.parse(data);
      return parsed?.__tcfapiCall;
    } catch {
      return undefined;
    }
  }
  if (data && typeof data === 'object') {
    return (data as { __tcfapiCall?: TcfApiCall }).__tcfapiCall;
  }
  return undefined;
}

/**
 * Install the ``message`` listener that proxies cross-frame __tcfapi
 * calls.
 *
 * Wire: vendor iframe ``postMessage({ __tcfapiCall: {...} })`` →
 * our listener → ``tcfApiHandler`` → ``postMessage({ __tcfapiReturn: {...} })``
 * back to the original sender. The wire format mirrors whatever the
 * caller sent (string vs object) so callers using ``JSON.stringify``
 * and callers passing raw objects both work.
 */
function installPostMessageHandler(): void {
  if (typeof window === 'undefined') return;
  // Idempotent — repeat installs would otherwise leak a stale listener.
  removePostMessageHandler();

  messageListener = (event: MessageEvent) => {
    const call = extractCall(event.data);
    if (!call || typeof call.command !== 'string') return;

    tcfApiHandler(
      call.command,
      call.version,
      (returnValue, success) => {
        const response = {
          __tcfapiReturn: {
            returnValue,
            success,
            callId: call.callId,
          },
        };
        const wire =
          typeof event.data === 'string' ? JSON.stringify(response) : response;

        if (event.source && 'postMessage' in event.source) {
          // sandboxed/null-origin iframes report ``"null"`` and require ``*``
          const target = event.origin && event.origin !== 'null' ? event.origin : '*';
          (event.source as Window).postMessage(wire, target);
        }
      },
      call.parameter
    );
  };

  window.addEventListener('message', messageListener);
}

/** Remove the postMessage listener (idempotent). */
function removePostMessageHandler(): void {
  if (messageListener && typeof window !== 'undefined') {
    window.removeEventListener('message', messageListener);
  }
  messageListener = null;
}

/** Process any queued __tcfapi calls from the stub. */
function processQueuedCalls(): void {
  if (typeof window === 'undefined') return;

  const queue = window.__tcfapiQueue;
  if (Array.isArray(queue)) {
    for (const args of queue) {
      tcfApiHandler(
        args[0] as string,
        args[1] as number,
        args[2] as TcfApiCallback,
        args[3]
      );
    }
    queue.length = 0;
  }
}

/**
 * Install the __tcfapi global function and process any queued calls.
 *
 * @param cmpId Registered CMP ID from the IAB CMP List.
 * @param cmpVersion CMP version number.
 * @param gdprApplies Whether GDPR applies to the current user.
 */
export function installTcfApi(
  cmpId: number,
  cmpVersion: number,
  gdprApplies: boolean = true
): void {
  apiState = {
    cmpId,
    cmpVersion,
    gdprApplies,
    tcModel: null,
    tcString: '',
    displayStatus: 'hidden',
    listeners: new Map(),
    nextListenerId: 1,
  };

  if (typeof window !== 'undefined') {
    window.__tcfapi = tcfApiHandler;
  }

  installLocatorFrame();
  installPostMessageHandler();
  processQueuedCalls();
}

/** Remove the __tcfapi global, locator iframe, and message listener. */
export function removeTcfApi(): void {
  if (typeof window !== 'undefined') {
    delete window.__tcfapi;
    delete window.__tcfapiQueue;
  }
  removePostMessageHandler();
  removeLocatorFrame();
  apiState = null;
}

/** Update the TCF state and notify all listeners. */
export function updateTcfConsent(model: TCModel): string {
  const tcString = encodeTCString(model);

  if (apiState) {
    apiState.tcModel = model;
    apiState.tcString = tcString;
    apiState.displayStatus = 'hidden';

    // Notify all listeners
    apiState.listeners.forEach((callback, listenerId) => {
      try {
        callback(buildTCData(apiState!, 'useractioncomplete', listenerId), true);
      } catch {
        // Swallow listener errors
      }
    });
  }

  return tcString;
}

/** Set the display status (visible when banner is shown). */
export function setTcfDisplayStatus(status: 'visible' | 'hidden' | 'disabled'): void {
  if (apiState) {
    apiState.displayStatus = status;
  }
}

/** Get the current TC string (empty if no consent yet). */
export function getTcString(): string {
  return apiState?.tcString ?? '';
}
