import { describe, expect, it } from 'vitest';

import type { Entry } from '$lib/types/entry';
import {
	entryUiStatus,
	entryStatusBadge,
	entryStatusDot,
	shouldShowPrizeModifier,
	type EntryUiStatus
} from './entryStatusBadge';

function makeEntry(overrides: Partial<Entry> = {}): Entry {
	return {
		id: 'e1',
		competition_id: 'c1',
		user_id: 'u1',
		reference: 'REF-1',
		display_name: 'Test Entry',
		entry_number: 1,
		paid: true,
		prize_eligible: true,
		is_disabled: false,
		disabled_reason: null,
		disabled_at: null,
		disabled_by_user_id: null,
		withdrawn_at: null,
		withdrawn_reason: null,
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		phases: [
			{
				phase: 'phase_1',
				status: 'draft',
				ready_at: null,
				submitted_at: null,
				locked_at: null,
				status_reason: null
			}
		],
		...overrides
	};
}

function submittedPhase() {
	return [
		{
			phase: 'phase_1' as const,
			status: 'submitted' as const,
			ready_at: null,
			submitted_at: '2026-01-02T00:00:00Z',
			locked_at: null,
			status_reason: null
		}
	];
}

describe('entryUiStatus', () => {
	it('returns "draft" for a draft entry before the deadline', () => {
		expect(entryUiStatus(makeEntry(), { deadlinePassed: false })).toBe('draft');
	});

	it('returns "missed" for a draft entry after the deadline', () => {
		expect(entryUiStatus(makeEntry(), { deadlinePassed: true })).toBe('missed');
	});

	it('returns "locked" for a submitted entry before the deadline', () => {
		const e = makeEntry({ phases: submittedPhase() });
		expect(entryUiStatus(e, { deadlinePassed: false })).toBe('locked');
	});

	it('returns "scored" for a submitted entry after the deadline', () => {
		const e = makeEntry({ phases: submittedPhase() });
		expect(entryUiStatus(e, { deadlinePassed: true })).toBe('scored');
	});

	it('returns "withdrawn" for a withdrawn entry regardless of deadline', () => {
		const e = makeEntry({ withdrawn_at: '2026-06-10T00:00:00Z' });
		expect(entryUiStatus(e, { deadlinePassed: false })).toBe('withdrawn');
		expect(entryUiStatus(e, { deadlinePassed: true })).toBe('withdrawn');
	});

	it('returns "disabled" when is_disabled is true, regardless of other state', () => {
		// Disabled wins over draft
		expect(entryUiStatus(makeEntry({ is_disabled: true }), { deadlinePassed: false })).toBe(
			'disabled'
		);
		// Disabled wins over submitted
		expect(
			entryUiStatus(makeEntry({ is_disabled: true, phases: submittedPhase() }), {
				deadlinePassed: true
			})
		).toBe('disabled');
		// Disabled wins over withdrawn
		expect(
			entryUiStatus(makeEntry({ is_disabled: true, withdrawn_at: '2026-06-10T00:00:00Z' }), {
				deadlinePassed: false
			})
		).toBe('disabled');
	});

	it('returns "ready" when totalFilled meets totalRequired pre-deadline on a draft', () => {
		expect(
			entryUiStatus(makeEntry(), {
				deadlinePassed: false,
				totalRequired: 104,
				totalFilled: 104
			})
		).toBe('ready');
	});

	it('returns "draft" when partially filled pre-deadline', () => {
		expect(
			entryUiStatus(makeEntry(), {
				deadlinePassed: false,
				totalRequired: 104,
				totalFilled: 50
			})
		).toBe('draft');
	});

	it('returns "draft" when counts are omitted even at 100% completion (skips READY check)', () => {
		// No counts passed — backwards compat for callers that don't have them
		expect(entryUiStatus(makeEntry(), { deadlinePassed: false })).toBe('draft');
	});

	it('returns "missed" not "ready" when counts indicate filled but deadline passed', () => {
		// READY only applies pre-deadline; missed wins past deadline
		expect(
			entryUiStatus(makeEntry(), {
				deadlinePassed: true,
				totalRequired: 104,
				totalFilled: 104
			})
		).toBe('missed');
	});
});

describe('entryStatusBadge', () => {
	it.each<[EntryUiStatus, string, string]>([
		['draft', 'DRAFT', 'badge-warning'],
		// 'ready' deliberately renders the same DRAFT/warning treatment
		// as 'draft' — see comment on BADGE in entryStatusBadge.ts.
		['ready', 'DRAFT', 'badge-warning'],
		['locked', '🔒 LOCKED', 'badge-success'],
		['scored', '✓ SCORED', 'badge-success'],
		['missed', '✗ NOT SUBMITTED', 'badge-error'],
		['withdrawn', 'WITHDRAWN', 'badge-neutral'],
		['disabled', '⚠ DISABLED', 'badge-error']
	])('maps %s → label "%s" / class "%s"', (status, label, cls) => {
		const badge = entryStatusBadge(status);
		expect(badge.label).toBe(label);
		expect(badge.class).toBe(cls);
	});
});

describe('entryStatusDot', () => {
	it.each<[EntryUiStatus, string]>([
		['draft', 'bg-warning'],
		['ready', 'bg-warning'],
		['locked', 'bg-success'],
		['scored', 'bg-success'],
		['missed', 'bg-error'],
		['withdrawn', 'bg-base-content/30'],
		['disabled', 'bg-error']
	])('maps %s → "%s"', (status, cls) => {
		expect(entryStatusDot(status)).toBe(cls);
	});
});

describe('shouldShowPrizeModifier', () => {
	it('returns false when entry is prize_eligible', () => {
		const e = makeEntry({ prize_eligible: true });
		const statuses: EntryUiStatus[] = [
			'draft',
			'ready',
			'locked',
			'scored',
			'missed',
			'withdrawn',
			'disabled'
		];
		for (const ui of statuses) {
			expect(shouldShowPrizeModifier(e, ui)).toBe(false);
		}
	});

	it('returns true for ineligible entries in active scoring states', () => {
		const e = makeEntry({ prize_eligible: false });
		const activeStates: EntryUiStatus[] = ['draft', 'ready', 'locked', 'scored', 'missed'];
		for (const ui of activeStates) {
			expect(shouldShowPrizeModifier(e, ui)).toBe(true);
		}
	});

	it('returns false for ineligible entries in admin-actioned states (suppressed)', () => {
		const e = makeEntry({ prize_eligible: false });
		expect(shouldShowPrizeModifier(e, 'disabled')).toBe(false);
		expect(shouldShowPrizeModifier(e, 'withdrawn')).toBe(false);
	});
});
