/**
 * Entry status → UI badge mapping.
 *
 * The backend lifecycle is three-state (draft / submitted / withdrawn),
 * but the user-facing UI surfaces a seven-state vocabulary that folds in
 * the deadline, the admin overlays (is_disabled), and completion progress
 * so users can tell at a glance what's actually going on:
 *
 *   draft     — still filling in (< 100% predicted)
 *   ready     — all picks filled, not yet submitted (deadline not passed)
 *   locked    — submitted, deadline not passed (awaiting results)
 *   scored    — submitted, deadline passed (results in)
 *   missed    — was draft, deadline passed (forgot to submit)
 *   withdrawn — admin/auto-withdrawn (was a real entry, now sidelined)
 *   disabled  — admin disabled (chargeback / suspicious / etc.)
 *
 * Precedence is top-down (first match wins):
 *   1. is_disabled                       → disabled
 *   2. withdrawn_at != null              → withdrawn
 *   3. backend status submitted +
 *      deadline passed                   → scored
 *   4. backend status submitted +
 *      deadline NOT passed               → locked
 *   5. backend status draft +
 *      deadline passed                   → missed
 *   6. backend status draft + filled
 *      (totalFilled >= totalRequired)    → ready
 *   7. otherwise                         → draft
 *
 * The READY state requires the caller to pass completion counts. When
 * omitted, the function falls through to DRAFT — backwards-compatible
 * for callers that don't have counts handy (list page rows, inactive
 * SheetSelector entries).
 *
 * Single source of truth for SheetSelector, the /entries list page, and
 * the /entries/[id] wizard hero.
 */

import { computeDisplayStatus, type Entry } from '$lib/types/entry';

export type EntryUiStatus =
	| 'draft'
	| 'ready'
	| 'locked'
	| 'scored'
	| 'missed'
	| 'withdrawn'
	| 'disabled';

export interface EntryBadge {
	label: string;
	/** DaisyUI badge-* class — semantic color. */
	class: string;
}

// Note: `ready` and `draft` deliberately render the same user-visible
// badge ("DRAFT", warning-amber). The internal `'ready'` state is kept
// distinct so wizard / Submit flow can branch on "all picks filled but
// not yet submitted" — e.g. enabling the Submit button — but the badge
// shouldn't read READY because that implies the user is done. Until
// they tick the disclaimer and tap Submit, the entry is still a draft.
const BADGE: Record<EntryUiStatus, EntryBadge> = {
	draft: { label: 'DRAFT', class: 'badge-warning' },
	ready: { label: 'DRAFT', class: 'badge-warning' },
	locked: { label: '🔒 LOCKED', class: 'badge-success' },
	scored: { label: '✓ SCORED', class: 'badge-success' },
	missed: { label: '✗ NOT SUBMITTED', class: 'badge-error' },
	withdrawn: { label: 'WITHDRAWN', class: 'badge-neutral' },
	disabled: { label: '⚠ DISABLED', class: 'badge-error' }
};

const DOT_FILL: Record<EntryUiStatus, string> = {
	draft: 'bg-warning',
	ready: 'bg-warning',
	locked: 'bg-success',
	scored: 'bg-success',
	missed: 'bg-error',
	withdrawn: 'bg-base-content/30',
	disabled: 'bg-error'
};

export interface EntryUiStatusOpts {
	deadlinePassed: boolean;
	/** Optional: completion counts. When both are passed AND the
	 *  entry is in a draft state pre-deadline, the function returns
	 *  READY once totalFilled >= totalRequired. Omit to skip the
	 *  READY check (caller will see DRAFT for unfilled drafts). */
	totalRequired?: number;
	totalFilled?: number;
}

export function entryUiStatus(entry: Entry, opts: EntryUiStatusOpts): EntryUiStatus {
	// 1. Admin overlay — wins over everything else.
	if (entry.is_disabled) return 'disabled';

	// 2. Explicit withdrawal (admin or auto) — distinct from missed.
	if (entry.withdrawn_at) return 'withdrawn';

	const backend = computeDisplayStatus(entry, 'phase_1');

	// 3 / 4. Submitted — deadline decides locked vs scored.
	if (backend === 'submitted') {
		return opts.deadlinePassed ? 'scored' : 'locked';
	}

	// 5. Draft past deadline — never submitted.
	if (opts.deadlinePassed) return 'missed';

	// 6. Draft before deadline, fully filled — READY (needs counts).
	if (
		opts.totalRequired !== undefined &&
		opts.totalFilled !== undefined &&
		opts.totalRequired > 0 &&
		opts.totalFilled >= opts.totalRequired
	) {
		return 'ready';
	}

	// 7. Default — still drafting.
	return 'draft';
}

export function entryStatusBadge(status: EntryUiStatus): EntryBadge {
	return BADGE[status];
}

export function entryStatusDot(status: EntryUiStatus): string {
	return DOT_FILL[status];
}

/**
 * Whether to render the secondary "NO PRIZE" chip next to the main
 * status badge. Surfaces an orthogonal axis — prize-pool eligibility —
 * without multiplying the lifecycle vocabulary.
 *
 * Shown when:
 *   - entry.prize_eligible is false, AND
 *   - the main status is one where ineligibility is not already implied
 *     (DISABLED / WITHDRAWN already carry that signal).
 *
 * Once the deadline passes, the chip is the canonical post-deadline
 * marker for any non-qualifying entry that wasn't admin-actioned.
 */
export function shouldShowPrizeModifier(entry: Entry, ui: EntryUiStatus): boolean {
	if (entry.prize_eligible) return false;
	const states: EntryUiStatus[] = ['draft', 'ready', 'locked', 'scored', 'missed'];
	return states.includes(ui);
}
