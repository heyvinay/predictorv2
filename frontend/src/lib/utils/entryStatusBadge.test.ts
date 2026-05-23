import { describe, expect, it } from 'vitest';

import type { Entry } from '$lib/types/entry';
import {
	entryUiStatus,
	entryStatusBadge,
	entryStatusDot,
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

describe('entryUiStatus', () => {
	it('returns "draft" for a draft entry before the deadline', () => {
		expect(entryUiStatus(makeEntry(), false)).toBe('draft');
	});

	it('returns "missed" for a draft entry after the deadline', () => {
		expect(entryUiStatus(makeEntry(), true)).toBe('missed');
	});

	it('returns "locked" for a submitted entry before the deadline', () => {
		const e = makeEntry({
			phases: [
				{
					phase: 'phase_1',
					status: 'submitted',
					ready_at: null,
					submitted_at: '2026-01-02T00:00:00Z',
					locked_at: null,
					status_reason: null
				}
			]
		});
		expect(entryUiStatus(e, false)).toBe('locked');
	});

	it('returns "scored" for a submitted entry after the deadline', () => {
		const e = makeEntry({
			phases: [
				{
					phase: 'phase_1',
					status: 'submitted',
					ready_at: null,
					submitted_at: '2026-01-02T00:00:00Z',
					locked_at: '2026-06-10T00:00:00Z',
					status_reason: null
				}
			]
		});
		expect(entryUiStatus(e, true)).toBe('scored');
	});

	it('returns "missed" for a withdrawn entry regardless of deadline', () => {
		const e = makeEntry({ withdrawn_at: '2026-06-10T00:00:00Z' });
		expect(entryUiStatus(e, false)).toBe('missed');
		expect(entryUiStatus(e, true)).toBe('missed');
	});
});

describe('entryStatusBadge', () => {
	it.each<[EntryUiStatus, string, string]>([
		['draft', 'DRAFT', 'badge-warning'],
		['locked', '🔒 LOCKED', 'badge-success'],
		['scored', '✓ SCORED', 'badge-success'],
		['missed', '✗ NOT SUBMITTED', 'badge-error']
	])('maps %s → label "%s" / class "%s"', (status, label, cls) => {
		const badge = entryStatusBadge(status);
		expect(badge.label).toBe(label);
		expect(badge.class).toBe(cls);
	});
});

describe('entryStatusDot', () => {
	it.each<[EntryUiStatus, string]>([
		['draft', 'bg-warning'],
		['locked', 'bg-success'],
		['scored', 'bg-success'],
		['missed', 'bg-error']
	])('maps %s → "%s"', (status, cls) => {
		expect(entryStatusDot(status)).toBe(cls);
	});
});
