/**
 * Prediction-entry types — mirrors `backend/app/schemas/entry.py` and
 * `backend/app/models/entry.py` after the lifecycle simplification.
 *
 * Three-status model: DRAFT, SUBMITTED, WITHDRAWN. Per-phase rows still
 * exist on the backend (Phase 2 dormant for future revival), but the UI
 * surface treats every entry as a single object with one status — the
 * Phase 1 row's status.
 */

import type { PredictionPhase } from './index';

export type EntryStatus = 'draft' | 'submitted' | 'withdrawn';

export type PaymentMode = 'per_entry' | 'per_user';

export interface EntryPhase {
	phase: PredictionPhase;
	status: EntryStatus;
	ready_at: string | null;
	submitted_at: string | null;
	locked_at: string | null;
	status_reason: string | null;
}

export interface Entry {
	id: string;
	competition_id: string;
	user_id: string;
	reference: string;
	display_name: string;
	entry_number: number;
	paid: boolean;
	prize_eligible: boolean;
	is_disabled: boolean;
	disabled_reason: string | null;
	disabled_at: string | null;
	disabled_by_user_id: string | null;
	withdrawn_at: string | null;
	withdrawn_reason: string | null;
	created_at: string;
	updated_at: string;
	phases: EntryPhase[];
}

export interface EntrySettings {
	max_entries_per_user: number;
	auto_create_first_entry: boolean;
	allow_duplicate_from_existing: boolean;
	allow_user_rename: boolean;
	payment_mode: PaymentMode;
	block_unpaid_entry_submission: boolean;
	show_entry_reference_publicly: boolean;
	phase_scoped_status_enabled: boolean;
}

export interface CompletionCount {
	done: number;
	total: number;
}

export interface CompletionSummary {
	entry_id: string;
	groups: CompletionCount;
	bracket: CompletionCount;
	bonus: CompletionCount;
	/** Team picked at `stage='winner'` in the bracket, or null if not yet
	 *  predicted. Surfaced on the entries list/card view so users see
	 *  their champion at a glance without opening the wizard. */
	predicted_winner: string | null;
}

export interface EntryCreate {
	display_name?: string;
}

export interface EntryRename {
	display_name: string;
}

export interface EntryWithdraw {
	reason: string;
}

export interface EntryReinstate {
	reason: string;
}

/**
 * Compute the entry-level status the UI should display.
 *
 * Order of precedence:
 *   1. `withdrawn` — set by admin or by the system at competition start.
 *   2. The Phase 1 row's status (`draft` / `submitted`).
 *
 * `is_disabled` is an orthogonal admin overlay (chargebacks, suspicious
 * entries). It does not replace the status badge — UI can render it as
 * an additional "Suspended" pill on top of the status if desired.
 */
export function computeDisplayStatus(
	entry: Entry,
	phase: PredictionPhase
): EntryStatus {
	if (entry.withdrawn_at) return 'withdrawn';
	const row = entry.phases.find((p) => p.phase === phase);
	return row?.status ?? 'draft';
}

/**
 * True when an entry can be edited (score inputs unlocked, "Submit"
 * affordance visible). Edit is only allowed on `draft` entries that
 * haven't crossed the competition deadline.
 */
export function isPhaseEditable(entry: Entry, phase: PredictionPhase): boolean {
	const status = computeDisplayStatus(entry, phase);
	return status === 'draft';
}

/**
 * Lifecycle button visibility helpers.
 *
 * - **Submit** — visible on DRAFT entries, before the competition deadline.
 * - **Edit**   — visible on SUBMITTED entries, before the competition deadline.
 *
 * Both predicates take the competition's `phase1_deadline` so the UI can
 * compute "is the deadline still in the future?" without hitting the
 * server again. Pass `null` if no deadline is set (admin not yet
 * configured) — both buttons are then allowed.
 *
 * Admin-only actions (withdraw, reinstate) are not exposed via these
 * helpers — they're only ever rendered from the admin entries table.
 */
export function canSubmit(
	entry: Entry,
	phase: PredictionPhase,
	phase1Deadline: string | null
): boolean {
	if (entry.is_disabled || entry.withdrawn_at) return false;
	const row = entry.phases.find((p) => p.phase === phase);
	if (!row) return false;
	if (row.status !== 'draft') return false;
	return _isBeforeDeadline(phase1Deadline);
}

export function canEdit(
	entry: Entry,
	phase: PredictionPhase,
	phase1Deadline: string | null
): boolean {
	if (entry.is_disabled || entry.withdrawn_at) return false;
	const row = entry.phases.find((p) => p.phase === phase);
	if (!row) return false;
	if (row.status !== 'submitted') return false;
	return _isBeforeDeadline(phase1Deadline);
}

function _isBeforeDeadline(deadline: string | null): boolean {
	if (!deadline) return true; // no deadline configured → editing allowed.
	return new Date(deadline).getTime() > Date.now();
}
