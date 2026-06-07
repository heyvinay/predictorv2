/**
 * Mission Control derived stores. Single source of active-entry context
 * for every ported widget — read from here instead of directly from raw
 * stores so the active-entry switcher re-contextualises the whole page
 * through ONE indirection.
 *
 * Upstream is single-entry-per-user; this layer is what makes the
 * active-entry-as-lens work for our multi-entry pool. Without it, every
 * ported widget would need its own active-entry awareness.
 */

import { derived } from 'svelte/store';
import { activeEntryId, entries } from '$stores/entries';
import { leaderboard } from '$stores/leaderboard';
import type { LeaderboardEntry } from '$types';

/** The leaderboard row for whichever entry the user is currently viewing. */
export const activeLeaderboardRow = derived(
	[leaderboard, activeEntryId],
	([$leaderboard, $activeEntryId]) =>
		($leaderboard ?? []).find((r: LeaderboardEntry) => r.entry_id === $activeEntryId) ?? null
);

export const activeRank = derived(activeLeaderboardRow, ($row) => $row?.position ?? null);
export const activePoints = derived(activeLeaderboardRow, ($row) => $row?.total_points ?? 0);
export const activeMovement = derived(activeLeaderboardRow, ($row) => $row?.movement ?? 0);
export const activeBreakdown = derived(activeLeaderboardRow, ($row) => $row?.breakdown ?? null);
export const activeCorrectOutcomes = derived(activeLeaderboardRow, ($row) => $row?.correct_outcomes ?? 0);
export const activeExactScores = derived(activeLeaderboardRow, ($row) => $row?.exact_scores ?? 0);

/** Map entry_id → leaderboard row for ALL the user's non-disabled entries.
 *  Used by the entry switcher to render rank + points on each pill. */
export const myLeaderboardByEntryId = derived(
	[leaderboard, entries],
	([$leaderboard, $entries]) => {
		const myIds = new Set(
			$entries.filter((e) => !e.is_disabled && !e.withdrawn_at).map((e) => e.id)
		);
		return new Map(
			($leaderboard ?? [])
				.filter((r: LeaderboardEntry) => myIds.has(r.entry_id))
				.map((r: LeaderboardEntry) => [r.entry_id, r])
		);
	}
);

/** The user's "best" (lowest rank) entry id. Drives the BEST ★ badge and
 *  the default active-entry on first paint. */
export const bestEntryId = derived(myLeaderboardByEntryId, ($map) => {
	let best: LeaderboardEntry | null = null;
	for (const row of $map.values()) {
		if (!best || row.position < best.position) best = row;
	}
	return best?.entry_id ?? null;
});

/** Entry IDs that aren't the active one (used for ghost sparklines, "also
 *  yours" leaderboard markers, etc.). */
export const siblingEntryIds = derived(
	[entries, activeEntryId],
	([$entries, $active]) =>
		$entries
			.filter((e) => !e.is_disabled && !e.withdrawn_at && e.id !== $active)
			.map((e) => e.id)
);

/** True when the user has at most one active entry. Hides the switcher
 *  and "viewing 1 of N" framing for single-entry players. */
export const isOnlyEntry = derived(
	entries,
	($entries) => $entries.filter((e) => !e.is_disabled && !e.withdrawn_at).length <= 1
);
