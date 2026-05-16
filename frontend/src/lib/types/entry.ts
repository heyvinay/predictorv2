/**
 * Prediction-entry types — mirrors `backend/app/schemas/entry.py` and
 * `backend/app/models/entry.py`.
 *
 * The backend uses per-phase status: each entry carries an array of
 * `EntryPhase` rows (one per `PredictionPhase`) with its own status +
 * timestamps. There is no single top-level "entry status" — display
 * status is computed via {@link computeDisplayStatus}.
 */

import type { PredictionPhase } from './index';

export type EntryStatus =
	| 'draft'
	| 'ready'
	| 'submitted'
	| 'locked'
	| 'withdrawn'
	| 'disabled';

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
	allow_user_withdrawal: boolean;
	require_ready_before_submit: boolean;
	payment_mode: PaymentMode;
	block_unpaid_entry_submission: boolean;
	show_entry_reference_publicly: boolean;
	phase_scoped_status_enabled: boolean;
	bonus_questions_required_for_ready: boolean;
}

export interface EntryCreate {
	display_name?: string;
}

export interface EntryRename {
	display_name: string;
}

export interface EntryWithdraw {
	reason?: string;
}

/**
 * Compute the entry-level status the UI should display.
 *
 * Order of precedence:
 *   1. `disabled`   — admin overlay; trumps everything.
 *   2. `withdrawn`  — user-initiated permanent exit.
 *   3. The active phase's status (`draft` / `ready` / `submitted` / `locked`).
 *
 * Falls back to `draft` if no phase row exists for `phase` (defensive —
 * the backend always seeds both phase rows on entry creation).
 */
export function computeDisplayStatus(
	entry: Entry,
	phase: PredictionPhase
): EntryStatus {
	if (entry.is_disabled) return 'disabled';
	if (entry.withdrawn_at) return 'withdrawn';
	const row = entry.phases.find((p) => p.phase === phase);
	return row?.status ?? 'draft';
}

/**
 * True when an entry can be edited in `phase` (score inputs unlocked,
 * "Save draft" / "Mark ready" affordances visible). Mirrors the wizard's
 * status-driven gating.
 */
export function isPhaseEditable(entry: Entry, phase: PredictionPhase): boolean {
	const status = computeDisplayStatus(entry, phase);
	return status === 'draft';
}
