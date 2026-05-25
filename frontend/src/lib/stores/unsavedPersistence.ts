/**
 * Silent localStorage mirror for unsaved prediction drafts.
 *
 * - Subscribes to the three unsaved stores and debounce-writes envelopes.
 * - Hydrates on mount; drops kicked-off match entries and locked-phase brackets.
 * - Listens for `storage` events so multiple tabs of the same user stay in sync.
 * - Per-key dedup cache breaks the cross-tab write/echo loop.
 *
 * Keys are scoped to `(userId, entryId)`. Switching active entry tears
 * down the previous subscriber set and registers a fresh one — drafts
 * never bleed across entries.
 */

import { writable, type Readable, type Unsubscriber } from 'svelte/store';
import { browser } from '$app/environment';
import {
	unsavedChanges,
	unsavedBracketPrediction,
	unsavedPhase2BracketPrediction,
	fetchMatchPredictions,
	fetchBracketPredictions,
	fetchPhase2BracketPredictions,
	type UnsavedPrediction
} from '$stores/predictions';
import type { BracketPrediction, FixturesByGroup } from '$types';
import { debounce } from '$lib/utils/debounce';

const CURRENT_VERSION = 1;
const DEBOUNCE_MS = 300;

type MatchesData = Record<string, UnsavedPrediction>;

interface Envelope<T> {
	v: number;
	savedAt: number;
	data: T;
}

const _lastLocalSave = writable<Date | null>(null);
export const lastLocalSave: Readable<Date | null> = _lastLocalSave;

// Tracks live subscriber sets keyed by `${userId}|${entryId}` so we can
// tear down cleanly when the active entry changes or the user logs out.
const subscribers = new Map<string, Unsubscriber[]>();

function contextKey(userId: string, entryId: string): string {
	return `${userId}|${entryId}`;
}

function keyMatches(userId: string, entryId: string): string {
	return `predictor_unsaved_${userId}_${entryId}_matches`;
}
function keyP1(userId: string, entryId: string): string {
	return `predictor_unsaved_${userId}_${entryId}_bracket_phase1`;
}
function keyP2(userId: string, entryId: string): string {
	return `predictor_unsaved_${userId}_${entryId}_bracket_phase2`;
}

/** Prefix of every key written by the current schema for a `(userId, entryId)` pair. */
function userEntryKeyPrefix(userId: string, entryId: string): string {
	return `predictor_unsaved_${userId}_${entryId}_`;
}

function safeParse<T>(raw: string): Envelope<T> | null {
	try {
		const parsed = JSON.parse(raw);
		if (parsed && typeof parsed === 'object' && 'v' in parsed && 'data' in parsed) {
			return parsed as Envelope<T>;
		}
	} catch {
		// fall through
	}
	return null;
}

function readEnvelope<T>(key: string): Envelope<T> | null {
	if (!browser) return null;
	const raw = localStorage.getItem(key);
	if (!raw) return null;
	const env = safeParse<T>(raw);
	if (!env || env.v !== CURRENT_VERSION) {
		localStorage.removeItem(key);
		return null;
	}
	return env;
}

function isEmpty(data: unknown): boolean {
	if (data === null || data === undefined) return true;
	if (typeof data === 'object' && Object.keys(data as object).length === 0) return true;
	return false;
}

/**
 * Drop any legacy `predictor_unsaved_{userId}_{type}` keys (no entry
 * segment). Drafts are local-only — if we can't tell which entry they
 * belonged to, the safer move is to discard them rather than guess.
 */
function discardLegacyKeys(userId: string): void {
	if (!browser) return;
	const legacyPrefix = `predictor_unsaved_${userId}_`;
	const legacySuffixes = ['matches', 'bracket_phase1', 'bracket_phase2'];
	for (const suffix of legacySuffixes) {
		const exactLegacy = `${legacyPrefix}${suffix}`;
		try {
			localStorage.removeItem(exactLegacy);
		} catch {
			// no-op
		}
	}
}

export function initPersistence(userId: string, entryId: string): void {
	if (!browser) return;
	const ctx = contextKey(userId, entryId);
	if (subscribers.has(ctx)) return;

	// Per-key dedup cache. Stores JSON.stringify(data) so identical follow-ups
	// (including echoes from cross-tab `storage` events) don't bounce-write.
	const lastWritten: { matches?: string; p1?: string; p2?: string } = {};

	function writeOrRemove(key: string, data: unknown): void {
		try {
			if (isEmpty(data)) {
				localStorage.removeItem(key);
			} else {
				const envelope: Envelope<unknown> = {
					v: CURRENT_VERSION,
					savedAt: Date.now(),
					data
				};
				localStorage.setItem(key, JSON.stringify(envelope));
			}
			_lastLocalSave.set(new Date());
		} catch {
			// Quota exceeded or storage unavailable — silently degrade.
		}
	}

	const writeMatches = debounce((data: MatchesData) => {
		writeOrRemove(keyMatches(userId, entryId), data);
	}, DEBOUNCE_MS);

	const writeP1 = debounce((data: BracketPrediction | null) => {
		writeOrRemove(keyP1(userId, entryId), data);
	}, DEBOUNCE_MS);

	const writeP2 = debounce((data: BracketPrediction | null) => {
		writeOrRemove(keyP2(userId, entryId), data);
	}, DEBOUNCE_MS);

	const subs: Unsubscriber[] = [];

	subs.push(
		unsavedChanges.subscribe((changes) => {
			const stringified = JSON.stringify(changes);
			if (lastWritten.matches === stringified) return;
			lastWritten.matches = stringified;
			writeMatches(changes);
		})
	);

	subs.push(
		unsavedBracketPrediction.subscribe((bracket) => {
			const stringified = JSON.stringify(bracket);
			if (lastWritten.p1 === stringified) return;
			lastWritten.p1 = stringified;
			writeP1(bracket);
		})
	);

	subs.push(
		unsavedPhase2BracketPrediction.subscribe((bracket) => {
			const stringified = JSON.stringify(bracket);
			if (lastWritten.p2 === stringified) return;
			lastWritten.p2 = stringified;
			writeP2(bracket);
		})
	);

	function onStorage(e: StorageEvent) {
		if (!e.key || !e.key.startsWith(userEntryKeyPrefix(userId, entryId))) return;

		const env = e.newValue ? safeParse<unknown>(e.newValue) : null;
		const data = env && env.v === CURRENT_VERSION ? env.data : null;

		// A removed key means the other tab either Saved (committed to the
		// server) or Cleared. Either way, this tab's server-state mirror may
		// be stale, so refetch it after applying the unsaved-store update.
		const remoteCommitted = e.newValue === null;

		// Prime the cache with the same shape the local subscriber will compute
		// after .set(), so the resulting subscription fire skips the bounce-write.
		if (e.key === keyMatches(userId, entryId)) {
			const next: MatchesData = (data as MatchesData) ?? {};
			lastWritten.matches = JSON.stringify(next);
			unsavedChanges.set(next);
			if (remoteCommitted) void fetchMatchPredictions();
		} else if (e.key === keyP1(userId, entryId)) {
			const next: BracketPrediction | null = (data as BracketPrediction) ?? null;
			lastWritten.p1 = JSON.stringify(next);
			unsavedBracketPrediction.set(next);
			if (remoteCommitted) void fetchBracketPredictions();
		} else if (e.key === keyP2(userId, entryId)) {
			const next: BracketPrediction | null = (data as BracketPrediction) ?? null;
			lastWritten.p2 = JSON.stringify(next);
			unsavedPhase2BracketPrediction.set(next);
			if (remoteCommitted) void fetchPhase2BracketPredictions();
		}
	}

	window.addEventListener('storage', onStorage);
	subs.push(() => window.removeEventListener('storage', onStorage));
	subs.push(() => {
		writeMatches.cancel();
		writeP1.cancel();
		writeP2.cancel();
	});

	subscribers.set(ctx, subs);
}

/**
 * Tear down the subscriber set for one `(userId, entryId)` pair. Called
 * by the wizard when the active entry changes — the new entry then calls
 * `initPersistence` with its own context.
 */
export function teardownPersistence(userId: string, entryId: string): void {
	const ctx = contextKey(userId, entryId);
	const subs = subscribers.get(ctx);
	if (subs) {
		for (const unsub of subs) unsub();
		subscribers.delete(ctx);
	}
}

export function hydrateFromStorage(
	userId: string,
	entryId: string,
	groupFixtures: FixturesByGroup[],
	isPhase1Locked: boolean,
	isPhase2BracketLocked: boolean
): {
	matchCount: number;
	bracketPhase1Restored: boolean;
	bracketPhase2Restored: boolean;
} | null {
	if (!browser) return null;

	// One-time cleanup — drafts saved before Task E (no entry segment)
	// can't be safely reassigned, so drop them.
	discardLegacyKeys(userId);

	const result = {
		matchCount: 0,
		bracketPhase1Restored: false,
		bracketPhase2Restored: false
	};

	// --- Match scores: drop kicked-off fixtures ---
	const matchesEnv = readEnvelope<MatchesData>(keyMatches(userId, entryId));
	if (matchesEnv) {
		const lockedIds = new Set<string>();
		for (const group of groupFixtures) {
			for (const fixture of group.fixtures) {
				if (fixture.is_locked) lockedIds.add(fixture.id);
			}
		}
		const survivors: MatchesData = {};
		for (const [fixtureId, scores] of Object.entries(matchesEnv.data)) {
			if (!lockedIds.has(fixtureId)) survivors[fixtureId] = scores;
		}
		const survivorCount = Object.keys(survivors).length;
		if (survivorCount > 0) {
			unsavedChanges.set(survivors);
			result.matchCount = survivorCount;
		}
		// If everything was kicked off, leave the key in place — the persistence
		// subscriber will overwrite/remove on the next store change. (Re-saving
		// here would cause a redundant write before any user action.)
	}

	// --- Phase 1 bracket: drop if phase is locked ---
	if (isPhase1Locked) {
		if (browser) localStorage.removeItem(keyP1(userId, entryId));
	} else {
		const p1Env = readEnvelope<BracketPrediction>(keyP1(userId, entryId));
		if (p1Env) {
			unsavedBracketPrediction.set(p1Env.data);
			result.bracketPhase1Restored = true;
		}
	}

	// --- Phase 2 bracket: drop if phase is locked ---
	if (isPhase2BracketLocked) {
		if (browser) localStorage.removeItem(keyP2(userId, entryId));
	} else {
		const p2Env = readEnvelope<BracketPrediction>(keyP2(userId, entryId));
		if (p2Env) {
			unsavedPhase2BracketPrediction.set(p2Env.data);
			result.bracketPhase2Restored = true;
		}
	}

	if (
		result.matchCount === 0 &&
		!result.bracketPhase1Restored &&
		!result.bracketPhase2Restored
	) {
		return null;
	}
	return result;
}

/**
 * Wipe every persisted draft key for this user across ALL entries.
 * Called on logout — we walk localStorage looking for the user's key
 * prefix rather than tracking entry ids.
 */
export function clearAllForUser(userId: string): void {
	if (!browser) return;
	const legacyPrefix = `predictor_unsaved_${userId}_`;
	// Active-entry key is exact-match (no competition segment after Task F.x);
	// we keep the legacy-prefix match below in case an old per-competition
	// variant survives from before the refactor.
	const activeExactKey = `predictor_active_entry_${userId}`;
	const activeLegacyPrefix = `predictor_active_entry_${userId}_`;
	try {
		const keysToRemove: string[] = [];
		for (let i = 0; i < localStorage.length; i++) {
			const key = localStorage.key(i);
			if (
				key &&
				(key.startsWith(legacyPrefix) ||
					key === activeExactKey ||
					key.startsWith(activeLegacyPrefix))
			) {
				keysToRemove.push(key);
			}
		}
		for (const key of keysToRemove) localStorage.removeItem(key);
	} catch {
		// no-op
	}
	// Tear down every subscriber set for this user (any entry).
	const prefix = `${userId}|`;
	for (const ctx of Array.from(subscribers.keys())) {
		if (ctx.startsWith(prefix)) {
			const subs = subscribers.get(ctx);
			if (subs) for (const unsub of subs) unsub();
			subscribers.delete(ctx);
		}
	}
}
