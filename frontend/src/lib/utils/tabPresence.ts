/**
 * Same-browser tab-presence tracker for the wizard.
 *
 * Detects when more than one tab of the same browser has the same
 * `(userId, entryId)` open. Used to warn the user before a save —
 * sibling tabs can save out-of-sync edits and last-write-wins on the
 * server. **Same-browser only** (localStorage is per-origin-per-
 * browser). Cross-device conflicts are handled by the backend
 * lifecycle guard + LifecycleConflictModal.
 *
 * Mechanism:
 *   - A tab ID is generated once per tab and stashed in sessionStorage.
 *     Refresh keeps the same ID (same tab); duplicate-tab gets a fresh
 *     ID; closing drops it. Matches user intuition.
 *   - Each registered context maintains an entry in a localStorage key
 *     `predictor_open_tabs_{userId}_{entryId}` shaped as
 *     `{ [tabId]: timestampMs }`. Heartbeat every 5s rewrites the
 *     entry; readers ignore entries older than 15s (stale tabs that
 *     crashed without firing `beforeunload`).
 *   - A `storage` listener keeps the reactive count fresh when a
 *     sibling tab writes.
 *
 * The exported `otherTabCount` readable store reflects the number of
 * sibling tabs (excluding self) for the most-recently-registered
 * context. Re-registering with a new context clears the previous one.
 */

import { writable, type Readable } from 'svelte/store';
import { browser } from '$app/environment';

const HEARTBEAT_MS = 5_000;
const FRESHNESS_WINDOW_MS = 15_000;
const TAB_ID_SESSION_KEY = 'predictor_tab_id';

type PresenceMap = Record<string, number>;

const _otherTabCount = writable<number>(0);
export const otherTabCount: Readable<number> = _otherTabCount;

function getTabId(): string {
	if (!browser) return '';
	let id = sessionStorage.getItem(TAB_ID_SESSION_KEY);
	if (!id) {
		// crypto.randomUUID is supported in all evergreen browsers; the
		// fallback covers older Safari and any constrained iframe.
		id =
			typeof crypto !== 'undefined' && 'randomUUID' in crypto
				? crypto.randomUUID()
				: `tab-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
		sessionStorage.setItem(TAB_ID_SESSION_KEY, id);
	}
	return id;
}

function presenceKey(userId: string, entryId: string): string {
	return `predictor_open_tabs_${userId}_${entryId}`;
}

function readPresence(key: string): PresenceMap {
	if (!browser) return {};
	try {
		const raw = localStorage.getItem(key);
		if (!raw) return {};
		const parsed = JSON.parse(raw);
		if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
			return parsed as PresenceMap;
		}
	} catch {
		// fall through
	}
	return {};
}

function writePresence(key: string, map: PresenceMap): void {
	if (!browser) return;
	try {
		if (Object.keys(map).length === 0) {
			localStorage.removeItem(key);
		} else {
			localStorage.setItem(key, JSON.stringify(map));
		}
	} catch {
		// Quota / disabled — silently degrade. The worst case is a stale
		// banner, not data loss.
	}
}

/**
 * Recompute the count of OTHER tabs for the currently-active context
 * and publish it. Filters out stale entries (older than the freshness
 * window) and the current tab.
 */
function recomputeCount(key: string, selfTabId: string): void {
	const now = Date.now();
	const map = readPresence(key);
	let other = 0;
	for (const [tabId, ts] of Object.entries(map)) {
		if (tabId === selfTabId) continue;
		if (typeof ts !== 'number') continue;
		if (now - ts > FRESHNESS_WINDOW_MS) continue;
		other += 1;
	}
	_otherTabCount.set(other);
}

// Module-level registration state. We only support ONE active context
// at a time (the wizard's current entry). Switching contexts tears down
// the previous registration cleanly.
let activeKey: string | null = null;
let activeTabId: string | null = null;
let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
let storageListener: ((e: StorageEvent) => void) | null = null;
let unloadListener: (() => void) | null = null;

function clearActive(): void {
	if (heartbeatTimer !== null) {
		clearInterval(heartbeatTimer);
		heartbeatTimer = null;
	}
	if (storageListener && browser) {
		window.removeEventListener('storage', storageListener);
		storageListener = null;
	}
	if (unloadListener && browser) {
		window.removeEventListener('beforeunload', unloadListener);
		unloadListener = null;
	}
	if (activeKey && activeTabId) {
		const map = readPresence(activeKey);
		delete map[activeTabId];
		writePresence(activeKey, map);
	}
	activeKey = null;
	activeTabId = null;
	_otherTabCount.set(0);
}

/**
 * Register this tab as present on `(userId, entryId)`. Starts the
 * heartbeat + storage listener and updates the `otherTabCount` store.
 * Re-registering with a different context tears down the previous one
 * first.
 */
export function registerTabPresence(userId: string, entryId: string): void {
	if (!browser) return;
	const key = presenceKey(userId, entryId);
	if (activeKey === key) return; // already registered for this context

	if (activeKey !== null) clearActive();

	const tabId = getTabId();
	activeKey = key;
	activeTabId = tabId;

	// Write the initial heartbeat immediately so the count reflects us.
	const map = readPresence(key);
	map[tabId] = Date.now();
	writePresence(key, map);
	recomputeCount(key, tabId);

	// Periodic heartbeat — refresh our timestamp and recompute count
	// (so stale sibling entries age out client-side without depending on
	// receiving a storage event).
	heartbeatTimer = setInterval(() => {
		if (!activeKey || !activeTabId) return;
		const m = readPresence(activeKey);
		m[activeTabId] = Date.now();
		writePresence(activeKey, m);
		recomputeCount(activeKey, activeTabId);
	}, HEARTBEAT_MS);

	// React to sibling tabs' writes.
	storageListener = (e: StorageEvent) => {
		if (!activeKey || !activeTabId) return;
		if (e.key !== activeKey) return;
		recomputeCount(activeKey, activeTabId);
	};
	window.addEventListener('storage', storageListener);

	// Best-effort cleanup on tab close.
	unloadListener = () => {
		if (!activeKey || !activeTabId) return;
		const m = readPresence(activeKey);
		delete m[activeTabId];
		writePresence(activeKey, m);
	};
	window.addEventListener('beforeunload', unloadListener);
}

/**
 * Tear down presence for `(userId, entryId)`. Called by the wizard
 * when the active entry changes — pair with `registerTabPresence` for
 * the new context.
 */
export function unregisterTabPresence(userId: string, entryId: string): void {
	if (!browser) return;
	const key = presenceKey(userId, entryId);
	if (activeKey !== key) return;
	clearActive();
}
