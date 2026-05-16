/**
 * Entries store.
 *
 * Owns the list of the current user's prediction entries, the
 * competition's entry settings, and the active entry id (which drives
 * every prediction read/write in the wizard + the "my points" KPI on
 * the dashboard).
 *
 * Hydration sequence (called by route layouts after auth):
 *   1. `loadEntries(userId, competitionId)` — GET /entries + /entries/settings
 *   2. If list is empty and `auto_create_first_entry` is true → POST /entries
 *   3. Pick active entry: localStorage key first, then most-recently-updated
 *      eligible entry. Persist on every explicit change.
 *
 * Single-source-of-truth: predictions and unsavedPersistence both read
 * `activeEntryId` to scope their keys/queries. Switching active entry
 * is the only mutation that should ever cause those stores to clear and
 * refetch — see `setActiveEntry`.
 */

import { writable, derived, get } from 'svelte/store';
import { browser } from '$app/environment';
import * as entriesApi from '$api/entries';
import type { Entry, EntrySettings } from '$lib/types/entry';

export const entries = writable<Entry[]>([]);
export const entrySettings = writable<EntrySettings | null>(null);
export const activeEntryId = writable<string | null>(null);
export const entriesLoading = writable<boolean>(false);
export const entriesError = writable<string | null>(null);

export const activeEntry = derived(
	[entries, activeEntryId],
	([$entries, $id]) => $entries.find((e) => e.id === $id) ?? null
);

/** Entries the user can still edit (draft) or has prepared (ready). */
export const editableEntries = derived(entries, ($entries) =>
	$entries.filter(
		(e) =>
			!e.is_disabled &&
			!e.withdrawn_at &&
			e.phases.some((p) => p.status === 'draft' || p.status === 'ready')
	)
);

/** Entries that are submitted or locked — count toward the leaderboard. */
export const submittedEntries = derived(entries, ($entries) =>
	$entries.filter(
		(e) =>
			!e.is_disabled &&
			!e.withdrawn_at &&
			e.phases.some((p) => p.status === 'submitted' || p.status === 'locked')
	)
);

/**
 * True when the competition is configured for one entry per user. The
 * wizard collapses the selector to a status pill in this mode.
 *
 * Defaults to true if settings haven't loaded yet — safer than briefly
 * showing the multi-entry chrome during hydration.
 */
export const isSingleEntryMode = derived(
	entrySettings,
	($s) => ($s?.max_entries_per_user ?? 1) === 1
);

function activeEntryStorageKey(userId: string, competitionId: string): string {
	return `predictor_active_entry_${userId}_${competitionId}`;
}

function readPersistedActiveEntry(userId: string, competitionId: string): string | null {
	if (!browser) return null;
	try {
		return localStorage.getItem(activeEntryStorageKey(userId, competitionId));
	} catch {
		return null;
	}
}

function persistActiveEntry(
	userId: string,
	competitionId: string,
	entryId: string | null
): void {
	if (!browser) return;
	try {
		const key = activeEntryStorageKey(userId, competitionId);
		if (entryId) localStorage.setItem(key, entryId);
		else localStorage.removeItem(key);
	} catch {
		// quota / disabled storage — silently degrade
	}
}

let hydrationContext: { userId: string; competitionId: string } | null = null;

function pickInitialEntry(list: Entry[], persistedId: string | null): Entry | null {
	if (list.length === 0) return null;
	const eligible = list.filter((e) => !e.is_disabled && !e.withdrawn_at);
	const pool = eligible.length > 0 ? eligible : list;

	if (persistedId) {
		const match = pool.find((e) => e.id === persistedId);
		if (match) return match;
	}

	// Most-recently-updated wins. updated_at is an ISO 8601 string so
	// lexicographic compare is safe.
	return [...pool].sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0];
}

/**
 * Hydrate the entries store for a logged-in user.
 *
 * Safe to call repeatedly — subsequent calls refresh the list without
 * resetting the active entry (unless the persisted one is no longer in
 * the response).
 */
export async function loadEntries(userId: string, competitionId: string): Promise<void> {
	entriesLoading.set(true);
	entriesError.set(null);
	hydrationContext = { userId, competitionId };

	try {
		const [list, settings] = await Promise.all([
			entriesApi.listEntries(),
			entriesApi.getEntrySettings()
		]);
		entrySettings.set(settings);

		let workingList = list;
		if (workingList.length === 0 && settings.auto_create_first_entry) {
			const created = await entriesApi.createEntry();
			workingList = [created];
		}
		entries.set(workingList);

		const persisted = readPersistedActiveEntry(userId, competitionId);
		const initial = pickInitialEntry(workingList, persisted);
		const nextId = initial?.id ?? null;
		activeEntryId.set(nextId);
		persistActiveEntry(userId, competitionId, nextId);
	} catch (e) {
		entriesError.set(e instanceof Error ? e.message : 'Failed to load entries');
	} finally {
		entriesLoading.set(false);
	}
}

/**
 * Refresh the list without disturbing the active entry. Use after a
 * create / rename / duplicate / withdraw round-trip so the dropdown
 * reflects the new state.
 */
export async function refreshEntries(): Promise<void> {
	try {
		const list = await entriesApi.listEntries();
		entries.set(list);
		// If the active entry vanished, fall back to the most recent.
		const current = get(activeEntryId);
		if (current && !list.some((e) => e.id === current)) {
			const fallback = pickInitialEntry(list, null);
			activeEntryId.set(fallback?.id ?? null);
			if (hydrationContext) {
				persistActiveEntry(
					hydrationContext.userId,
					hydrationContext.competitionId,
					fallback?.id ?? null
				);
			}
		}
	} catch (e) {
		entriesError.set(e instanceof Error ? e.message : 'Failed to refresh entries');
	}
}

/**
 * Switch the active entry. Persists the choice and lets subscribers
 * (predictions store, unsavedPersistence) react.
 */
export function setActiveEntry(entryId: string): void {
	activeEntryId.set(entryId);
	if (hydrationContext) {
		persistActiveEntry(hydrationContext.userId, hydrationContext.competitionId, entryId);
	}
}

/**
 * Tear down on logout. Wipes in-memory state; localStorage entries
 * are kept so the user gets their previous active entry on next login.
 */
export function resetEntries(): void {
	entries.set([]);
	entrySettings.set(null);
	activeEntryId.set(null);
	entriesError.set(null);
	hydrationContext = null;
}
