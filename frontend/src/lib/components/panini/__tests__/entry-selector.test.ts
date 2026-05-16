/**
 * Tests for the status-mapping helpers that drive PnEntrySelector's
 * status chip + the wizard's editable gating.
 *
 * The project's Vitest setup is pure-function only (no jsdom /
 * testing-library/svelte). We test the helpers directly rather than
 * rendering the component — these helpers are 100% of the surface
 * that determines what status the user sees and whether they can
 * type into a score input.
 */

import { describe, expect, it } from 'vitest';
import {
	computeDisplayStatus,
	isPhaseEditable,
	type Entry,
	type EntryStatus
} from '$lib/types/entry';

function makeEntry(overrides: Partial<Entry> = {}): Entry {
	return {
		id: 'entry-1',
		competition_id: 'comp-1',
		user_id: 'user-1',
		reference: 'WC26-000001',
		display_name: 'Entry 1',
		entry_number: 1,
		paid: false,
		prize_eligible: true,
		is_disabled: false,
		disabled_reason: null,
		disabled_at: null,
		disabled_by_user_id: null,
		withdrawn_at: null,
		withdrawn_reason: null,
		created_at: '2026-05-01T00:00:00Z',
		updated_at: '2026-05-01T00:00:00Z',
		phases: [
			{
				phase: 'phase_1',
				status: 'draft',
				ready_at: null,
				submitted_at: null,
				locked_at: null,
				status_reason: null
			},
			{
				phase: 'phase_2',
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

describe('computeDisplayStatus', () => {
	it('returns the phase status for a healthy entry', () => {
		const e = makeEntry({
			phases: [
				{
					phase: 'phase_1',
					status: 'ready',
					ready_at: '2026-05-02T00:00:00Z',
					submitted_at: null,
					locked_at: null,
					status_reason: null
				},
				{
					phase: 'phase_2',
					status: 'draft',
					ready_at: null,
					submitted_at: null,
					locked_at: null,
					status_reason: null
				}
			]
		});
		expect(computeDisplayStatus(e, 'phase_1')).toBe<EntryStatus>('ready');
		expect(computeDisplayStatus(e, 'phase_2')).toBe<EntryStatus>('draft');
	});

	it('treats is_disabled as terminal — trumps phase status', () => {
		const e = makeEntry({
			is_disabled: true,
			disabled_reason: 'admin removed',
			phases: [
				{
					phase: 'phase_1',
					status: 'locked',
					ready_at: null,
					submitted_at: null,
					locked_at: null,
					status_reason: null
				},
				{
					phase: 'phase_2',
					status: 'submitted',
					ready_at: null,
					submitted_at: null,
					locked_at: null,
					status_reason: null
				}
			]
		});
		expect(computeDisplayStatus(e, 'phase_1')).toBe<EntryStatus>('disabled');
		expect(computeDisplayStatus(e, 'phase_2')).toBe<EntryStatus>('disabled');
	});

	it('treats withdrawn_at as terminal but ranks below disabled', () => {
		const withdrawn = makeEntry({ withdrawn_at: '2026-05-10T12:00:00Z' });
		expect(computeDisplayStatus(withdrawn, 'phase_1')).toBe<EntryStatus>('withdrawn');

		// Disabled wins if both flags are set (admin override).
		const both = makeEntry({
			is_disabled: true,
			withdrawn_at: '2026-05-10T12:00:00Z'
		});
		expect(computeDisplayStatus(both, 'phase_1')).toBe<EntryStatus>('disabled');
	});

	it('falls back to draft when the phase row is missing', () => {
		const e = makeEntry({ phases: [] });
		expect(computeDisplayStatus(e, 'phase_1')).toBe<EntryStatus>('draft');
	});
});

describe('isPhaseEditable', () => {
	it('is true only for draft', () => {
		const draft = makeEntry();
		expect(isPhaseEditable(draft, 'phase_1')).toBe(true);

		const ready = makeEntry({
			phases: [
				{ phase: 'phase_1', status: 'ready', ready_at: null, submitted_at: null, locked_at: null, status_reason: null },
				{ phase: 'phase_2', status: 'draft', ready_at: null, submitted_at: null, locked_at: null, status_reason: null }
			]
		});
		expect(isPhaseEditable(ready, 'phase_1')).toBe(false);
		expect(isPhaseEditable(ready, 'phase_2')).toBe(true);

		const submitted = makeEntry({
			phases: [
				{ phase: 'phase_1', status: 'submitted', ready_at: null, submitted_at: null, locked_at: null, status_reason: null },
				{ phase: 'phase_2', status: 'draft', ready_at: null, submitted_at: null, locked_at: null, status_reason: null }
			]
		});
		expect(isPhaseEditable(submitted, 'phase_1')).toBe(false);
	});

	it('returns false for disabled / withdrawn regardless of phase status', () => {
		const disabled = makeEntry({ is_disabled: true });
		expect(isPhaseEditable(disabled, 'phase_1')).toBe(false);

		const withdrawn = makeEntry({ withdrawn_at: '2026-05-12T00:00:00Z' });
		expect(isPhaseEditable(withdrawn, 'phase_1')).toBe(false);
	});
});
