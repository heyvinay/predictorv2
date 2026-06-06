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
	/** v2.160.0 — powers the Entries card on the Overview. */
	total_entries: number;
	/** v2.160.0 — DISTINCT entries with at least one SUBMITTED phase. */
	submitted_entries: number;
	/** v2.160.0 — active competition's entry_fee × submitted_entries. 0 if no active competition. */
	prize_pool: number;
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
	/** Nullable: magic-link sign-ups that haven't completed /onboarding
	 *  yet have name === null. Render with an email-prefix fallback. */
	name: string | null;
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
	/**
	 * Free-text smart search — OR-matches user email and entry reference
	 * (substring, case-insensitive). Backend wires this through
	 * `services/entries.py:admin_list_entries`'s `search` param. See
	 * Tweak 6 in stay-in-plan-mode-dynamic-adleman.md.
	 */
	search?: string;
	status?: string; // 'draft' | 'ready' | 'submitted' | 'locked' | 'withdrawn' | 'disabled'
	paid?: boolean;
	disabled?: boolean;
}

/** Pagination options. Omit both for "give me everything" (CSV export). */
export interface AdminEntriesPageOpts {
	limit?: number;
	offset?: number;
}

/** Paginated response from `GET /admin/entries`. */
export interface AdminEntriesPage {
	items: Entry[];
	total: number;
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
	filters: AdminEntryFiltersV2 = {},
	opts: AdminEntriesPageOpts = {}
): Promise<AdminEntriesPage> {
	const params = new URLSearchParams();
	if (filters.user_id) params.set('user_id', filters.user_id);
	if (filters.reference) params.set('reference', filters.reference);
	if (filters.search) params.set('search', filters.search);
	if (filters.status) params.set('status', filters.status);
	if (filters.paid !== undefined) params.set('paid', String(filters.paid));
	if (filters.disabled !== undefined) params.set('disabled', String(filters.disabled));
	if (filters.modified_within) params.set('modified_within', filters.modified_within);
	if (opts.limit !== undefined) params.set('limit', String(opts.limit));
	if (opts.offset !== undefined) params.set('offset', String(opts.offset));
	const qs = params.toString();
	const url = qs ? `/admin/entries?${qs}` : '/admin/entries';
	const raw = await api.get<unknown>(url);
	// Tolerate both shapes during rollout: the new backend returns
	// {items, total}; the old backend returns a bare Entry[]. Once the
	// backend change lands everywhere, drop the array branch.
	if (Array.isArray(raw)) {
		return { items: raw as Entry[], total: (raw as Entry[]).length };
	}
	return raw as AdminEntriesPage;
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

// ===========================================================================
// v2.157.0 — admin slide-over real prediction data (F1+F2+F3)
// ===========================================================================

/** One bonus answer with its question title resolved server-side. */
export interface AdminBonusAnswer {
	question_id: string;
	question_title: string;
	answer: string | null;
}

/** Aggregated bracket (mirrors backend `BracketPrediction`). */
export interface AdminBracketPrediction {
	group_winners: Record<string, string[]>;
	round_of_32: string[];
	round_of_16: string[];
	quarter_finals: string[];
	semi_finals: string[];
	final: string[];
	winner: string;
}

/** One round-trip payload for the slide-over Group / Knockout / Bonus tabs. */
export interface AdminEntryPredictions {
	match_predictions: Array<{
		id: string;
		fixture_id: string;
		home_score: number;
		away_score: number;
		phase: 'phase_1' | 'phase_2';
		locked_at: string | null;
		home_team: string | null;
		away_team: string | null;
		kickoff: string | null;
		is_locked: boolean;
	}>;
	bracket: AdminBracketPrediction | null;
	bonus_answers: AdminBonusAnswer[];
}

export async function getAdminEntryPredictions(
	entryId: string
): Promise<AdminEntryPredictions> {
	return api.get<AdminEntryPredictions>(
		`/admin/entries/${entryId}/predictions`
	);
}

// ===========================================================================
// v2.156.0 — admin redesign API additions
// ===========================================================================

export type UserCohort =
	| 'all'
	| 'active'
	| 'admins'
	| 'unpaid'
	| 'paid'
	| 'signed_up_only'
	| 'verified_only';

export interface AuditEventRead {
	id: string;
	event_type: string;
	actor_user_id: string | null;
	actor_name: string | null;
	actor_email: string | null;
	actor_role: string;
	subject_type: string | null;
	subject_id: string | null;
	ip_address: string | null;
	event_metadata: Record<string, unknown> | null;
	reason: string | null;
	created_at: string;
}

export interface AuditEventPage {
	rows: AuditEventRead[];
	total: number;
}

export interface UserAdminRowV2 {
	id: string;
	email: string;
	name: string | null;
	auth_provider: string;
	is_admin: boolean;
	is_active: boolean;
	paid: boolean;
	paid_to: string | null;
	employer: string | null;
	company_contact: string | null;
	cohort: UserCohort;
	entries_count: number;
	submitted_entries_count: number;
	draft_entries_count: number;
	prediction_count: number;
	last_login_at: string | null;
	last_activity_at: string | null;
	created_at: string;
}

export interface UserAdminPage {
	rows: UserAdminRowV2[];
	total: number;
}

export interface UserDetailRead extends UserAdminRowV2 {
	recent_activity: AuditEventRead[];
}

export interface EngagementSummary {
	last_seen: string | null;
	last_url: string | null;
	session_count: number;
	avg_session_seconds: number | null;
	sparkline_14d: number[];
}

export interface AuditFeedFilters {
	event_type?: string;
	namespace?: string;
	actor_user_id?: string;
	subject_id?: string;
	subject_type?: string;
	search?: string;
	since?: string;
	until?: string;
	limit?: number;
	offset?: number;
}

function buildQS(params: Record<string, unknown> | object): string {
	const p = params as Record<string, unknown>;
	const qs = new URLSearchParams();
	for (const [k, v] of Object.entries(p)) {
		if (v !== undefined && v !== null && v !== '') {
			qs.set(k, String(v));
		}
	}
	const s = qs.toString();
	return s ? '?' + s : '';
}

export async function getAuditFeed(
	filters: AuditFeedFilters = {}
): Promise<AuditEventPage> {
	return api.get<AuditEventPage>(`/admin/audit${buildQS(filters)}`);
}

export async function listUsersV2(opts: {
	cohort?: UserCohort;
	search?: string;
	limit?: number;
	offset?: number;
} = {}): Promise<UserAdminPage> {
	return api.get<UserAdminPage>(`/admin/users/list${buildQS(opts)}`);
}

export async function getUserDetail(userId: string): Promise<UserDetailRead> {
	return api.get<UserDetailRead>(`/admin/users/${userId}`);
}

export async function getUserEngagement(
	userId: string,
	days: number = 30
): Promise<EngagementSummary | null> {
	return api.get<EngagementSummary | null>(
		`/admin/users/${userId}/engagement?days=${days}`
	);
}

/**
 * Triggers the inactive-cohort CSV download in the browser. Opens the
 * URL directly because the response is a blob — fetch() + creating a
 * link works too, but a plain anchor click is simpler.
 */
export function downloadInactiveEmailsUrl(
	cohort: 'signed_up_only' | 'verified_only' | 'both' = 'both'
): string {
	return `/api/admin/users/inactive?cohort=${cohort}`;
}

export interface AdminEntryFiltersV2 extends AdminEntryFilters {
	/** New in v2.156.0: '1h' | '24h' | '7d' | '30d' */
	modified_within?: string;
}

// ---------------------------------------------------------------------------
// Broadcast emails (v2.160.0)
// ---------------------------------------------------------------------------

/** Mirrors the backend `BroadcastSegment` enum. */
export type BroadcastSegment = 'submitters' | 'no_entry' | 'draft_holders';

/** Live counts feed the badges on the broadcast card. */
export interface BroadcastAudienceCounts {
	submitters: number;
	no_entry: number;
	draft_holders: number;
}

/** Result of a single-recipient test send. */
export interface BroadcastTestResult {
	sent: boolean;
	to_email: string;
	error: string | null;
}

/** Result of a real (or dry-run) broadcast send.
 *
 * `sample_emails` carries different things depending on `dry_run`:
 *  - dry_run=true: first 5 recipient emails (preview for the modal)
 *  - dry_run=false: first 3 FAILED recipient emails (error spot-check)
 */
export interface BroadcastSendResult {
	dry_run: boolean;
	segment: BroadcastSegment;
	audience_count: number;
	sent: number;
	failed: number;
	sample_emails: string[];
}

export async function getBroadcastAudienceCounts(): Promise<BroadcastAudienceCounts> {
	return api.get<BroadcastAudienceCounts>('/admin/broadcasts/audience');
}

export async function sendBroadcastTest(
	segment: BroadcastSegment,
	toEmail?: string
): Promise<BroadcastTestResult> {
	return api.post<BroadcastTestResult>('/admin/broadcasts/test', {
		segment,
		to_email: toEmail ?? null
	});
}

export async function sendBroadcast(
	segment: BroadcastSegment,
	dryRun: boolean
): Promise<BroadcastSendResult> {
	return api.post<BroadcastSendResult>('/admin/broadcasts', {
		segment,
		dry_run: dryRun
	});
}
