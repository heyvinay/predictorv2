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
import type { CompletionSummary, Entry, EntrySettings } from '$lib/types/entry';

export const entries = writable<Entry[]>([]);
export const entrySettings = writable<EntrySettings | null>(null);
export const activeEntryId = writable<string | null>(null);
export const entriesLoading = writable<boolean>(false);
export const entriesError = writable<string | null>(null);

export const activeEntry = derived(
	[entries, activeEntryId],
	([$entries, $id]) => $entries.find((e) => e.id === $id) ?? null
);

/** Entries still in DRAFT (user can edit). */
export const editableEntries = derived(entries, ($entries) =>
	$entries.filter(
		(e) =>
			!e.is_disabled &&
			!e.withdrawn_at &&
			e.phases.some((p) => p.status === 'draft')
	)
);

/** Entries that are SUBMITTED — qualify for scoring + leaderboard. */
export const submittedEntries = derived(entries, ($entries) =>
	$entries.filter(
		(e) =>
			!e.is_disabled &&
			!e.withdrawn_at &&
			e.phases.some((p) => p.status === 'submitted')
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

/**
 * Per-entry completion summaries keyed by entry id. Populated by
 * `loadCompletionSummaries()` — currently called from the landing page
 * so the WelcomeBackCard can distinguish "draft, still picking" from
 * "draft, fully picked but unsubmitted" (the silent-failure state).
 * Empty object when not yet loaded; consumers should treat a missing
 * key as "unknown completion."
 */
export const completionSummaries = writable<Record<string, CompletionSummary>>({});

/**
 * True when every pick category (groups, bracket, bonus) is fully
 * filled in. A `false` for a missing summary is intentional — we don't
 * want to claim readiness before we've loaded the data.
 */
export function isEntryComplete(s: CompletionSummary | undefined): boolean {
	if (!s) return false;
	return (
		s.groups.done === s.groups.total &&
		s.bracket.done === s.bracket.total &&
		s.bonus.done === s.bonus.total
	);
}

function activeEntryStorageKey(userId: string): string {
	return `predictor_active_entry_${userId}`;
}

function readPersistedActiveEntry(userId: string): string | null {
	if (!browser) return null;
	try {
		return localStorage.getItem(activeEntryStorageKey(userId));
	} catch {
		return null;
	}
}

function persistActiveEntry(userId: string, entryId: string | null): void {
	if (!browser) return;
	try {
		const key = activeEntryStorageKey(userId);
		if (entryId) localStorage.setItem(key, entryId);
		else localStorage.removeItem(key);
	} catch {
		// quota / disabled storage — silently degrade
	}
}

let hydrationContext: { userId: string } | null = null;

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
 * The active competition is a backend-side singleton — the API derives
 * it from the request's auth context, so we don't need to thread a
 * competition id from the frontend. (Earlier versions did; that caused
 * a race condition when `$user.competition_id` was still null in the
 * Svelte store at the moment `onMount` ran on a fresh page load.)
 *
 * Safe to call repeatedly — subsequent calls refresh the list without
 * resetting the active entry (unless the persisted one is no longer in
 * the response).
 */
export async function loadEntries(userId: string): Promise<void> {
	entriesLoading.set(true);
	entriesError.set(null);
	hydrationContext = { userId };

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

		const persisted = readPersistedActiveEntry(userId);
		const initial = pickInitialEntry(workingList, persisted);
		const nextId = initial?.id ?? null;
		activeEntryId.set(nextId);
		persistActiveEntry(userId, nextId);
	} catch (e) {
		entriesError.set(e instanceof Error ? e.message : 'Failed to load entries');
	} finally {
		entriesLoading.set(false);
	}
}

/**
 * Hydrate the per-entry completion summary map. Safe to call alongside
 * `loadEntries` — they hit independent endpoints and the response is
 * keyed by entry id so order doesn't matter. Failures are swallowed
 * (the card just falls back to "unknown completion" copy).
 */
export async function loadCompletionSummaries(): Promise<void> {
	try {
		const list = await entriesApi.getCompletionSummary();
		const next: Record<string, CompletionSummary> = {};
		for (const s of list) next[s.entry_id] = s;
		completionSummaries.set(next);
	} catch {
		// Soft failure — leave the map empty; consumers treat that as unknown.
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
				persistActiveEntry(hydrationContext.userId, fallback?.id ?? null);
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
		persistActiveEntry(hydrationContext.userId, entryId);
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
	completionSummaries.set({});
	hydrationContext = null;
}
