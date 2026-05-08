/**
 * IAB GPP CMP API — `__gpp()` global interface.
 *
 * Implements the client-side JavaScript API that ad tech vendors call to
 * retrieve the user's consent state under the Global Privacy Platform.
 * Analogous to `__tcfapi()` for TCF v2.3.
 *
 * Supported commands: ping, getGPPData, getSection, hasSection,
 * addEventListener, removeEventListener.
 *
 * @see https://github.com/InteractiveAdvertisingBureau/Global-Privacy-Platform/blob/main/Core/CMP%20API%20Specification.md
 */

import {
  type GppHeader,
  type GppString,
  type SectionData,
  type SectionDef,
  SECTION_REGISTRY,
  encodeGppString,
} from './gpp';

// ── Types ────────────────────────────────────────────────────────────

declare global {
  interface Window {
    __gpp?: GppApiFunction;
    __gppQueue?: GppQueueEntry[];
  }
}

/** Signature of the __gpp() global function. */
export type GppApiFunction = (
  command: string,
  callback: GppApiCallback,
  parameter?: unknown,
) => void;

/** Callback passed to __gpp() by callers. */
export type GppApiCallback = (data: unknown, success: boolean) => void;

/** A queued __gpp() call (from the stub). */
export type GppQueueEntry = [string, GppApiCallback, unknown?];

/** Return type for the 'ping' command. */
export interface GppPingReturn {
  gppVersion: string;
  cmpStatus: 'loaded' | 'stub';
  cmpDisplayStatus: 'visible' | 'hidden' | 'disabled';
  signalStatus: 'ready' | 'not ready';
  supportedAPIs: string[];
  cmpId: number;
  /** The current GPP string, or empty if not yet resolved. */
  gppString: string;
  /** Section IDs that apply to the current transaction. */
  applicableSections: number[];
}

/** Return type for the 'getGPPData' command. */
export interface GppData {
  /** The encoded GPP string. */
  gppString: string;
  /** Section IDs applicable to the current transaction. */
  applicableSections: number[];
  /** Parsed section data keyed by section ID. */
  parsedSections: Record<number, SectionData>;
}

/** Event data sent to registered listeners. */
export interface GppEventData {
  eventName: string;
  listenerId: number;
  data: GppData | GppPingReturn | boolean;
  pingData: GppPingReturn;
}

// ── Internal state ───────────────────────────────────────────────────

interface GppApiState {
  cmpId: number;
  gppString: string;
  header: GppHeader | null;
  sections: Map<number, SectionData>;
  supportedAPIs: string[];
  signalStatus: 'ready' | 'not ready';
  displayStatus: 'visible' | 'hidden' | 'disabled';
  listeners: Map<number, GppApiCallback>;
  nextListenerId: number;
}

let apiState: GppApiState | null = null;

// ── Ping builder ─────────────────────────────────────────────────────

function buildPingReturn(state: GppApiState): GppPingReturn {
  return {
    gppVersion: '1.1',
    cmpStatus: 'loaded',
    cmpDisplayStatus: state.displayStatus,
    signalStatus: state.signalStatus,
    supportedAPIs: state.supportedAPIs,
    cmpId: state.cmpId,
    gppString: state.gppString,
    applicableSections: state.header?.applicableSections ?? [],
  };
}

function buildGppData(state: GppApiState): GppData {
  const parsedSections: Record<number, SectionData> = {};
  state.sections.forEach((data, id) => {
    parsedSections[id] = data;
  });

  return {
    gppString: state.gppString,
    applicableSections: state.header?.applicableSections ?? [],
    parsedSections,
  };
}

// ── Command handler ──────────────────────────────────────────────────

function gppApiHandler(
  command: string,
  callback: GppApiCallback,
  parameter?: unknown,
): void {
  if (!apiState) {
    callback(false, false);
    return;
  }

  switch (command) {
    case 'ping': {
      callback(buildPingReturn(apiState), true);
      break;
    }

    case 'getGPPData': {
      callback(buildGppData(apiState), true);
      break;
    }

    case 'getSection': {
      const prefix = parameter as string;
      if (!prefix) {
        callback(null, false);
        return;
      }
      // Find section by API prefix
      let found = false;
      for (const [id, def] of SECTION_REGISTRY.entries()) {
        if (def.apiPrefix === prefix && apiState.sections.has(id)) {
          callback(apiState.sections.get(id)!, true);
          found = true;
          break;
        }
      }
      if (!found) {
        callback(null, false);
      }
      break;
    }

    case 'hasSection': {
      const prefix = parameter as string;
      if (!prefix) {
        callback(false, true);
        return;
      }
      let has = false;
      for (const [id, def] of SECTION_REGISTRY.entries()) {
        if (def.apiPrefix === prefix && apiState.sections.has(id)) {
          has = true;
          break;
        }
      }
      callback(has, true);
      break;
    }

    case 'addEventListener': {
      const listenerId = apiState.nextListenerId++;
      apiState.listeners.set(listenerId, callback);
      // Immediately notify with current state
      const eventData: GppEventData = {
        eventName: 'listenerRegistered',
        listenerId,
        data: buildGppData(apiState),
        pingData: buildPingReturn(apiState),
      };
      try {
        callback(eventData, true);
      } catch {
        // Swallow listener errors during initial notification
      }
      break;
    }

    case 'removeEventListener': {
      const id = parameter as number;
      const removed = apiState.listeners.delete(id);
      callback(removed, removed);
      break;
    }

    default:
      callback(false, false);
  }
}

// ── Queue processing ─────────────────────────────────────────────────

/** Process any queued __gpp() calls from the stub installed by the loader. */
function processQueuedCalls(): void {
  if (typeof window === 'undefined') return;

  const queue = window.__gppQueue;
  if (Array.isArray(queue)) {
    for (const entry of queue) {
      gppApiHandler(entry[0], entry[1], entry[2]);
    }
    queue.length = 0;
  }
}

// ── Public API ───────────────────────────────────────────────────────

/**
 * Install the __gpp() global function and process any queued calls.
 *
 * @param cmpId Registered CMP ID.
 * @param supportedAPIs List of supported API prefixes (e.g. ['usnat', 'usca']).
 */
export function installGppApi(
  cmpId: number,
  supportedAPIs: string[] = [],
): void {
  apiState = {
    cmpId,
    gppString: '',
    header: null,
    sections: new Map(),
    supportedAPIs,
    signalStatus: 'not ready',
    displayStatus: 'hidden',
    listeners: new Map(),
    nextListenerId: 1,
  };

  if (typeof window !== 'undefined') {
    window.__gpp = gppApiHandler;
  }

  processQueuedCalls();
}

/** Remove the __gpp() global function and clear state. */
export function removeGppApi(): void {
  if (typeof window !== 'undefined') {
    delete window.__gpp;
    delete window.__gppQueue;
  }
  apiState = null;
}

/**
 * Update the GPP consent state and notify all listeners.
 *
 * @param gpp The full GPP string data to set.
 * @returns The encoded GPP string.
 */
export function updateGppConsent(gpp: GppString): string {
  const gppString = encodeGppString(gpp);

  if (apiState) {
    apiState.gppString = gppString;
    apiState.header = gpp.header;
    apiState.sections = new Map<number, SectionData>();

    // Copy section data (just the data, not the gpcSubsection)
    for (const [id, section] of gpp.sections.entries()) {
      apiState.sections.set(id, section.data);
    }

    apiState.signalStatus = 'ready';
    apiState.displayStatus = 'hidden';

    // Notify all listeners
    const ping = buildPingReturn(apiState);
    apiState.listeners.forEach((callback, listenerId) => {
      const eventData: GppEventData = {
        eventName: 'signalStatus',
        listenerId,
        data: buildGppData(apiState!),
        pingData: ping,
      };
      try {
        callback(eventData, true);
      } catch {
        // Swallow listener errors
      }
    });
  }

  return gppString;
}

/** Set the display status (visible when banner is shown). */
export function setGppDisplayStatus(status: 'visible' | 'hidden' | 'disabled'): void {
  if (apiState) {
    apiState.displayStatus = status;
  }
}

/** Set the signal status. */
export function setGppSignalStatus(status: 'ready' | 'not ready'): void {
  if (apiState) {
    apiState.signalStatus = status;
  }
}

/** Get the current GPP string (empty if no consent yet). */
export function getGppString(): string {
  return apiState?.gppString ?? '';
}

/**
 * Check whether the GPP API is currently installed.
 * Useful for conditional logic in the banner.
 */
export function isGppApiInstalled(): boolean {
  return apiState !== null;
}
