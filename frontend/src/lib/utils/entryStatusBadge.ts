/**
 * Entry status → UI badge mapping.
 *
 * The backend lifecycle is three-state (draft / submitted / withdrawn),
 * but the wizard and the entries list both render a four-state UI that
 * folds the deadline into the badge so users can tell pre-results
 * (LOCKED) apart from post-results (SCORED). Withdrawn entries — or
 * drafts past the deadline — show as NOT SUBMITTED.
 *
 * Single source of truth for both `SheetSelector` and the `/entries`
 * list page; mirroring the inline maps that used to live in
 * `SheetSelector.svelte`.
 */

import { computeDisplayStatus, type Entry } from '$lib/types/entry';

export type EntryUiStatus = 'draft' | 'locked' | 'scored' | 'missed';

export interface EntryBadge {
	label: string;
	/** DaisyUI badge-* class — semantic color. */
	class: string;
}

const BADGE: Record<EntryUiStatus, EntryBadge> = {
	draft: { label: 'DRAFT', class: 'badge-warning' },
	locked: { label: '🔒 LOCKED', class: 'badge-success' },
	scored: { label: '✓ SCORED', class: 'badge-success' },
	missed: { label: '✗ NOT SUBMITTED', class: 'badge-error' }
};

const DOT_FILL: Record<EntryUiStatus, string> = {
	draft: 'bg-warning',
	locked: 'bg-success',
	scored: 'bg-success',
	missed: 'bg-error'
};

export function entryUiStatus(entry: Entry, deadlinePassed: boolean): EntryUiStatus {
	const s = computeDisplayStatus(entry, 'phase_1');
	if (s === 'withdrawn') return 'missed';
	if (s === 'submitted') return deadlinePassed ? 'scored' : 'locked';
	return deadlinePassed ? 'missed' : 'draft';
}

export function entryStatusBadge(status: EntryUiStatus): EntryBadge {
	return BADGE[status];
}

export function entryStatusDot(status: EntryUiStatus): string {
	return DOT_FILL[status];
}
