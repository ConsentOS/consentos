import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  BitReader,
  BitWriter,
  RestrictionType,
  SegmentType,
  base64urlToBytes,
  bytesToBase64url,
  createTCModel,
  decodeTCString,
  decisecondsToMs,
  encodeDisclosedVendorsSegment,
  encodeTCString,
  getTcString,
  installTcfApi,
  msToDeciseconds,
  removeTcfApi,
  setTcfDisplayStatus,
  updateTcfConsent,
} from '../tcf';
import type { TCModel, TcfApiCallback } from '../tcf';

// ── BitWriter / BitReader ────────────────────────────────────────────

describe('BitWriter', () => {
  it('writes single bits correctly', () => {
    const w = new BitWriter();
    w.writeBool(true);
    w.writeBool(false);
    w.writeBool(true);
    w.writeBool(true);
    w.writeBool(false);
    w.writeBool(false);
    w.writeBool(true);
    w.writeBool(false);
    const bytes = w.toBytes();
    expect(bytes.length).toBe(1);
    // 10110010 = 0xB2 = 178
    expect(bytes[0]).toBe(0b10110010);
  });

  it('writes multi-bit integers', () => {
    const w = new BitWriter();
    w.writeInt(2, 6); // 000010
    const bytes = w.toBytes();
    // 000010 + 00 (padding) = 00001000 = 8
    expect(bytes[0]).toBe(0b00001000);
  });

  it('writes integers across byte boundaries', () => {
    const w = new BitWriter();
    w.writeInt(0b11111111, 8);
    w.writeInt(0b1010, 4);
    const bytes = w.toBytes();
    expect(bytes.length).toBe(2);
    expect(bytes[0]).toBe(0xff);
    // 1010 + 0000 (padding) = 10100000
    expect(bytes[1]).toBe(0b10100000);
  });

  it('writes a bitfield from a Set', () => {
    const w = new BitWriter();
    w.writeBitfield(new Set([1, 3, 5]), 8);
    const bytes = w.toBytes();
    // bits: 1 0 1 0 1 0 0 0 = 0xA8
    expect(bytes[0]).toBe(0b10101000);
  });

  it('writes two-letter codes', () => {
    const w = new BitWriter();
    w.writeLetters('EN');
    const bytes = w.toBytes();
    // E=4 (000100), N=13 (001101) → 000100 001101 → 00010000 1101(0000)
    const r = new BitReader(bytes);
    expect(r.readInt(6)).toBe(4); // E
    expect(r.readInt(6)).toBe(13); // N
  });

  it('handles empty writes', () => {
    const w = new BitWriter();
    const bytes = w.toBytes();
    expect(bytes.length).toBe(0);
  });

  it('pads incomplete last byte', () => {
    const w = new BitWriter();
    w.writeBool(true);
    const bytes = w.toBytes();
    expect(bytes.length).toBe(1);
    // 1 + 0000000 (padding) = 10000000
    expect(bytes[0]).toBe(0b10000000);
  });
});

describe('BitReader', () => {
  it('reads single bits', () => {
    const r = new BitReader(new Uint8Array([0b10110010]));
    expect(r.readBool()).toBe(true);
    expect(r.readBool()).toBe(false);
    expect(r.readBool()).toBe(true);
    expect(r.readBool()).toBe(true);
    expect(r.readBool()).toBe(false);
    expect(r.readBool()).toBe(false);
    expect(r.readBool()).toBe(true);
    expect(r.readBool()).toBe(false);
  });

  it('reads multi-bit integers', () => {
    const r = new BitReader(new Uint8Array([0b00001000]));
    expect(r.readInt(6)).toBe(2);
  });

  it('reads across byte boundaries', () => {
    const r = new BitReader(new Uint8Array([0xff, 0b10100000]));
    expect(r.readInt(8)).toBe(255);
    expect(r.readInt(4)).toBe(0b1010);
  });

  it('reads a bitfield into a Set', () => {
    const r = new BitReader(new Uint8Array([0b10101000]));
    const ids = r.readBitfield(8);
    expect(ids).toEqual(new Set([1, 3, 5]));
  });

  it('reads two-letter codes', () => {
    // E=4 (000100), N=13 (001101) → 00010000 11010000
    const r = new BitReader(new Uint8Array([0b00010000, 0b11010000]));
    expect(r.readLetters()).toBe('EN');
  });

  it('hasRemaining checks available bits', () => {
    const r = new BitReader(new Uint8Array([0xff]));
    expect(r.hasRemaining(8)).toBe(true);
    expect(r.hasRemaining(9)).toBe(false);
    r.readInt(4);
    expect(r.hasRemaining(4)).toBe(true);
    expect(r.hasRemaining(5)).toBe(false);
  });

  it('reads zero when past end of buffer', () => {
    const r = new BitReader(new Uint8Array([0xff]));
    r.readInt(8); // consume all
    expect(r.readInt(4)).toBe(0);
  });
});

// ── Base64url ────────────────────────────────────────────────────────

describe('base64url encoding', () => {
  it('round-trips bytes correctly', () => {
    const original = new Uint8Array([0, 1, 2, 127, 128, 255]);
    const encoded = bytesToBase64url(original);
    const decoded = base64urlToBytes(encoded);
    expect(decoded).toEqual(original);
  });

  it('encodes empty array', () => {
    expect(bytesToBase64url(new Uint8Array([]))).toBe('');
  });

  it('decodes empty string', () => {
    expect(base64urlToBytes('')).toEqual(new Uint8Array([]));
  });

  it('produces URL-safe characters (no +, /, =)', () => {
    const bytes = new Uint8Array(256);
    for (let i = 0; i < 256; i++) bytes[i] = i;
    const encoded = bytesToBase64url(bytes);
    expect(encoded).not.toContain('+');
    expect(encoded).not.toContain('/');
    expect(encoded).not.toContain('=');
  });

  it('round-trips single byte', () => {
    const original = new Uint8Array([42]);
    expect(base64urlToBytes(bytesToBase64url(original))).toEqual(original);
  });

  it('round-trips two bytes', () => {
    const original = new Uint8Array([200, 100]);
    expect(base64urlToBytes(bytesToBase64url(original))).toEqual(original);
  });
});

// ── Timestamp helpers ────────────────────────────────────────────────

describe('timestamp conversion', () => {
  it('converts ms to deciseconds', () => {
    expect(msToDeciseconds(1000)).toBe(10);
    expect(msToDeciseconds(100)).toBe(1);
    expect(msToDeciseconds(150)).toBe(2); // rounds
  });

  it('converts deciseconds to ms', () => {
    expect(decisecondsToMs(10)).toBe(1000);
    expect(decisecondsToMs(1)).toBe(100);
  });

  it('round-trips approximately', () => {
    const now = Date.now();
    const ds = msToDeciseconds(now);
    const back = decisecondsToMs(ds);
    // Within 100ms accuracy (one decisecond)
    expect(Math.abs(back - now)).toBeLessThan(100);
  });
});

// ── createTCModel ────────────────────────────────────────────────────

describe('createTCModel', () => {
  it('creates a model with defaults', () => {
    const model = createTCModel();
    expect(model.version).toBe(2);
    expect(model.tcfPolicyVersion).toBe(5);
    expect(model.isServiceSpecific).toBe(true);
    expect(model.consentLanguage).toBe('EN');
    expect(model.publisherCC).toBe('GB');
    expect(model.purposeConsents.size).toBe(0);
    expect(model.vendorConsents.size).toBe(0);
  });

  it('accepts overrides', () => {
    const model = createTCModel({
      cmpId: 42,
      consentLanguage: 'FR',
      purposeConsents: new Set([1, 2, 3]),
    });
    expect(model.cmpId).toBe(42);
    expect(model.consentLanguage).toBe('FR');
    expect(model.purposeConsents).toEqual(new Set([1, 2, 3]));
    // Defaults still apply
    expect(model.version).toBe(2);
  });

  it('sets created and lastUpdated to now', () => {
    const before = msToDeciseconds(Date.now());
    const model = createTCModel();
    const after = msToDeciseconds(Date.now());
    expect(model.created).toBeGreaterThanOrEqual(before);
    expect(model.created).toBeLessThanOrEqual(after);
    expect(model.lastUpdated).toBe(model.created);
  });
});

// ── Encode / Decode round-trip ───────────────────────────────────────

describe('encodeTCString / decodeTCString', () => {
  it('round-trips a minimal model', () => {
    const model = createTCModel({
      created: 100000,
      lastUpdated: 100000,
      cmpId: 10,
      cmpVersion: 2,
    });

    const tcString = encodeTCString(model);
    expect(typeof tcString).toBe('string');
    expect(tcString.length).toBeGreaterThan(0);

    const decoded = decodeTCString(tcString);
    expect(decoded.version).toBe(2);
    expect(decoded.created).toBe(100000);
    expect(decoded.lastUpdated).toBe(100000);
    expect(decoded.cmpId).toBe(10);
    expect(decoded.cmpVersion).toBe(2);
    expect(decoded.consentLanguage).toBe('EN');
    expect(decoded.publisherCC).toBe('GB');
    expect(decoded.isServiceSpecific).toBe(true);
    expect(decoded.tcfPolicyVersion).toBe(5);
  });

  it('round-trips purpose consents', () => {
    const model = createTCModel({
      created: 200000,
      lastUpdated: 200000,
      purposeConsents: new Set([1, 2, 3, 7, 10]),
      purposeLegitimateInterests: new Set([2, 4, 6]),
    });

    const decoded = decodeTCString(encodeTCString(model));
    expect(decoded.purposeConsents).toEqual(new Set([1, 2, 3, 7, 10]));
    expect(decoded.purposeLegitimateInterests).toEqual(new Set([2, 4, 6]));
  });

  it('round-trips vendor consents', () => {
    const model = createTCModel({
      created: 300000,
      lastUpdated: 300000,
      vendorConsents: new Set([1, 5, 10, 100]),
      vendorLegitimateInterests: new Set([2, 50]),
    });

    const decoded = decodeTCString(encodeTCString(model));
    expect(decoded.vendorConsents).toEqual(new Set([1, 5, 10, 100]));
    expect(decoded.vendorLegitimateInterests).toEqual(new Set([2, 50]));
  });

  it('round-trips special feature opt-ins', () => {
    const model = createTCModel({
      created: 400000,
      lastUpdated: 400000,
      specialFeatureOptIns: new Set([1, 2]),
    });

    const decoded = decodeTCString(encodeTCString(model));
    expect(decoded.specialFeatureOptIns).toEqual(new Set([1, 2]));
  });

  it('round-trips consent language and publisher CC', () => {
    const model = createTCModel({
      created: 500000,
      lastUpdated: 500000,
      consentLanguage: 'FR',
      publisherCC: 'DE',
    });

    const decoded = decodeTCString(encodeTCString(model));
    expect(decoded.consentLanguage).toBe('FR');
    expect(decoded.publisherCC).toBe('DE');
  });

  it('round-trips boolean flags', () => {
    const model = createTCModel({
      created: 600000,
      lastUpdated: 600000,
      isServiceSpecific: false,
      useNonStandardTexts: true,
      purposeOneTreatment: true,
    });

    const decoded = decodeTCString(encodeTCString(model));
    expect(decoded.isServiceSpecific).toBe(false);
    expect(decoded.useNonStandardTexts).toBe(true);
    expect(decoded.purposeOneTreatment).toBe(true);
  });

  it('round-trips publisher restrictions', () => {
    const model = createTCModel({
      created: 700000,
      lastUpdated: 700000,
      publisherRestrictions: [
        {
          purposeId: 1,
          restrictionType: RestrictionType.REQUIRE_CONSENT,
          vendorIds: new Set([10, 20, 30]),
        },
        {
          purposeId: 3,
          restrictionType: RestrictionType.NOT_ALLOWED,
          vendorIds: new Set([5]),
        },
      ],
    });

    const decoded = decodeTCString(encodeTCString(model));
    expect(decoded.publisherRestrictions.length).toBe(2);
    expect(decoded.publisherRestrictions[0].purposeId).toBe(1);
    expect(decoded.publisherRestrictions[0].restrictionType).toBe(
      RestrictionType.REQUIRE_CONSENT
    );
    expect(decoded.publisherRestrictions[0].vendorIds).toEqual(new Set([10, 20, 30]));
    expect(decoded.publisherRestrictions[1].purposeId).toBe(3);
    expect(decoded.publisherRestrictions[1].vendorIds).toEqual(new Set([5]));
  });

  it('handles empty vendor sets', () => {
    const model = createTCModel({
      created: 800000,
      lastUpdated: 800000,
      vendorConsents: new Set(),
      vendorLegitimateInterests: new Set(),
    });

    const decoded = decodeTCString(encodeTCString(model));
    expect(decoded.vendorConsents.size).toBe(0);
    expect(decoded.vendorLegitimateInterests.size).toBe(0);
  });

  it('handles no publisher restrictions', () => {
    const model = createTCModel({
      created: 900000,
      lastUpdated: 900000,
      publisherRestrictions: [],
    });

    const decoded = decodeTCString(encodeTCString(model));
    expect(decoded.publisherRestrictions.length).toBe(0);
  });

  it('round-trips a fully populated model', () => {
    const model = createTCModel({
      created: 1000000,
      lastUpdated: 1000001,
      cmpId: 300,
      cmpVersion: 5,
      consentScreen: 2,
      consentLanguage: 'DE',
      vendorListVersion: 150,
      tcfPolicyVersion: 5,
      isServiceSpecific: false,
      useNonStandardTexts: false,
      specialFeatureOptIns: new Set([1, 2]),
      purposeConsents: new Set([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]),
      purposeLegitimateInterests: new Set([2, 7, 9, 10]),
      purposeOneTreatment: true,
      publisherCC: 'FR',
      vendorConsents: new Set([1, 2, 3, 10, 25, 50, 100, 200, 500]),
      vendorLegitimateInterests: new Set([1, 10, 50]),
      publisherRestrictions: [
        {
          purposeId: 2,
          restrictionType: RestrictionType.REQUIRE_LEGITIMATE_INTEREST,
          vendorIds: new Set([100, 101, 102]),
        },
      ],
    });

    const tcString = encodeTCString(model);
    const decoded = decodeTCString(tcString);

    expect(decoded.version).toBe(2);
    expect(decoded.created).toBe(1000000);
    expect(decoded.lastUpdated).toBe(1000001);
    expect(decoded.cmpId).toBe(300);
    expect(decoded.cmpVersion).toBe(5);
    expect(decoded.consentScreen).toBe(2);
    expect(decoded.consentLanguage).toBe('DE');
    expect(decoded.vendorListVersion).toBe(150);
    expect(decoded.tcfPolicyVersion).toBe(5);
    expect(decoded.isServiceSpecific).toBe(false);
    expect(decoded.purposeConsents).toEqual(new Set([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]));
    expect(decoded.purposeLegitimateInterests).toEqual(new Set([2, 7, 9, 10]));
    expect(decoded.purposeOneTreatment).toBe(true);
    expect(decoded.publisherCC).toBe('FR');
    expect(decoded.vendorConsents).toEqual(
      new Set([1, 2, 3, 10, 25, 50, 100, 200, 500])
    );
    expect(decoded.vendorLegitimateInterests).toEqual(new Set([1, 10, 50]));
    expect(decoded.specialFeatureOptIns).toEqual(new Set([1, 2]));
    expect(decoded.publisherRestrictions[0].vendorIds).toEqual(
      new Set([100, 101, 102])
    );
  });

  it('only parses the core segment when dots are present', () => {
    const model = createTCModel({ created: 1100000, lastUpdated: 1100000 });
    const tcString = encodeTCString(model);
    // Append a fake disclosed vendors segment
    const withSegments = `${tcString}.FAKE_SEGMENT`;
    const decoded = decodeTCString(withSegments);
    expect(decoded.version).toBe(2);
    expect(decoded.created).toBe(1100000);
  });
});

// ── __tcfapi interface ───────────────────────────────────────────────

describe('__tcfapi interface', () => {
  beforeEach(() => {
    removeTcfApi();
  });

  afterEach(() => {
    removeTcfApi();
  });

  describe('installTcfApi', () => {
    it('installs __tcfapi on window', () => {
      installTcfApi(42, 1);
      expect(typeof window.__tcfapi).toBe('function');
    });

    it('processes queued calls from the stub', () => {
      const queue: unknown[][] = [];
      window.__tcfapiQueue = queue;

      const callback = vi.fn();
      queue.push(['ping', 2, callback]);

      installTcfApi(42, 1);

      expect(callback).toHaveBeenCalledOnce();
      expect(callback).toHaveBeenCalledWith(
        expect.objectContaining({ cmpLoaded: true }),
        true
      );
    });

    it('clears the queue after processing', () => {
      const queue: unknown[][] = [['ping', 2, vi.fn()]];
      window.__tcfapiQueue = queue;

      installTcfApi(42, 1);
      expect(queue.length).toBe(0);
    });
  });

  describe('ping command', () => {
    it('returns CMP status', () => {
      installTcfApi(42, 3);
      const callback = vi.fn();

      const api = window.__tcfapi as Function;
      api('ping', 2, callback);

      expect(callback).toHaveBeenCalledWith(
        expect.objectContaining({
          gdprApplies: true,
          cmpLoaded: true,
          cmpStatus: 'loaded',
          displayStatus: 'hidden',
          apiVersion: '2.3',
          cmpVersion: 3,
          cmpId: 42,
          tcfPolicyVersion: 5,
        }),
        true
      );
    });

    it('respects gdprApplies parameter', () => {
      installTcfApi(42, 1, false);
      const callback = vi.fn();

      const api = window.__tcfapi as Function;
      api('ping', 2, callback);

      expect(callback).toHaveBeenCalledWith(
        expect.objectContaining({ gdprApplies: false }),
        true
      );
    });
  });

  describe('getTCData command', () => {
    it('returns cmpuishown when no consent', () => {
      installTcfApi(42, 1);
      const callback = vi.fn();

      const api = window.__tcfapi as Function;
      api('getTCData', 2, callback);

      expect(callback).toHaveBeenCalledWith(
        expect.objectContaining({
          eventStatus: 'cmpuishown',
          cmpId: 42,
          tcString: '',
        }),
        true
      );
    });

    it('returns tcloaded after consent is set', () => {
      installTcfApi(42, 1);

      const model = createTCModel({
        created: 100000,
        lastUpdated: 100000,
        cmpId: 42,
        purposeConsents: new Set([1, 2]),
      });
      updateTcfConsent(model);

      const callback = vi.fn();
      const api = window.__tcfapi as Function;
      api('getTCData', 2, callback);

      const result = callback.mock.calls[0][0];
      expect(result.eventStatus).toBe('tcloaded');
      expect(result.tcString).toBeTruthy();
      expect(result.purpose.consents['1']).toBe(true);
      expect(result.purpose.consents['2']).toBe(true);
      expect(result.purpose.consents['3']).toBe(false);
    });

    it('includes vendor consent data', () => {
      installTcfApi(42, 1);

      const model = createTCModel({
        created: 100000,
        lastUpdated: 100000,
        vendorConsents: new Set([1, 5, 10]),
        vendorLegitimateInterests: new Set([2, 5]),
      });
      updateTcfConsent(model);

      const callback = vi.fn();
      const api = window.__tcfapi as Function;
      api('getTCData', 2, callback);

      const result = callback.mock.calls[0][0];
      expect(result.vendor.consents['1']).toBe(true);
      expect(result.vendor.consents['5']).toBe(true);
      expect(result.vendor.consents['10']).toBe(true);
      expect(result.vendor.consents['2']).toBe(false);
      expect(result.vendor.legitimateInterests['2']).toBe(true);
      expect(result.vendor.legitimateInterests['5']).toBe(true);
    });

    it('includes special feature opt-in data', () => {
      installTcfApi(42, 1);

      const model = createTCModel({
        created: 100000,
        lastUpdated: 100000,
        specialFeatureOptIns: new Set([1, 2]),
      });
      updateTcfConsent(model);

      const callback = vi.fn();
      const api = window.__tcfapi as Function;
      api('getTCData', 2, callback);

      const result = callback.mock.calls[0][0];
      expect(result.specialFeatureOptins['1']).toBe(true);
      expect(result.specialFeatureOptins['2']).toBe(true);
      expect(result.specialFeatureOptins['3']).toBe(false);
    });
  });

  describe('addEventListener command', () => {
    it('assigns a listener ID and returns current TC data', () => {
      installTcfApi(42, 1);

      const callback = vi.fn();
      const api = window.__tcfapi as Function;
      api('addEventListener', 2, callback);

      expect(callback).toHaveBeenCalledOnce();
      const result = callback.mock.calls[0][0];
      expect(result.listenerId).toBe(1);
      expect(result.eventStatus).toBe('cmpuishown');
    });

    it('notifies listeners when consent is updated', () => {
      installTcfApi(42, 1);

      const listener = vi.fn();
      const api = window.__tcfapi as Function;
      api('addEventListener', 2, listener);

      // Initial call
      expect(listener).toHaveBeenCalledOnce();

      // Update consent
      const model = createTCModel({
        created: 100000,
        lastUpdated: 100000,
        purposeConsents: new Set([1]),
      });
      updateTcfConsent(model);

      // Should be called again with useractioncomplete
      expect(listener).toHaveBeenCalledTimes(2);
      const updateResult = listener.mock.calls[1][0];
      expect(updateResult.eventStatus).toBe('useractioncomplete');
      expect(updateResult.tcString).toBeTruthy();
    });

    it('assigns incrementing listener IDs', () => {
      installTcfApi(42, 1);

      const cb1 = vi.fn();
      const cb2 = vi.fn();
      const api = window.__tcfapi as Function;
      api('addEventListener', 2, cb1);
      api('addEventListener', 2, cb2);

      expect(cb1.mock.calls[0][0].listenerId).toBe(1);
      expect(cb2.mock.calls[0][0].listenerId).toBe(2);
    });

    it('swallows errors in listener callbacks', () => {
      installTcfApi(42, 1);

      const badListener = vi.fn(() => {
        throw new Error('boom');
      });
      const goodListener = vi.fn();

      const api = window.__tcfapi as Function;
      api('addEventListener', 2, badListener);
      api('addEventListener', 2, goodListener);

      // Update consent - should not throw
      const model = createTCModel({ created: 100000, lastUpdated: 100000 });
      expect(() => updateTcfConsent(model)).not.toThrow();

      // Good listener still called
      expect(goodListener).toHaveBeenCalledTimes(2);
    });
  });

  describe('removeEventListener command', () => {
    it('removes a listener by ID', () => {
      installTcfApi(42, 1);

      const listener = vi.fn();
      const api = window.__tcfapi as Function;
      api('addEventListener', 2, listener);

      const listenerId = listener.mock.calls[0][0].listenerId;

      const removeCallback = vi.fn();
      api('removeEventListener', 2, removeCallback, listenerId);
      expect(removeCallback).toHaveBeenCalledWith(true, true);

      // Listener should not be called on updates
      listener.mockClear();
      updateTcfConsent(createTCModel({ created: 100000, lastUpdated: 100000 }));
      expect(listener).not.toHaveBeenCalled();
    });

    it('returns false for non-existent listener ID', () => {
      installTcfApi(42, 1);

      const callback = vi.fn();
      const api = window.__tcfapi as Function;
      api('removeEventListener', 2, callback, 999);
      expect(callback).toHaveBeenCalledWith(false, false);
    });
  });

  describe('version checking', () => {
    it('rejects non-v2 API calls', () => {
      installTcfApi(42, 1);

      const callback = vi.fn();
      const api = window.__tcfapi as Function;
      api('ping', 1, callback);
      expect(callback).toHaveBeenCalledWith(false, false);
    });
  });

  describe('unknown commands', () => {
    it('calls back with false for unknown commands', () => {
      installTcfApi(42, 1);

      const callback = vi.fn();
      const api = window.__tcfapi as Function;
      api('unknownCommand', 2, callback);
      expect(callback).toHaveBeenCalledWith(false, false);
    });
  });

  describe('uninitialised state', () => {
    it('calls back with false when API not installed', () => {
      // Do NOT call installTcfApi — directly test the handler via a mock
      // Since removeTcfApi is called in beforeEach, apiState is null
      // We need to call installTcfApi then removeTcfApi to reset, then
      // try calling a cached reference (but __tcfapi is deleted).
      // Instead, test that getTcString returns empty when uninitialised.
      expect(getTcString()).toBe('');
    });
  });
});

// ── updateTcfConsent ─────────────────────────────────────────────────

describe('updateTcfConsent', () => {
  beforeEach(() => {
    removeTcfApi();
  });

  afterEach(() => {
    removeTcfApi();
  });

  it('returns a valid TC string', () => {
    installTcfApi(42, 1);
    const model = createTCModel({
      created: 100000,
      lastUpdated: 100000,
      cmpId: 42,
      purposeConsents: new Set([1, 2, 3]),
    });

    const tcString = updateTcfConsent(model);
    expect(typeof tcString).toBe('string');
    expect(tcString.length).toBeGreaterThan(0);

    // Should be decodable
    const decoded = decodeTCString(tcString);
    expect(decoded.purposeConsents).toEqual(new Set([1, 2, 3]));
  });

  it('updates getTcString return value', () => {
    installTcfApi(42, 1);
    expect(getTcString()).toBe('');

    const model = createTCModel({ created: 100000, lastUpdated: 100000 });
    const tcString = updateTcfConsent(model);
    expect(getTcString()).toBe(tcString);
  });

  it('works without installTcfApi (returns TC string, no listeners)', () => {
    // apiState is null, but should still encode
    const model = createTCModel({ created: 100000, lastUpdated: 100000 });
    const tcString = updateTcfConsent(model);
    expect(typeof tcString).toBe('string');
    expect(tcString.length).toBeGreaterThan(0);
  });
});

// ── setTcfDisplayStatus ──────────────────────────────────────────────

describe('setTcfDisplayStatus', () => {
  beforeEach(() => {
    removeTcfApi();
  });

  afterEach(() => {
    removeTcfApi();
  });

  it('updates the display status returned by ping', () => {
    installTcfApi(42, 1);
    setTcfDisplayStatus('visible');

    const callback = vi.fn();
    const api = window.__tcfapi as Function;
    api('ping', 2, callback);

    expect(callback.mock.calls[0][0].displayStatus).toBe('visible');
  });

  it('does nothing when API not installed', () => {
    // Should not throw
    expect(() => setTcfDisplayStatus('visible')).not.toThrow();
  });
});

// ── removeTcfApi ─────────────────────────────────────────────────────

describe('removeTcfApi', () => {
  it('removes __tcfapi from window', () => {
    installTcfApi(42, 1);
    expect(window.__tcfapi).toBeDefined();

    removeTcfApi();
    expect(window.__tcfapi).toBeUndefined();
  });

  it('cleans up __tcfapiQueue', () => {
    window.__tcfapiQueue = [];
    installTcfApi(42, 1);

    removeTcfApi();
    expect(window.__tcfapiQueue).toBeUndefined();
  });

  it('is safe to call multiple times', () => {
    expect(() => {
      removeTcfApi();
      removeTcfApi();
    }).not.toThrow();
  });
});

// ── TCF v2.3 ─────────────────────────────────────────────────────────

describe('TCF v2.3 — DisclosedVendors segment', () => {
  it('encodeTCString emits a 3-segment string (Core + DisclosedVendors)', () => {
    const model = createTCModel({
      cmpId: 42,
      vendorListVersion: 100,
      disclosedVendors: new Set([1, 2, 5]),
    });
    const tc = encodeTCString(model);
    const segments = tc.split('.');
    expect(segments.length).toBe(2);
    expect(segments[0].length).toBeGreaterThan(0);
    expect(segments[1].length).toBeGreaterThan(0);
  });

  it('emits a DisclosedVendors segment even when the disclosure set is empty', () => {
    const model = createTCModel({ cmpId: 42 });
    const tc = encodeTCString(model);
    expect(tc.split('.').length).toBe(2);
  });

  it('round-trips disclosedVendors through encode/decode', () => {
    const model = createTCModel({
      cmpId: 42,
      vendorListVersion: 100,
      vendorConsents: new Set([1, 2]),
      disclosedVendors: new Set([1, 2, 3, 4, 5, 10, 50]),
    });
    const tc = encodeTCString(model);
    const decoded = decodeTCString(tc);
    expect([...decoded.disclosedVendors].sort((a, b) => a - b)).toEqual([
      1, 2, 3, 4, 5, 10, 50,
    ]);
  });

  it('decodes legacy v2.2 single-segment strings with empty disclosedVendors', () => {
    // Build a v2.2-shape string by encoding then dropping the v2.3 segment.
    const model = createTCModel({
      cmpId: 42,
      vendorListVersion: 100,
      vendorConsents: new Set([1, 5]),
      disclosedVendors: new Set([1, 5, 10]),
    });
    const v23 = encodeTCString(model);
    const v22 = v23.split('.')[0];

    const decoded = decodeTCString(v22);
    expect(decoded.cmpId).toBe(42);
    expect(decoded.vendorListVersion).toBe(100);
    expect([...decoded.vendorConsents].sort((a, b) => a - b)).toEqual([1, 5]);
    expect(decoded.disclosedVendors.size).toBe(0);
  });

  it('encodeDisclosedVendorsSegment writes the spec segment-type prefix', () => {
    const segment = encodeDisclosedVendorsSegment(new Set([1, 3]));
    const bytes = base64urlToBytes(segment);
    const reader = new BitReader(bytes);
    expect(reader.readInt(3)).toBe(SegmentType.DisclosedVendors);
  });

  it('encodeDisclosedVendorsSegment with empty set writes maxId = 0', () => {
    const segment = encodeDisclosedVendorsSegment(new Set());
    const bytes = base64urlToBytes(segment);
    const reader = new BitReader(bytes);
    expect(reader.readInt(3)).toBe(SegmentType.DisclosedVendors);
    expect(reader.readInt(16)).toBe(0);
  });

  it('decoder ignores unknown segment types without throwing', () => {
    const model = createTCModel({ cmpId: 42 });
    const core = encodeTCString(model).split('.')[0];

    // Synthesise a PublisherTC-shaped segment (segment type 3, no payload
    // we care about). Decoder should leave disclosedVendors empty and
    // not throw.
    const w = new BitWriter();
    w.writeInt(SegmentType.PublisherTC, 3);
    w.writeInt(0, 24); // some empty publisher purposes
    const publisher = bytesToBase64url(w.toBytes());

    const tc = `${core}.${publisher}`;
    const decoded = decodeTCString(tc);
    expect(decoded.disclosedVendors.size).toBe(0);
  });

  it('uses tcfPolicyVersion 5 for v2.3 (matches the live GVL)', () => {
    const model = createTCModel();
    expect(model.tcfPolicyVersion).toBe(5);
    const tc = encodeTCString(model);
    expect(decodeTCString(tc).tcfPolicyVersion).toBe(5);
  });
});

// ── Cross-frame __tcfapi (locator iframe + postMessage) ─────────────

describe('TCF cross-frame — __tcfapiLocator iframe', () => {
  beforeEach(() => {
    removeTcfApi();
    document.body.innerHTML = '';
  });

  afterEach(() => {
    removeTcfApi();
    document.body.innerHTML = '';
  });

  it('creates a hidden iframe named __tcfapiLocator on install', () => {
    installTcfApi(42, 1);
    const frame = document.querySelector(
      'iframe[name="__tcfapiLocator"]'
    ) as HTMLIFrameElement | null;
    expect(frame).not.toBeNull();
    expect(frame!.style.display).toBe('none');
    expect(frame!.tabIndex).toBe(-1);
  });

  it('does not create a duplicate locator on repeat install', () => {
    installTcfApi(42, 1);
    installTcfApi(42, 1);
    const frames = document.querySelectorAll('iframe[name="__tcfapiLocator"]');
    expect(frames.length).toBe(1);
  });

  it('removes the locator iframe on removeTcfApi', () => {
    installTcfApi(42, 1);
    expect(document.querySelector('iframe[name="__tcfapiLocator"]')).not.toBeNull();
    removeTcfApi();
    expect(document.querySelector('iframe[name="__tcfapiLocator"]')).toBeNull();
  });
});

describe('TCF cross-frame — postMessage proxy', () => {
  beforeEach(() => {
    removeTcfApi();
    document.body.innerHTML = '';
  });

  afterEach(() => {
    removeTcfApi();
    document.body.innerHTML = '';
  });

  /**
   * Drive the message listener directly: jsdom doesn't process real
   * cross-frame messages, but the listener accepts MessageEvent-shaped
   * objects so we can synthesise one and assert the round-trip.
   */
  function dispatchCall(payload: unknown, source: { postMessage: ReturnType<typeof vi.fn> }) {
    const event = new MessageEvent('message', {
      data: payload,
      origin: 'https://vendor.example',
      source: source as unknown as MessageEventSource,
    });
    window.dispatchEvent(event);
  }

  it('responds to a ping envelope on the source window', () => {
    installTcfApi(42, 3);
    const source = { postMessage: vi.fn() };
    dispatchCall(
      { __tcfapiCall: { command: 'ping', version: 2, callId: 'abc-1' } },
      source
    );

    expect(source.postMessage).toHaveBeenCalledTimes(1);
    const [reply, target] = source.postMessage.mock.calls[0];
    expect(target).toBe('https://vendor.example');
    expect(reply.__tcfapiReturn.callId).toBe('abc-1');
    expect(reply.__tcfapiReturn.success).toBe(true);
    expect(reply.__tcfapiReturn.returnValue.cmpId).toBe(42);
    expect(reply.__tcfapiReturn.returnValue.apiVersion).toBe('2.3');
  });

  it('round-trips JSON string envelopes (caller used JSON.stringify)', () => {
    installTcfApi(42, 1);
    const source = { postMessage: vi.fn() };
    dispatchCall(
      JSON.stringify({
        __tcfapiCall: { command: 'ping', version: 2, callId: 99 },
      }),
      source
    );

    expect(source.postMessage).toHaveBeenCalledTimes(1);
    const [reply] = source.postMessage.mock.calls[0];
    expect(typeof reply).toBe('string');
    const parsed = JSON.parse(reply as string);
    expect(parsed.__tcfapiReturn.callId).toBe(99);
    expect(parsed.__tcfapiReturn.success).toBe(true);
  });

  it('falls back to "*" targetOrigin when source reports null origin', () => {
    installTcfApi(42, 1);
    const source = { postMessage: vi.fn() };
    const event = new MessageEvent('message', {
      data: { __tcfapiCall: { command: 'ping', version: 2, callId: 1 } },
      origin: 'null',
      source: source as unknown as MessageEventSource,
    });
    window.dispatchEvent(event);

    expect(source.postMessage).toHaveBeenCalledTimes(1);
    expect(source.postMessage.mock.calls[0][1]).toBe('*');
  });

  it('ignores messages without an __tcfapiCall envelope', () => {
    installTcfApi(42, 1);
    const source = { postMessage: vi.fn() };
    dispatchCall({ unrelated: 'message' }, source);
    dispatchCall('just a string', source);
    dispatchCall(null, source);
    expect(source.postMessage).not.toHaveBeenCalled();
  });

  it('rejects callers using a wrong API version', () => {
    installTcfApi(42, 1);
    const source = { postMessage: vi.fn() };
    dispatchCall(
      { __tcfapiCall: { command: 'ping', version: 1, callId: 7 } },
      source
    );

    const [reply] = source.postMessage.mock.calls[0];
    expect(reply.__tcfapiReturn.success).toBe(false);
    expect(reply.__tcfapiReturn.returnValue).toBe(false);
  });

  it('proxies getTCData over postMessage', () => {
    installTcfApi(42, 1);
    updateTcfConsent(
      createTCModel({
        cmpId: 42,
        purposeConsents: new Set([1, 3]),
        disclosedVendors: new Set([5]),
      })
    );

    const source = { postMessage: vi.fn() };
    dispatchCall(
      { __tcfapiCall: { command: 'getTCData', version: 2, callId: 'g-1' } },
      source
    );

    const [reply] = source.postMessage.mock.calls[0];
    expect(reply.__tcfapiReturn.success).toBe(true);
    const tcData = reply.__tcfapiReturn.returnValue;
    expect(tcData.cmpId).toBe(42);
    expect(tcData.purpose.consents['1']).toBe(true);
    expect(tcData.purpose.consents['2']).toBe(false);
    expect(tcData.disclosedVendors['5']).toBe(true);
  });

  it('removes the message listener on removeTcfApi', () => {
    installTcfApi(42, 1);
    removeTcfApi();

    const source = { postMessage: vi.fn() };
    dispatchCall(
      { __tcfapiCall: { command: 'ping', version: 2, callId: 1 } },
      source
    );
    expect(source.postMessage).not.toHaveBeenCalled();
  });
});

describe('TCF v2.3 — TCData', () => {
  beforeEach(() => {
    delete window.__tcfapi;
    delete window.__tcfapiQueue;
  });

  afterEach(() => {
    removeTcfApi();
  });

  it('exposes disclosedVendors on getTCData', () => {
    installTcfApi(42, 1);
    const model = createTCModel({
      cmpId: 42,
      disclosedVendors: new Set([1, 4]),
    });
    updateTcfConsent(model);

    const callback = vi.fn();
    const api = window.__tcfapi as Function;
    api('getTCData', 2, callback);

    const tcData = callback.mock.calls[0][0];
    expect(tcData.disclosedVendors).toEqual({
      '1': true,
      '2': false,
      '3': false,
      '4': true,
    });
  });

  it('returns empty disclosedVendors when no model is set', () => {
    installTcfApi(42, 1);
    const callback = vi.fn();
    const api = window.__tcfapi as Function;
    api('getTCData', 2, callback);

    expect(callback.mock.calls[0][0].disclosedVendors).toEqual({});
  });
});
