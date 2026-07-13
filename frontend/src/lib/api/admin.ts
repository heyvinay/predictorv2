/**
 * Admin API functions.
 */

import { api, ApiResponseError } from './client';
import type { EntryCompletenessResult } from '$lib/types/admin';
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
	/** Rows left untouched because an admin verified the score via the
	 *  /admin/sync editor (manual scores are locked against the API). */
	skipped_verified: number;
	errors: string[];
}

/** v2.160.5 — drives the /admin/entries stat cards (Total / Submitted /
 *  Paid / Disabled-Withdrawn). All counts are GLOBAL to the active
 *  competition; the page's table filter/paging state does NOT affect
 *  them. Replaces the per-page-derived counts that capped at 100. */
export interface AdminEntriesStatsResponse {
	total: number;
	submitted: number;
	drafts: number;
	paid: number;
	disabled_or_withdrawn: number;
}

export async function getAdminStats(): Promise<AdminStats> {
	return api.get<AdminStats>('/admin/stats');
}

/** Fetch global entry-state breakdown for the active competition.
 *  Used by /admin/entries stat cards. */
export async function getAdminEntriesStats(): Promise<AdminEntriesStatsResponse> {
	return api.get<AdminEntriesStatsResponse>('/admin/entries/stats');
}

/** Trigger a browser download of the full admin entries CSV export
 *  (v2.160.6). The JSON ApiClient is wrong for this — we need the raw
 *  response body, not a parsed JSON — so we fetch manually with the
 *  same Bearer token, blob it, and trigger a download via a synthetic
 *  <a> click. Filename comes from the server's Content-Disposition;
 *  falls back to a date-stamped default. */
export async function downloadAdminEntriesCsv(): Promise<void> {
	// Pull the live token off the ApiClient instance — same way every
	// other call authenticates. Reading via a tiny `_token` shim is
	// brittle, so use the public `get` for type+url consistency but
	// branch into a raw fetch since the body isn't JSON.
	const url = '/api/admin/entries/export.csv';
	const tokenRaw = (api as unknown as { token: string | null }).token;
	const headers: Record<string, string> = {};
	if (tokenRaw) headers['Authorization'] = `Bearer ${tokenRaw}`;

	const response = await fetch(url, { method: 'GET', headers });
	if (!response.ok) {
		// Match ApiResponseError's contract so callers can catch uniformly.
		const body = await response
			.json()
			.catch(() => ({ detail: `HTTP ${response.status}: ${response.statusText}` }));
		throw new ApiResponseError(response.status, body.detail, body);
	}

	const blob = await response.blob();

	// Derive filename from Content-Disposition header if present, else fall
	// back to a date-stamped default so the user always gets something useful.
	const cd = response.headers.get('Content-Disposition') ?? '';
	const match = cd.match(/filename="?([^"]+)"?/i);
	const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
	const filename = match?.[1] ?? `entries-${today}.csv`;

	const objectUrl = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = objectUrl;
	a.download = filename;
	document.body.appendChild(a);
	a.click();
	a.remove();
	// Revoke after a tick — some browsers race the navigation otherwise.
	setTimeout(() => URL.revokeObjectURL(objectUrl), 100);
}

export async function getCompetitions(): Promise<CompetitionAdminView[]> {
	return api.get<CompetitionAdminView[]>('/admin/competitions');
}

export async function setPhase1Deadline(deadline: string): Promise<{ status: string; deadline: string }> {
	return api.post('/admin/competition/phase1/deadline', { deadline });
}

/** Flip the post-deadline release switch (v2.166.0) — opens/closes the
 *  V4 dashboard, results and leaderboard for the whole pool. */
export async function setPostDeadlineLive(
	live: boolean
): Promise<{ status: string; post_deadline_live: boolean }> {
	return api.post('/admin/competition/go-live', { live });
}

/** Flip the Group Stage Winner release switch (v2.181.0) — exposes the
 *  GroupStageWinnerCard on the dashboard AND surfaces real data in
 *  the GROUP_STAGE_FINAL broadcast template. */
export async function setGroupStageWinnerReleased(
	released: boolean
): Promise<{ status: string; group_stage_winner_released: boolean }> {
	return api.post('/admin/competition/group-stage-winner/release', { released });
}

/** Flip the knockout-scoring gate (v2.181.1). When enabled=true the
 *  scoring engine starts paying out advancement points (group_advance
 *  / group_position bracket credits AND R32→winner credits). The
 *  leaderboard cache hard-invalidates on the same commit, so every
 *  entry's score rebuilds on next read. */
export async function setKnockoutScoringEnabled(
	enabled: boolean
): Promise<{ status: string; knockout_scoring_enabled: boolean }> {
	return api.post('/admin/competition/knockout-scoring', { enabled });
}

/** Flip the live-projection master switch (v2.198.0). When enabled=true
 *  (AND knockout_scoring_enabled is also true AND a knockout match is
 *  currently live), GET /leaderboard/ layers a provisional advancement
 *  projection onto the banked board. Read-time only — no cache
 *  invalidation happens on this toggle. */
export async function setLiveProjectionEnabled(
	enabled: boolean
): Promise<{ status: string; live_projection_enabled: boolean }> {
	return api.post('/admin/competition/live-projection', { enabled });
}

/** Flip the Win Probability tab's master switch. Read-time gate — no
 *  cache invalidation happens on this toggle; GET /leaderboard/
 *  win-probability checks it fresh on every request. */
export async function setWinProbabilityEnabled(
	enabled: boolean
): Promise<{ status: string; win_probability_enabled: boolean }> {
	return api.post('/admin/competition/win-probability', { enabled });
}

/** Flip the what-if bracket simulator's admin master switch (v2.194.x).
 *  When `enabled=false`, non-admins can't reach `/simulator/*` even if
 *  they've already completed the trivia unlock — admins always retain
 *  full access regardless of this flag (see backend
 *  app/services/simulator.py). Current state is read via
 *  `getSimulatorStatus().feature_enabled` (api/simulator.ts) — there's
 *  no dedicated GET here, mirroring how other admin toggles source
 *  their initial value from the feature's own status endpoint rather
 *  than a competition-settings read. */
export async function setSimulatorEnabled(
	enabled: boolean
): Promise<{ status: string; simulator_enabled: boolean }> {
	return api.post('/admin/competition/simulator-enabled', { enabled });
}

/** Standings drift verification (v2.182.0). */
export interface DriftCheckResult {
	source_used: 'FOOTBALL_DATA' | 'ESPN' | 'WIKIPEDIA' | null;
	disagreement_count: number;
	created_event_id: string | null;
}

export interface DriftEvent {
	id: string;
	competition_id: string;
	detected_at: string;
	trusted_source: 'FOOTBALL_DATA' | 'ESPN' | 'WIKIPEDIA';
	status:
		| 'OPEN'
		| 'DISMISSED_OURS_CORRECT'
		| 'DISMISSED_TRANSIENT'
		| 'RESOLVED_VIA_SCORE_EDIT';
	disagreement_count: number;
	groups_disagreeing: { groups?: Record<string, { ours: unknown[]; theirs: unknown[] }> };
	resolved_at: string | null;
	resolution_note: string | null;
}

export async function triggerStandingsDriftCheck(): Promise<DriftCheckResult> {
	return api.post('/admin/standings-drift/check', {});
}

export async function listOpenDriftEvents(): Promise<DriftEvent[]> {
	return api.get<DriftEvent[]>('/admin/standings-drift/open');
}

export async function dismissDriftEvent(
	eventId: string,
	resolution: 'DISMISSED_OURS_CORRECT' | 'DISMISSED_TRANSIENT' | 'RESOLVED_VIA_SCORE_EDIT',
	note?: string
): Promise<{ status: string; event_id: string; resolution: string }> {
	return api.post(`/admin/standings-drift/${eventId}/dismiss`, {
		status: resolution,
		note: note ?? null
	});
}

/** Close-the-pool dry-run counts (v2.166.0). */
export interface PoolClosePreview {
	deadline_passed: boolean;
	accounts_to_disable: number;
	submitters_kept: number;
	admins_exempt: number;
	already_inactive: number;
	drafts_withdrawn: number;
	eligible_submitted_entries: number;
}

export async function getPoolClosePreview(): Promise<PoolClosePreview> {
	return api.get<PoolClosePreview>('/admin/close-pool/preview');
}

/** Disable every account without a counting submission (admins exempt,
 *  post-deadline only, idempotent, audited). */
export async function runPoolClose(): Promise<{ disabled_count: number }> {
	return api.post('/admin/close-pool');
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
	| 'verified_only'
	| 'no_submission';

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

/** Mirrors the backend `BroadcastSegment` enum.
 *  v2.176.0 — added `pool_ghost` and `lapsing` cohorts.
 *  v2.178.0 — added `group_r1_recap` one-off round-recap broadcast.
 *  v2.180.0 — added `group_r2_recap` Round 2 recap.
 *  v2.181.0 — added `group_stage_final` champion announcement.
 *  v2.195.0 — added `group_r32_recap` Round of 32 knockout recap.
 *  v2.209.0 — added `group_r16_recap` Round of 16 knockout recap. */
export type BroadcastSegment =
	| 'submitters'
	| 'no_entry'
	| 'draft_holders'
	| 'pool_ghost'
	| 'lapsing'
	| 'group_r1_recap'
	| 'group_r2_recap'
	| 'group_stage_final'
	| 'group_r32_recap'
	| 'group_r16_recap';

/** Live counts feed the badges on the broadcast card. */
export interface BroadcastAudienceCounts {
	submitters: number;
	no_entry: number;
	draft_holders: number;
	pool_ghost: number;          // NEW v2.176.0
	lapsing: number;             // NEW v2.176.0
	group_r1_recap: number;      // NEW v2.178.0
	group_r2_recap: number;      // NEW v2.180.0
	group_stage_final: number;   // NEW v2.181.0
	group_r32_recap: number;     // NEW v2.195.0
	group_r16_recap: number;     // NEW v2.209.0
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

// ---------------------------------------------------------------------------
// Site Pulse (v2.176.0) — /admin Overview "Site Pulse" panel
// ---------------------------------------------------------------------------

/** One bar of the 14-day DAU sparkline. `date` is ISO YYYY-MM-DD. */
export interface DauPoint {
	date: string;
	count: number;
}

/** One Top-5 pages row. Frontend derives the trend indicator from the
 *  two counts. */
export interface PageTrend {
	path: string;
	current_7d: number;
	prior_7d: number;
}

/** One Top-5 events row. */
export interface EventTrend {
	event_name: string;
	current_7d: number;
	prior_7d: number;
}

/** One Recent-Logins row. */
export interface RecentLogin {
	user_id: string;
	name: string;
	login_at: string;       // ISO timestamp
}

/** Aggregate /admin/pulse response — four widgets in one shot. */
export interface SitePulse {
	dau_sparkline: DauPoint[];
	top_pages: PageTrend[];
	top_events: EventTrend[];
	recent_logins: RecentLogin[];
}

export async function getSitePulse(): Promise<SitePulse> {
	return api.get<SitePulse>('/admin/pulse');
}

// --- Usage & Adoption dashboard (v2.212.0, /admin/usage) ---
// A deliberately separate, more analytical surface from Site Pulse
// above — see docs/superpowers/specs/2026-07-13-usage-adoption-dashboard-design.md.

export type UsageRange = '1h' | '24h' | '7d' | '30d' | 'all';
export type UsageGranularity = 'hour' | 'day' | 'week';
export type UsageSegment = 'all' | 'atlas' | 'jmfa' | 'neither';

export interface UsageFunnel {
	submitters: number;
	no_entry: number;
	draft_holders: number;
	pool_ghost: number;
	lapsing: number;
}

export interface UsageKpi {
	key: string;
	label: string;
	value: number | null;
	suffix: string;
	delta_pct: number | null;
	sparkline: number[];
}

export interface UsageSeriesPoint {
	bucket: string;
	count: number;
}

export interface UsageRetentionCohort {
	cohort_week: string;
	pct_by_offset: (number | null)[];
}

export interface UsageFrequencyBucket {
	label: string;
	count: number;
	is_power: boolean;
	is_dormant: boolean;
}

export interface UsageFeatureAdoption {
	key: string;
	name: string;
	sub: string;
	users: number;
	pct: number;
	last_used: string | null; // ISO timestamp
	frozen: boolean;
	rarely_used: boolean;
}

export interface UsageUncategorizedEvent {
	name: string;
	count: number;
	last_seen: string | null;
}

export interface UsagePowerUser {
	user_id: string;
	name: string;
	logins: number;
	active_days: number;
	sessions: number;
	last_seen_at: string | null;
}

export interface UsageFeatureAdopter {
	user_id: string;
	name: string;
	last_used: string | null;
}

/** Aggregate /admin/usage response — every widget on the page in one shot. */
export interface UsageReport {
	range: UsageRange;
	granularity: UsageGranularity;
	segment: UsageSegment;
	posthog_available: boolean;
	funnel: UsageFunnel;
	kpis: UsageKpi[];
	active_users_series: UsageSeriesPoint[];
	time_of_day: number[];
	retention_cohorts: UsageRetentionCohort[];
	frequency_buckets: UsageFrequencyBucket[];
	feature_adoption: UsageFeatureAdoption[];
	uncategorized_events: UsageUncategorizedEvent[];
	power_users_most_active: UsagePowerUser[];
	power_users_least_active: UsagePowerUser[];
	power_users_never_engaged: UsagePowerUser[];
}

export async function getUsageReport(params: {
	range?: UsageRange;
	granularity?: UsageGranularity;
	segment?: UsageSegment;
}): Promise<UsageReport> {
	const qs = new URLSearchParams();
	if (params.range) qs.set('range', params.range);
	if (params.granularity) qs.set('granularity', params.granularity);
	if (params.segment) qs.set('segment', params.segment);
	return api.get<UsageReport>(`/admin/usage?${qs.toString()}`);
}

export async function getUsageFeatureAdopters(
	key: string,
	params: { range?: UsageRange; segment?: UsageSegment } = {}
): Promise<UsageFeatureAdopter[]> {
	const qs = new URLSearchParams();
	if (params.range) qs.set('range', params.range);
	if (params.segment) qs.set('segment', params.segment);
	return api.get<UsageFeatureAdopter[]>(
		`/admin/usage/features/${key}/adopters?${qs.toString()}`
	);
}

// --- Usage & Adoption click-through drill-downs (v2.213.0) ---
// "Who's behind this number?" — a generic row shape shared by the
// day-bucket, hour-of-day, frequency-bucket, and funnel-cohort
// drawers. Exactly one of last_used / detail is normally populated.

export interface UsageDrillUser {
	user_id: string;
	name: string;
	last_used: string | null;
	detail: string | null;
}

export interface UserFeatureUsage {
	key: string;
	name: string;
	sub: string;
	count: number;
	last_used: string | null;
	frozen: boolean;
}

export async function getUsageDayUsers(
	bucket: string,
	params: { granularity?: UsageGranularity; segment?: UsageSegment } = {}
): Promise<UsageDrillUser[]> {
	const qs = new URLSearchParams({ bucket });
	if (params.granularity) qs.set('granularity', params.granularity);
	if (params.segment) qs.set('segment', params.segment);
	return api.get<UsageDrillUser[]>(`/admin/usage/day-users?${qs.toString()}`);
}

export async function getUsageHourUsers(
	hour: number,
	params: { range?: UsageRange; segment?: UsageSegment } = {}
): Promise<UsageDrillUser[]> {
	const qs = new URLSearchParams({ hour: String(hour) });
	if (params.range) qs.set('range', params.range);
	if (params.segment) qs.set('segment', params.segment);
	return api.get<UsageDrillUser[]>(`/admin/usage/hour-users?${qs.toString()}`);
}

export async function getUsageFrequencyUsers(
	bucket: string,
	params: { range?: UsageRange; segment?: UsageSegment } = {}
): Promise<UsageDrillUser[]> {
	const qs = new URLSearchParams({ bucket });
	if (params.range) qs.set('range', params.range);
	if (params.segment) qs.set('segment', params.segment);
	return api.get<UsageDrillUser[]>(`/admin/usage/frequency-users?${qs.toString()}`);
}

export async function getUsageFunnelUsers(cohort: string): Promise<UsageDrillUser[]> {
	const qs = new URLSearchParams({ cohort });
	return api.get<UsageDrillUser[]>(`/admin/usage/funnel-users?${qs.toString()}`);
}

export async function getUsageUserFeatures(
	userId: string,
	params: { range?: UsageRange } = {}
): Promise<UserFeatureUsage[]> {
	const qs = new URLSearchParams();
	if (params.range) qs.set('range', params.range);
	return api.get<UserFeatureUsage[]>(
		`/admin/usage/users/${userId}/features?${qs.toString()}`
	);
}

// --- Entry completeness check (E.1, v2.163.0) ---


/** GET /api/admin/entries/completeness-check — pick fullness for every
 *  eligible entry. Returns ALL eligible entries; callers filter to
 *  incompletes for display. */
export async function fetchCompletenessCheck(
	detail = false
): Promise<EntryCompletenessResult[]> {
	const url = detail
		? '/admin/entries/completeness-check?detail=true'
		: '/admin/entries/completeness-check';
	return api.get<EntryCompletenessResult[]>(url);
}

/** Download the incompletes-only CSV. Same raw-fetch + blob pattern as
 *  downloadAdminEntriesCsv above — the body isn't JSON and the request
 *  must carry the Bearer token (plain navigation would 401). */
export async function downloadCompletenessCsv(): Promise<void> {
	const url = '/api/admin/entries/completeness-check.csv';
	const tokenRaw = (api as unknown as { token: string | null }).token;
	const headers: Record<string, string> = {};
	if (tokenRaw) headers['Authorization'] = `Bearer ${tokenRaw}`;

	const response = await fetch(url, { method: 'GET', headers });
	if (!response.ok) {
		const body = await response
			.json()
			.catch(() => ({ detail: `HTTP ${response.status}: ${response.statusText}` }));
		throw new ApiResponseError(response.status, body.detail, body);
	}

	const blob = await response.blob();
	const cd = response.headers.get('Content-Disposition') ?? '';
	const match = cd.match(/filename="?([^"]+)"?/i);
	const today = new Date().toISOString().slice(0, 10);
	const filename = match?.[1] ?? `entry-completeness-${today}.csv`;

	const objectUrl = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = objectUrl;
	a.download = filename;
	document.body.appendChild(a);
	a.click();
	a.remove();
	setTimeout(() => URL.revokeObjectURL(objectUrl), 100);
}
