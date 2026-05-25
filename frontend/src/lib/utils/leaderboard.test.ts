/**
 * Pure-function tests for the leaderboard row helpers (Task F.3).
 */

import { describe, expect, it } from 'vitest';
import { isYouRow, shouldShowReference } from './leaderboard';
import type { LeaderboardEntry, EntrySettings, PointBreakdown } from '$types';

function makeRow(overrides: Partial<LeaderboardEntry> = {}): LeaderboardEntry {
	// PointBreakdown carries lots of fields; we don't read them in these
	// helpers, so a zero-filled object is fine.
	const zeroBreakdown = {} as PointBreakdown;
	return {
		entry_id: 'entry-1',
		entry_reference: 'WC26-000001',
		entry_name: 'Entry 1',
		user_id: 'user-alice',
		user_name: 'Alice',
		position: 1,
		total_points: 0,
		breakdown: zeroBreakdown,
		correct_outcomes: 0,
		exact_scores: 0,
		movement: 0,
		...overrides
	};
}

function makeSettings(overrides: Partial<EntrySettings> = {}): EntrySettings {
	return {
		max_entries_per_user: 5,
		auto_create_first_entry: true,
		allow_duplicate_from_existing: true,
		allow_user_rename: true,
		payment_mode: 'per_entry',
		block_unpaid_entry_submission: false,
		show_entry_reference_publicly: false,
		phase_scoped_status_enabled: false,
		...overrides
	};
}

describe('isYouRow', () => {
	it('matches when row.user_id === viewerUserId', () => {
		const r = makeRow();
		expect(isYouRow(r, 'user-alice')).toBe(true);
	});

	it('does not match other users', () => {
		const r = makeRow();
		expect(isYouRow(r, 'user-bob')).toBe(false);
	});

	it('returns false for unauthenticated viewers', () => {
		const r = makeRow();
		expect(isYouRow(r, null)).toBe(false);
		expect(isYouRow(r, undefined)).toBe(false);
	});

	it('matches every row a user owns (multi-entry case)', () => {
		const e1 = makeRow({ entry_id: 'e1', user_id: 'user-alice' });
		const e2 = makeRow({ entry_id: 'e2', user_id: 'user-alice' });
		expect(isYouRow(e1, 'user-alice')).toBe(true);
		expect(isYouRow(e2, 'user-alice')).toBe(true);
	});
});

describe('shouldShowReference', () => {
	it('shows for owner regardless of public flag', () => {
		const r = makeRow();
		const s = makeSettings({ show_entry_reference_publicly: false });
		expect(shouldShowReference(r, s, 'user-alice')).toBe(true);
	});

	it('hides from non-owner when flag is off', () => {
		const r = makeRow();
		const s = makeSettings({ show_entry_reference_publicly: false });
		expect(shouldShowReference(r, s, 'user-bob')).toBe(false);
	});

	it('shows to non-owner when flag is on', () => {
		const r = makeRow();
		const s = makeSettings({ show_entry_reference_publicly: true });
		expect(shouldShowReference(r, s, 'user-bob')).toBe(true);
	});

	it('shows to admin regardless of flag or ownership', () => {
		const r = makeRow();
		const s = makeSettings({ show_entry_reference_publicly: false });
		expect(shouldShowReference(r, s, 'user-bob', true)).toBe(true);
	});

	it('conservative when settings is null (hides from non-owners)', () => {
		const r = makeRow();
		expect(shouldShowReference(r, null, 'user-bob')).toBe(false);
		// Owner still sees their own.
		expect(shouldShowReference(r, null, 'user-alice')).toBe(true);
	});

	it('hides from unauthenticated viewer when flag is off', () => {
		const r = makeRow();
		const s = makeSettings({ show_entry_reference_publicly: false });
		expect(shouldShowReference(r, s, null)).toBe(false);
		expect(shouldShowReference(r, s, undefined)).toBe(false);
	});

	it('shows to unauthenticated viewer when flag is on', () => {
		const r = makeRow();
		const s = makeSettings({ show_entry_reference_publicly: true });
		expect(shouldShowReference(r, s, null)).toBe(true);
	});
});
