/**
 * Silent sessionStorage mirror for unsaved prediction drafts.
 *
 * Per-tab by design: refresh keeps drafts, tab close drops them, sibling
 * tabs are independent. Subscribes to the three unsaved stores and
 * debounce-writes envelopes; hydrates on mount; drops kicked-off match
 * entries and locked-phase brackets.
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
	const raw = sessionStorage.getItem(key);
	if (!raw) return null;
	const env = safeParse<T>(raw);
	if (!env || env.v !== CURRENT_VERSION) {
		sessionStorage.removeItem(key);
		return null;
	}
	return env;
}

function isEmpty(data: unknown): boolean {
	if (data === null || data === undefined) return true;
	if (typeof data === 'object' && Object.keys(data as object).length === 0) return true;
	return false;
}

export function initPersistence(userId: string, entryId: string): void {
	if (!browser) return;
	const ctx = contextKey(userId, entryId);
	if (subscribers.has(ctx)) return;

	function writeOrRemove(key: string, data: unknown): void {
		try {
			if (isEmpty(data)) {
				sessionStorage.removeItem(key);
			} else {
				const envelope: Envelope<unknown> = {
					v: CURRENT_VERSION,
					savedAt: Date.now(),
					data
				};
				sessionStorage.setItem(key, JSON.stringify(envelope));
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

	subs.push(unsavedChanges.subscribe((changes) => writeMatches(changes)));
	subs.push(unsavedBracketPrediction.subscribe((bracket) => writeP1(bracket)));
	subs.push(unsavedPhase2BracketPrediction.subscribe((bracket) => writeP2(bracket)));

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
		// subscriber will overwrite/remove on the next store change.
	}

	// --- Phase 1 bracket: drop if phase is locked ---
	if (isPhase1Locked) {
		sessionStorage.removeItem(keyP1(userId, entryId));
	} else {
		const p1Env = readEnvelope<BracketPrediction>(keyP1(userId, entryId));
		if (p1Env) {
			unsavedBracketPrediction.set(p1Env.data);
			result.bracketPhase1Restored = true;
		}
	}

	// --- Phase 2 bracket: drop if phase is locked ---
	if (isPhase2BracketLocked) {
		sessionStorage.removeItem(keyP2(userId, entryId));
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
 * Called on logout — drafts live in sessionStorage (per-tab) while the
 * active-entry pointer lives in localStorage; we walk both.
 */
export function clearAllForUser(userId: string): void {
	if (!browser) return;
	const unsavedPrefix = `predictor_unsaved_${userId}_`;
	const activeExactKey = `predictor_active_entry_${userId}`;
	const activeLegacyPrefix = `predictor_active_entry_${userId}_`;

	try {
		const sessionKeysToRemove: string[] = [];
		for (let i = 0; i < sessionStorage.length; i++) {
			const key = sessionStorage.key(i);
			if (key && key.startsWith(unsavedPrefix)) sessionKeysToRemove.push(key);
		}
		for (const key of sessionKeysToRemove) sessionStorage.removeItem(key);
	} catch {
		// no-op
	}

	try {
		const localKeysToRemove: string[] = [];
		for (let i = 0; i < localStorage.length; i++) {
			const key = localStorage.key(i);
			if (key && (key === activeExactKey || key.startsWith(activeLegacyPrefix))) {
				localKeysToRemove.push(key);
			}
		}
		for (const key of localKeysToRemove) localStorage.removeItem(key);
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
