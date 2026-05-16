/**
 * Admin API functions.
 */

import { api } from './client';
import type { Entry, EntrySettings, PaymentMode } from '$lib/types/entry';
import type { PredictionPhase } from '$types';

export interface AdminStats {
	total_users: number;
	active_users: number;
	total_fixtures: number;
	completed_fixtures: number;
	live_fixtures: number;
	total_predictions: number;
	total_scores: number;
}

export interface CompetitionAdminView {
	id: string;
	name: string;
	entry_fee: number;
	phase1_deadline: string | null;
	is_phase2_active: boolean;
	phase2_activated_at: string | null;
	phase2_bracket_deadline: string | null;
	phase2_deadline: string | null;
	is_active: boolean;
	fixture_count: number;
	user_count: number;
}

export interface UserAdminView {
	id: string;
	email: string;
	name: string;
	auth_provider: string;
	is_admin: boolean;
	is_active: boolean;
	/** Backend may omit this until the migration lands; treat undefined as false. */
	paid?: boolean;
	created_at: string;
	prediction_count: number;
}

export interface SyncScoresResponse {
	synced: number;
	updated: number;
	errors: string[];
}

export async function getAdminStats(): Promise<AdminStats> {
	return api.get<AdminStats>('/admin/stats');
}

export async function getCompetitions(): Promise<CompetitionAdminView[]> {
	return api.get<CompetitionAdminView[]>('/admin/competitions');
}

export async function setPhase1Deadline(deadline: string): Promise<{ status: string; deadline: string }> {
	return api.post('/admin/competition/phase1/deadline', { deadline });
}

export async function activatePhase2(bracketDeadline: string): Promise<{ status: string; bracket_deadline: string; activated_at: string }> {
	return api.post('/admin/competition/phase2/activate', { bracket_deadline: bracketDeadline });
}

export async function deactivatePhase2(): Promise<{ status: string }> {
	return api.post('/admin/competition/phase2/deactivate');
}

export async function getAllUsers(): Promise<UserAdminView[]> {
	return api.get<UserAdminView[]>('/admin/users');
}

export async function toggleUserAdmin(userId: string): Promise<UserAdminView> {
	return api.patch<UserAdminView>(`/admin/users/${userId}/admin`);
}

export async function toggleUserActive(userId: string): Promise<UserAdminView> {
	return api.patch<UserAdminView>(`/admin/users/${userId}/active`);
}

/**
 * Toggle a user's paid status.
 *
 * The backend endpoint /admin/users/{id}/paid will exist once the worktree's
 * backend changes merge (User.paid field, migration, endpoint) and
 * `alembic upgrade head` runs against the prod-shape DB. Until then this
 * falls back to a per-browser localStorage flag so the UI is fully demoable.
 *
 * Once the backend is live the localStorage cache becomes harmless mirror.
 */
const PAID_LOCAL_PREFIX = 'predictor.paid.';

export function getPaidLocal(userId: string): boolean {
	if (typeof localStorage === 'undefined') return false;
	return localStorage.getItem(PAID_LOCAL_PREFIX + userId) === '1';
}

export async function toggleUserPaid(userId: string): Promise<boolean> {
	try {
		const view = await api.patch<UserAdminView>(`/admin/users/${userId}/paid`);
		const next = !!view.paid;
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem(PAID_LOCAL_PREFIX + userId, next ? '1' : '0');
		}
		return next;
	} catch (_e) {
		// Backend doesn't have the endpoint yet — fall back to localStorage.
		const current = getPaidLocal(userId);
		const next = !current;
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem(PAID_LOCAL_PREFIX + userId, next ? '1' : '0');
		}
		return next;
	}
}

export async function syncScores(): Promise<SyncScoresResponse> {
	return api.post<SyncScoresResponse>('/admin/scores/sync');
}

// ---------------------------------------------------------------------------
// Entry administration (Task F.2)
// ---------------------------------------------------------------------------

/** One audit row from `prediction_entry_events`. */
export interface EntryEvent {
	id: string;
	entry_id: string;
	phase: PredictionPhase | null;
	from_status: string;
	to_status: string;
	actor_user_id: string;
	actor_role: string;
	reason: string | null;
	created_at: string;
}

/** Result of `POST /admin/competition/phase2/open`. */
export interface Phase2OpenResponse {
	entries_opened: number;
	entries_skipped_withdrawn: number;
	entries_skipped_disabled: number;
	entries_already_open: number;
}

/** Filters mirror the backend `GET /admin/entries` query params. */
export interface AdminEntryFilters {
	user_id?: string;
	reference?: string;
	status?: string; // 'draft' | 'ready' | 'submitted' | 'locked' | 'withdrawn' | 'disabled'
	paid?: boolean;
	disabled?: boolean;
}

/** Partial update — only included keys are PATCHed. */
export interface EntrySettingsUpdate {
	max_entries_per_user?: number;
	auto_create_first_entry?: boolean;
	allow_duplicate_from_existing?: boolean;
	allow_user_rename?: boolean;
	allow_user_withdrawal?: boolean;
	require_ready_before_submit?: boolean;
	payment_mode?: PaymentMode;
	block_unpaid_entry_submission?: boolean;
	show_entry_reference_publicly?: boolean;
	phase_scoped_status_enabled?: boolean;
	bonus_questions_required_for_ready?: boolean;
}

// --- Competition entry settings (admin) ---

export async function getAdminEntrySettings(): Promise<EntrySettings> {
	return api.get<EntrySettings>('/admin/competition/entry-settings');
}

export async function updateAdminEntrySettings(
	patch: EntrySettingsUpdate
): Promise<EntrySettings> {
	return api.patch<EntrySettings>('/admin/competition/entry-settings', patch);
}

// --- Phase II open ---

export async function openPhase2(): Promise<Phase2OpenResponse> {
	return api.post<Phase2OpenResponse>('/admin/competition/phase2/open');
}

// --- Entries listing + per-row actions ---

export async function adminListEntries(
	filters: AdminEntryFilters = {}
): Promise<Entry[]> {
	const params = new URLSearchParams();
	if (filters.user_id) params.set('user_id', filters.user_id);
	if (filters.reference) params.set('reference', filters.reference);
	if (filters.status) params.set('status', filters.status);
	if (filters.paid !== undefined) params.set('paid', String(filters.paid));
	if (filters.disabled !== undefined) params.set('disabled', String(filters.disabled));
	const qs = params.toString();
	const url = qs ? `/admin/entries?${qs}` : '/admin/entries';
	return api.get<Entry[]>(url);
}

export async function getAdminEntryEvents(entryId: string): Promise<EntryEvent[]> {
	return api.get<EntryEvent[]>(`/admin/entries/${entryId}/events`);
}

export async function adminDisableEntry(
	entryId: string,
	reason: string
): Promise<Entry> {
	return api.post<Entry>(`/admin/entries/${entryId}/disable`, { reason });
}

export async function adminEnableEntry(entryId: string): Promise<Entry> {
	return api.post<Entry>(`/admin/entries/${entryId}/enable`);
}

export async function adminSetEntryPaid(
	entryId: string,
	paid: boolean
): Promise<Entry> {
	return api.patch<Entry>(`/admin/entries/${entryId}/paid`, { paid });
}

export async function adminSetEntryPrizeEligible(
	entryId: string,
	prize_eligible: boolean
): Promise<Entry> {
	return api.patch<Entry>(`/admin/entries/${entryId}/prize-eligible`, {
		prize_eligible
	});
}
