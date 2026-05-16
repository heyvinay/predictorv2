/**
 * Pure helpers backing the leaderboard row presentation (Task F.3).
 *
 * Kept as separate exports so they can be unit-tested without rendering
 * the Svelte component (the project's vitest setup is pure-function only
 * — no @testing-library/svelte).
 */

import type { LeaderboardEntry, EntrySettings } from '$types';

/**
 * True when the row belongs to the viewer's user account.
 *
 * A user with multiple entries can own multiple rows; each gets the YOU
 * badge. `viewerUserId` is null when the viewer is unauthenticated, in
 * which case nothing is marked.
 */
export function isYouRow(row: LeaderboardEntry, viewerUserId: string | null | undefined): boolean {
	if (!viewerUserId) return false;
	return row.user_id === viewerUserId;
}

/**
 * Whether the row's `entry_reference` (WC26-…) should render to this viewer.
 *
 * Rules:
 *   - Owner always sees their own reference.
 *   - Admins always see references.
 *   - If `show_entry_reference_publicly` is on, everyone sees references.
 *   - Otherwise references are hidden from non-owners.
 *
 * `settings` may be null while the entries store is hydrating. Conservative
 * fallback: treat as if the flag were OFF (hide references from non-owners).
 * That matches the safer side of the privacy guarantee.
 */
export function shouldShowReference(
	row: LeaderboardEntry,
	settings: EntrySettings | null,
	viewerUserId: string | null | undefined,
	viewerIsAdmin: boolean = false
): boolean {
	if (viewerIsAdmin) return true;
	if (viewerUserId && row.user_id === viewerUserId) return true;
	return !!settings?.show_entry_reference_publicly;
}
