<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import {
		fetchPhaseStatus,
		isPhase2Active,
		phase1Deadline,
		phase2BracketDeadline,
		phase1Countdown,
		phase2Countdown
	} from '$stores/phase';
	import {
		getAdminStats,
		getCompetitions,
		setPhase1Deadline,
		activatePhase2,
		deactivatePhase2,
		getAllUsers,
		toggleUserAdmin,
		toggleUserActive,
		toggleUserPaid,
		getPaidLocal,
		syncScores,
		getAdminEntrySettings,
		updateAdminEntrySettings,
		openPhase2,
		adminListEntries,
		getAdminEntryEvents,
		adminDisableEntry,
		adminEnableEntry,
		adminSetEntryPaid,
		adminSetEntryPrizeEligible,
		type AdminStats,
		type CompetitionAdminView,
		type UserAdminView,
		type SyncScoresResponse,
		type AdminEntryFilters,
		type EntryEvent,
		type EntrySettingsUpdate,
		type Phase2OpenResponse
	} from '$lib/api/admin';
	import { listBonusAnswers, setBonusAnswer, type BonusAnswerView } from '$api/bonus';
	import type { Entry, EntrySettings, EntryStatus, PaymentMode } from '$lib/types/entry';
	import { computeDisplayStatus } from '$lib/types/entry';
	import type { PredictionPhase } from '$types';
	import PnPageShell from '$components/panini/PnPageShell.svelte';

	$: if ($isAuthenticated && !$user?.is_admin) goto('/');
	$: if (!$isAuthenticated) goto('/login');

	let stats: AdminStats | null = null;
	let competitions: CompetitionAdminView[] = [];
	let users: UserAdminView[] = [];
	let loading = true;
	let error: string | null = null;

	let phase1DeadlineDate = '';
	let phase1DeadlineTime = '12:00';
	let settingPhase1 = false;
	let phase1Error: string | null = null;
	let phase1Success: string | null = null;

	let bracketDeadlineDate = '';
	let bracketDeadlineTime = '12:00';
	let activating = false;
	let activationError: string | null = null;
	let activationSuccess: string | null = null;

	let syncing = false;
	let syncResult: SyncScoresResponse | null = null;
	let syncedAt: Date | null = null;
	let syncError: string | null = null;

	let userSearch = '';
	let togglingUserId: string | null = null;
	let userActionError: string | null = null;

	// --- F.2: Competition entry settings (the 11-field form) -----------------
	type BoolSettingKey =
		| 'auto_create_first_entry'
		| 'allow_duplicate_from_existing'
		| 'allow_user_rename'
		| 'allow_user_withdrawal'
		| 'require_ready_before_submit'
		| 'block_unpaid_entry_submission'
		| 'show_entry_reference_publicly'
		| 'phase_scoped_status_enabled'
		| 'bonus_questions_required_for_ready';
	const BOOL_SETTINGS: { key: BoolSettingKey; label: string }[] = [
		{ key: 'auto_create_first_entry', label: "Auto-create user's first entry" },
		{ key: 'allow_duplicate_from_existing', label: 'Allow duplicate from existing' },
		{ key: 'allow_user_rename', label: 'Allow users to rename entries' },
		{ key: 'allow_user_withdrawal', label: 'Allow users to withdraw entries' },
		{ key: 'require_ready_before_submit', label: 'Require READY before SUBMIT' },
		{ key: 'block_unpaid_entry_submission', label: 'Block unpaid entry submission' },
		{ key: 'show_entry_reference_publicly', label: 'Show entry reference publicly' },
		{ key: 'phase_scoped_status_enabled', label: 'Per-phase status (vs. competition-wide)' },
		{ key: 'bonus_questions_required_for_ready', label: 'Bonus questions required for READY' }
	];

	let entrySettings: EntrySettings | null = null;
	let settingsDraft: EntrySettings | null = null;
	let settingsLoading = false;
	let settingsSaving = false;
	let settingsError: string | null = null;
	let settingsSuccess: string | null = null;

	$: settingsDirty = (() => {
		if (!entrySettings || !settingsDraft) return false;
		const keys = Object.keys(entrySettings) as (keyof EntrySettings)[];
		return keys.some((k) => entrySettings![k] !== settingsDraft![k]);
	})();

	// --- F.2: Phase II open ---------------------------------------------------
	let openingPhase2 = false;
	let phase2OpenResult: Phase2OpenResponse | null = null;
	let phase2OpenError: string | null = null;

	// --- F.2: Entries admin table --------------------------------------------
	let entries: Entry[] = [];
	let entriesLoading = false;
	let entriesError: string | null = null;
	let entryFilters: AdminEntryFilters = {};
	let entryUserSearch = '';
	let entryRefSearch = '';
	let entryStatusFilter: '' | EntryStatus = '';
	let entryPaidFilter: '' | 'paid' | 'unpaid' = '';
	let entryDisabledFilter: '' | 'disabled' | 'active' = '';

	let entryActionError: string | null = null;
	let entryActingId: string | null = null;

	// Audit drawer state. `auditEntryId` is the currently-open entry; null
	// means the drawer is closed.
	let auditEntryId: string | null = null;
	let auditEvents: EntryEvent[] = [];
	let auditLoading = false;
	let auditError: string | null = null;

	// Disable dialog state. We use a tiny inline form rather than
	// window.prompt so the admin can paste a multi-word reason cleanly.
	let disableTargetId: string | null = null;
	let disableReason = '';

	function setBoolSetting(key: BoolSettingKey, checked: boolean) {
		if (!settingsDraft) return;
		settingsDraft[key] = checked;
		settingsDraft = settingsDraft;
	}

	async function loadEntrySettings() {
		settingsLoading = true;
		settingsError = null;
		try {
			const next = await getAdminEntrySettings();
			entrySettings = next;
			settingsDraft = { ...next };
		} catch (e) {
			settingsError = e instanceof Error ? e.message : 'Failed to load entry settings';
		} finally {
			settingsLoading = false;
		}
	}

	async function handleSaveSettings() {
		if (!entrySettings || !settingsDraft) return;
		// Build a partial patch — only changed fields go up. Keeps the audit
		// log clean and matches the backend's exclude_unset semantics.
		const patch: EntrySettingsUpdate = {};
		const keys = Object.keys(entrySettings) as (keyof EntrySettings)[];
		for (const k of keys) {
			if (entrySettings[k] !== settingsDraft[k]) {
				// eslint-disable-next-line @typescript-eslint/no-explicit-any
				(patch as any)[k] = settingsDraft[k];
			}
		}
		if (Object.keys(patch).length === 0) return;

		settingsSaving = true;
		settingsError = null;
		settingsSuccess = null;
		try {
			const next = await updateAdminEntrySettings(patch);
			entrySettings = next;
			settingsDraft = { ...next };
			settingsSuccess = 'Entry settings saved';
			setTimeout(() => (settingsSuccess = null), 3000);
		} catch (e) {
			settingsError = e instanceof Error ? e.message : 'Failed to save settings';
		} finally {
			settingsSaving = false;
		}
	}

	function handleResetSettings() {
		if (entrySettings) settingsDraft = { ...entrySettings };
		settingsError = null;
		settingsSuccess = null;
	}

	async function handleOpenPhase2() {
		const ok = confirm(
			'Open Phase II for all eligible entries? This advances each ' +
				"submitted/locked entry's Phase 2 row to allow new picks. " +
				'Audit-logged. Continue?'
		);
		if (!ok) return;
		openingPhase2 = true;
		phase2OpenError = null;
		phase2OpenResult = null;
		try {
			phase2OpenResult = await openPhase2();
			// Refresh entries list so the new phase rows surface.
			await loadEntries();
		} catch (e) {
			phase2OpenError = e instanceof Error ? e.message : 'Failed to open Phase II';
		} finally {
			openingPhase2 = false;
		}
	}

	function buildFilters(): AdminEntryFilters {
		const f: AdminEntryFilters = {};
		// User search hits both name and email client-side; the backend filter
		// takes user_id, so we only set it once the search resolves to a
		// unique match. Otherwise we filter the response client-side too.
		if (entryRefSearch.trim()) f.reference = entryRefSearch.trim();
		if (entryStatusFilter) f.status = entryStatusFilter;
		if (entryPaidFilter === 'paid') f.paid = true;
		else if (entryPaidFilter === 'unpaid') f.paid = false;
		if (entryDisabledFilter === 'disabled') f.disabled = true;
		else if (entryDisabledFilter === 'active') f.disabled = false;
		return f;
	}

	async function loadEntries() {
		entriesLoading = true;
		entriesError = null;
		try {
			entryFilters = buildFilters();
			entries = await adminListEntries(entryFilters);
		} catch (e) {
			entriesError = e instanceof Error ? e.message : 'Failed to load entries';
		} finally {
			entriesLoading = false;
		}
	}

	function userNameById(userId: string): string {
		const u = users.find((x) => x.id === userId);
		return u?.name ?? userId.slice(0, 8);
	}

	function userEmailById(userId: string): string {
		const u = users.find((x) => x.id === userId);
		return u?.email ?? '—';
	}

	$: visibleEntries = (() => {
		if (!entryUserSearch.trim()) return entries;
		const q = entryUserSearch.trim().toLowerCase();
		return entries.filter((e) => {
			const u = users.find((x) => x.id === e.user_id);
			if (!u) return false;
			return u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q);
		});
	})();

	function entryDisplayStatus(e: Entry): EntryStatus {
		// Show the dominant status. Phase 1 is the default lens since the
		// admin usually wants to know "is this entry locked in for the
		// group stage?". Disabled / withdrawn already win in computeDisplayStatus.
		return computeDisplayStatus(e, 'phase_1' as PredictionPhase);
	}

	function statusChipClass(s: EntryStatus): string {
		switch (s) {
			case 'submitted':
			case 'locked':
				return 'pn-tag got';
			case 'ready':
				return 'pn-tag gold';
			case 'disabled':
				return 'pn-tag red';
			case 'withdrawn':
				return 'pn-tag'; // muted default
			default:
				return 'pn-tag';
		}
	}

	async function handleEntryTogglePaid(e: Entry) {
		entryActingId = e.id;
		entryActionError = null;
		try {
			const updated = await adminSetEntryPaid(e.id, !e.paid);
			entries = entries.map((x) => (x.id === updated.id ? updated : x));
		} catch (err) {
			entryActionError = err instanceof Error ? err.message : 'Failed to update paid';
		} finally {
			entryActingId = null;
		}
	}

	async function handleEntryTogglePrize(e: Entry) {
		entryActingId = e.id;
		entryActionError = null;
		try {
			const updated = await adminSetEntryPrizeEligible(e.id, !e.prize_eligible);
			entries = entries.map((x) => (x.id === updated.id ? updated : x));
		} catch (err) {
			entryActionError = err instanceof Error ? err.message : 'Failed to update prize eligibility';
		} finally {
			entryActingId = null;
		}
	}

	function openDisableDialog(e: Entry) {
		disableTargetId = e.id;
		disableReason = '';
	}

	function closeDisableDialog() {
		disableTargetId = null;
		disableReason = '';
	}

	async function handleConfirmDisable() {
		if (!disableTargetId) return;
		const reason = disableReason.trim();
		if (!reason) {
			entryActionError = 'A reason is required to disable an entry';
			return;
		}
		entryActingId = disableTargetId;
		entryActionError = null;
		try {
			const updated = await adminDisableEntry(disableTargetId, reason);
			entries = entries.map((x) => (x.id === updated.id ? updated : x));
			closeDisableDialog();
		} catch (err) {
			entryActionError = err instanceof Error ? err.message : 'Failed to disable entry';
		} finally {
			entryActingId = null;
		}
	}

	async function handleEnable(e: Entry) {
		entryActingId = e.id;
		entryActionError = null;
		try {
			const updated = await adminEnableEntry(e.id);
			entries = entries.map((x) => (x.id === updated.id ? updated : x));
		} catch (err) {
			entryActionError = err instanceof Error ? err.message : 'Failed to enable entry';
		} finally {
			entryActingId = null;
		}
	}

	async function openAuditDrawer(entryId: string) {
		auditEntryId = entryId;
		auditLoading = true;
		auditError = null;
		auditEvents = [];
		try {
			auditEvents = await getAdminEntryEvents(entryId);
		} catch (err) {
			auditError = err instanceof Error ? err.message : 'Failed to load audit log';
		} finally {
			auditLoading = false;
		}
	}

	function closeAuditDrawer() {
		auditEntryId = null;
		auditEvents = [];
		auditError = null;
	}

	function fmtAuditTime(iso: string): string {
		try {
			return new Date(iso).toLocaleString('en-GB', {
				day: 'numeric',
				month: 'short',
				hour: '2-digit',
				minute: '2-digit'
			});
		} catch {
			return iso;
		}
	}

	// Bonus question answers admin state
	let bonusAnswerViews: BonusAnswerView[] = [];
	let bonusDrafts: Map<string, string> = new Map(); // question_id → draft input
	let savingQId: string | null = null;
	let bonusError: string | null = null;

	async function loadBonusAnswers() {
		try {
			bonusAnswerViews = await listBonusAnswers();
		} catch (e) {
			bonusError = e instanceof Error ? e.message : 'Failed to load bonus answers';
		}
	}

	function draftFor(view: BonusAnswerView): string {
		return bonusDrafts.get(view.question_id) ?? view.correct_answer ?? '';
	}

	function setDraft(qid: string, value: string) {
		const next = new Map(bonusDrafts);
		next.set(qid, value);
		bonusDrafts = next;
	}

	async function handleSaveBonusAnswer(view: BonusAnswerView) {
		const value = draftFor(view).trim();
		savingQId = view.question_id;
		bonusError = null;
		try {
			const updated = await setBonusAnswer(view.question_id, value);
			bonusAnswerViews = bonusAnswerViews.map((v) =>
				v.question_id === view.question_id ? updated : v
			);
			// Clear the draft so the input now reflects the saved value.
			const next = new Map(bonusDrafts);
			next.delete(view.question_id);
			bonusDrafts = next;
		} catch (e) {
			bonusError = e instanceof Error ? e.message : 'Failed to save bonus answer';
		} finally {
			savingQId = null;
		}
	}

	$: bonusByCategory = (() => {
		const groups: Record<string, BonusAnswerView[]> = {
			group_stage: [],
			top_flop: [],
			awards: []
		};
		for (const v of bonusAnswerViews) {
			(groups[v.category] ?? (groups[v.category] = [])).push(v);
		}
		return groups;
	})();

	const BONUS_CATEGORY_LABEL: Record<string, string> = {
		group_stage: 'Group stage',
		top_flop: 'Top / Flop',
		awards: 'Awards'
	};

	function fmtResolved(iso: string | null): string {
		if (!iso) return 'Not resolved';
		const d = new Date(iso);
		return `Resolved ${d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`;
	}

	onMount(async () => {
		if ($user?.is_admin) {
			await loadData();
			await Promise.all([loadBonusAnswers(), loadEntrySettings(), loadEntries()]);
		}
	});

	async function loadData() {
		loading = true;
		error = null;
		try {
			[stats, competitions, users] = await Promise.all([
				getAdminStats(),
				getCompetitions(),
				getAllUsers()
			]);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load admin data';
		} finally {
			loading = false;
		}
	}

	async function handleSyncScores() {
		syncing = true;
		syncResult = null;
		syncError = null;
		try {
			syncResult = await syncScores();
			syncedAt = new Date();
			await loadData();
		} catch (e) {
			syncError = e instanceof Error ? e.message : 'Failed to sync scores';
		} finally {
			syncing = false;
		}
	}

	async function handleToggleAdmin(u: UserAdminView) {
		const action = u.is_admin ? 'remove admin from' : 'grant admin to';
		if (!confirm(`Are you sure you want to ${action} ${u.name}?`)) return;
		togglingUserId = u.id;
		userActionError = null;
		try {
			const updated = await toggleUserAdmin(u.id);
			users = users.map((x) => (x.id === updated.id ? updated : x));
		} catch (e) {
			userActionError = e instanceof Error ? e.message : 'Failed to update admin status';
		} finally {
			togglingUserId = null;
		}
	}

	async function handleTogglePaid(u: UserAdminView) {
		togglingUserId = u.id;
		userActionError = null;
		try {
			const next = await toggleUserPaid(u.id);
			users = users.map((x) => (x.id === u.id ? { ...x, paid: next } : x));
		} catch (e) {
			userActionError = e instanceof Error ? e.message : 'Failed to update paid status';
		} finally {
			togglingUserId = null;
		}
	}

	/** Effective paid state for a user — backend value if present, else localStorage. */
	function paidOf(u: UserAdminView): boolean {
		return u.paid ?? getPaidLocal(u.id);
	}

	async function handleToggleActive(u: UserAdminView) {
		const action = u.is_active ? 'deactivate' : 'reactivate';
		if (!confirm(`Are you sure you want to ${action} ${u.name}?`)) return;
		togglingUserId = u.id;
		userActionError = null;
		try {
			const updated = await toggleUserActive(u.id);
			users = users.map((x) => (x.id === updated.id ? updated : x));
		} catch (e) {
			userActionError = e instanceof Error ? e.message : 'Failed to update active status';
		} finally {
			togglingUserId = null;
		}
	}

	$: filteredUsers = userSearch.trim()
		? users.filter((u) => {
				const q = userSearch.toLowerCase();
				return u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q);
			})
		: users;

	async function handleSetPhase1Deadline() {
		if (!phase1DeadlineDate) {
			phase1Error = 'Please select a deadline date';
			return;
		}
		settingPhase1 = true;
		phase1Error = null;
		phase1Success = null;
		try {
			const deadline = `${phase1DeadlineDate}T${phase1DeadlineTime}:00`;
			const result = await setPhase1Deadline(deadline);
			phase1Success = `Phase 1 deadline set: ${new Date(result.deadline).toLocaleString()}`;
			await Promise.all([loadData(), fetchPhaseStatus()]);
		} catch (e) {
			phase1Error = e instanceof Error ? e.message : 'Failed to set Phase 1 deadline';
		} finally {
			settingPhase1 = false;
		}
	}

	async function handleActivatePhase2() {
		if (!bracketDeadlineDate) {
			activationError = 'Please select a deadline date';
			return;
		}
		activating = true;
		activationError = null;
		activationSuccess = null;
		try {
			const deadline = `${bracketDeadlineDate}T${bracketDeadlineTime}:00`;
			const result = await activatePhase2(deadline);
			activationSuccess = `Phase 2 activated! Bracket deadline: ${new Date(result.bracket_deadline).toLocaleString()}`;
			await Promise.all([loadData(), fetchPhaseStatus()]);
		} catch (e) {
			activationError = e instanceof Error ? e.message : 'Failed to activate Phase 2';
		} finally {
			activating = false;
		}
	}

	async function handleDeactivatePhase2() {
		if (!confirm('Are you sure you want to deactivate Phase 2?')) return;
		activating = true;
		activationError = null;
		activationSuccess = null;
		try {
			await deactivatePhase2();
			activationSuccess = 'Phase 2 deactivated';
			await Promise.all([loadData(), fetchPhaseStatus()]);
		} catch (e) {
			activationError = e instanceof Error ? e.message : 'Failed to deactivate Phase 2';
		} finally {
			activating = false;
		}
	}

	$: activeCompetition = competitions.find((c) => c.is_active);
</script>

<svelte:head>
	<title>Admin — Predictor</title>
</svelte:head>

{#if $isAuthenticated && $user?.is_admin}
	<PnPageShell>
		<section class="pn-pf-hero">
			<div class="av" style="background: var(--gold); color: var(--ink);">★</div>
			<div class="nm-block">
				<div class="nm">Admin <em>console</em></div>
				<div class="sub">Manage competition, phases, scores, and users</div>
			</div>
			<div class="rank-block">
				<div class="l">Phase</div>
				<div class="v" style="color: var(--gold);">{$isPhase2Active ? 'II' : 'I'}</div>
				<div class="of">{activeCompetition?.name ?? 'no competition active'}</div>
			</div>
		</section>

		{#if loading}
			<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">Loading admin data…</p>
		{:else if error}
			<div class="pn-pf-alert error">{error} · <button class="pn-btn ghost" style="padding: 4px 10px; font-size: 11px;" on:click={loadData}>Retry</button></div>
		{:else}
			<!-- Stats -->
			{#if stats}
				<section class="pn-pf-stats">
					<div class="pn-pf-stat">
						<div class="l">Users</div>
						<div class="v">{stats.total_users}</div>
						<div class="sub">{stats.active_users} active</div>
					</div>
					<div class="pn-pf-stat">
						<div class="l">Fixtures</div>
						<div class="v">{stats.total_fixtures}</div>
						<div class="sub">{stats.completed_fixtures} completed</div>
					</div>
					<div class="pn-pf-stat">
						<div class="l">Predictions</div>
						<div class="v">{stats.total_predictions}</div>
					</div>
					<div class="pn-pf-stat">
						<div class="l">Live</div>
						<div class="v exact">{stats.live_fixtures}</div>
						<div class="sub">matches</div>
					</div>
				</section>
			{/if}

			<!-- Score Sync -->
			<section class="pn-pf-section">
				<div class="h"><span>Score Sync</span><span class="right">Football-Data.org</span></div>
				<div class="body">
					{#if syncError}<div class="pn-pf-alert error" style="margin-bottom: 12px;">{syncError}</div>{/if}
					{#if syncResult}
						<div class="pn-ad-syncresult">
							<div>Last sync: <b>{syncedAt?.toLocaleTimeString() ?? ''}</b></div>
							<div class="pills">
								<span class="pn-tag got">{syncResult.synced} created</span>
								<span class="pn-tag">{syncResult.updated} updated</span>
								{#if syncResult.errors.length > 0}
									<span class="pn-tag red">{syncResult.errors.length} errors</span>
								{/if}
							</div>
							{#if syncResult.errors.length > 0}
								<div style="margin-top: 8px;">
									{#each syncResult.errors as err}
										<div style="color: var(--red); font-size: 10.5px;">• {err}</div>
									{/each}
								</div>
							{/if}
						</div>
					{/if}
					<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); letter-spacing: 0.06em; margin-bottom: 12px;">
						The background scheduler runs every 60s during match windows; this is the manual escape hatch.
					</p>
					<button class="pn-btn gold" type="button" on:click={handleSyncScores} disabled={syncing}>
						{syncing ? 'Syncing…' : 'Sync scores now'}
					</button>
				</div>
			</section>

			<!-- Phase 1 Deadline -->
			<section class="pn-pf-section">
				<div class="h"><span>Phase I Deadline</span><span class="right">Group stage lock</span></div>
				<div class="body">
					<div class="pn-ad-status">
						<span>
							<b>DEADLINE</b>
							{#if $phase1Deadline}
								· {new Date($phase1Deadline).toLocaleString()}
							{:else}
								· <span class="warn">NOT SET</span>
							{/if}
						</span>
						{#if $phase1Deadline}
							<span class="{$phase1Countdown === 'Locked' ? 'warn' : 'ok'}">{$phase1Countdown}</span>
						{/if}
					</div>

					{#if phase1Error}<div class="pn-pf-alert error" style="margin-bottom: 12px;">{phase1Error}</div>{/if}
					{#if phase1Success}<div class="pn-pf-alert success" style="margin-bottom: 12px;">{phase1Success}</div>{/if}

					<div class="pn-pf-form row2">
						<div>
							<label for="p1-date">Date</label>
							<input id="p1-date" type="date" bind:value={phase1DeadlineDate} />
						</div>
						<div>
							<label for="p1-time">Time</label>
							<input id="p1-time" type="time" bind:value={phase1DeadlineTime} />
						</div>
						<div class="full">
							<button class="pn-btn" type="button" on:click={handleSetPhase1Deadline} disabled={settingPhase1}>
								{settingPhase1 ? 'Setting…' : 'Set Phase I deadline'}
							</button>
						</div>
					</div>
				</div>
			</section>

			<!-- Phase 2 Activation -->
			<section class="pn-pf-section">
				<div class="h"><span>Phase II Activation</span><span class="right">Knockout stage</span></div>
				<div class="body">
					<div class="pn-ad-status">
						<span>
							<b>STATUS</b> ·
							{#if $isPhase2Active}
								<span class="ok">ACTIVE</span>
								{#if $phase2BracketDeadline}
									· Bracket locks {new Date($phase2BracketDeadline).toLocaleString()}
								{/if}
							{:else}
								<span class="warn">NOT ACTIVE</span>
							{/if}
						</span>
						{#if $phase2BracketDeadline}
							<span class="{$phase2Countdown === 'Locked' ? 'warn' : 'ok'}">{$phase2Countdown}</span>
						{/if}
					</div>

					{#if activationError}<div class="pn-pf-alert error" style="margin-bottom: 12px;">{activationError}</div>{/if}
					{#if activationSuccess}<div class="pn-pf-alert success" style="margin-bottom: 12px;">{activationSuccess}</div>{/if}

					<div class="pn-pf-form row2">
						<div>
							<label for="p2-date">Bracket lock date</label>
							<input id="p2-date" type="date" bind:value={bracketDeadlineDate} />
						</div>
						<div>
							<label for="p2-time">Time</label>
							<input id="p2-time" type="time" bind:value={bracketDeadlineTime} />
						</div>
						<div class="full" style="display: flex; gap: 10px; flex-wrap: wrap;">
							<button class="pn-btn gold" type="button" on:click={handleActivatePhase2} disabled={activating}>
								{activating ? 'Working…' : ($isPhase2Active ? 'Update Phase II deadline' : 'Activate Phase II')}
							</button>
							{#if $isPhase2Active}
								<button class="pn-btn navy" type="button" on:click={handleDeactivatePhase2} disabled={activating}>
									Deactivate Phase II
								</button>
							{/if}
						</div>
					</div>
				</div>
			</section>

			<!-- Phase II open (advances each eligible entry's phase_2 row to draft) -->
			{#if $isPhase2Active}
				<section class="pn-pf-section">
					<div class="h"><span>Phase II Open</span><span class="right">Per-entry advance</span></div>
					<div class="body">
						<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); letter-spacing: 0.06em; margin-bottom: 12px;">
							Phase II <b>activation</b> opens the bracket window globally (above). Phase II <b>open</b> walks every eligible entry and advances its
							per-phase row so the user can start picking. Idempotent — already-open rows are skipped.
						</p>
						{#if phase2OpenError}<div class="pn-pf-alert error" style="margin-bottom: 12px;">{phase2OpenError}</div>{/if}
						{#if phase2OpenResult}
							<div class="pn-ad-syncresult">
								<div class="pills">
									<span class="pn-tag got">{phase2OpenResult.entries_opened} opened</span>
									<span class="pn-tag">{phase2OpenResult.entries_already_open} already open</span>
									{#if phase2OpenResult.entries_skipped_withdrawn > 0}
										<span class="pn-tag">{phase2OpenResult.entries_skipped_withdrawn} withdrawn</span>
									{/if}
									{#if phase2OpenResult.entries_skipped_disabled > 0}
										<span class="pn-tag red">{phase2OpenResult.entries_skipped_disabled} disabled</span>
									{/if}
								</div>
							</div>
						{/if}
						<button class="pn-btn gold" type="button" on:click={handleOpenPhase2} disabled={openingPhase2} style="margin-top: 12px;">
							{openingPhase2 ? 'Opening…' : 'Open Phase II for all eligible entries'}
						</button>
					</div>
				</section>
			{/if}

			<!-- Competition Entry Settings -->
			<section class="pn-pf-section">
				<div class="h">
					<span>Entry Settings</span>
					<span class="right">
						{#if entrySettings}max {entrySettings.max_entries_per_user} / user · {entrySettings.payment_mode}{/if}
					</span>
				</div>
				<div class="body">
					{#if settingsLoading && !entrySettings}
						<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3);">Loading…</p>
					{:else if settingsError}
						<div class="pn-pf-alert error" style="margin-bottom: 12px;">{settingsError} · <button class="pn-btn ghost" style="padding: 4px 10px; font-size: 11px;" on:click={loadEntrySettings}>Retry</button></div>
					{:else if settingsDraft}
						{#if settingsSuccess}<div class="pn-pf-alert success" style="margin-bottom: 12px;">{settingsSuccess}</div>{/if}
						<div class="pn-ad-settings">
							<label class="num">
								<span class="lbl">Max entries per user</span>
								<input type="number" min="1" bind:value={settingsDraft.max_entries_per_user} />
							</label>
							<label class="num">
								<span class="lbl">Payment mode</span>
								<select bind:value={settingsDraft.payment_mode}>
									<option value="per_entry">per_entry</option>
									<option value="per_user">per_user</option>
								</select>
							</label>
							{#each BOOL_SETTINGS as f (f.key)}
								<label class="check">
									<input
										type="checkbox"
										checked={settingsDraft[f.key]}
										on:change={(e) => setBoolSetting(f.key, e.currentTarget.checked)}
									/>
									<span class="lbl">{f.label}</span>
								</label>
							{/each}
						</div>
						<div style="display: flex; gap: 10px; margin-top: 16px; flex-wrap: wrap;">
							<button class="pn-btn" type="button" on:click={handleSaveSettings} disabled={!settingsDirty || settingsSaving}>
								{settingsSaving ? 'Saving…' : settingsDirty ? 'Save changes' : 'Saved'}
							</button>
							<button class="pn-btn ghost" type="button" on:click={handleResetSettings} disabled={!settingsDirty || settingsSaving}>
								Reset
							</button>
						</div>
					{/if}
				</div>
			</section>

			<!-- Entries admin table -->
			<section class="pn-pf-section">
				<div class="h">
					<span>Entries</span>
					<span class="right">{visibleEntries.length} of {entries.length}</span>
				</div>
				<div class="body">
					{#if entryActionError}<div class="pn-pf-alert error" style="margin-bottom: 12px;">{entryActionError}</div>{/if}

					<!-- Filters row -->
					<div class="pn-ad-entry-filters">
						<input
							class="pn-ad-search"
							placeholder="User name / email…"
							bind:value={entryUserSearch}
							type="search"
						/>
						<input
							class="pn-ad-search"
							placeholder="Reference (WC26-…)"
							bind:value={entryRefSearch}
							type="search"
							on:change={loadEntries}
						/>
						<select bind:value={entryStatusFilter} on:change={loadEntries}>
							<option value="">Any status</option>
							<option value="draft">draft</option>
							<option value="ready">ready</option>
							<option value="submitted">submitted</option>
							<option value="locked">locked</option>
							<option value="withdrawn">withdrawn</option>
							<option value="disabled">disabled</option>
						</select>
						<select bind:value={entryPaidFilter} on:change={loadEntries}>
							<option value="">Any paid</option>
							<option value="paid">Paid</option>
							<option value="unpaid">Unpaid</option>
						</select>
						<select bind:value={entryDisabledFilter} on:change={loadEntries}>
							<option value="">Any state</option>
							<option value="active">Active</option>
							<option value="disabled">Disabled</option>
						</select>
						<button class="pn-btn ghost" type="button" on:click={loadEntries} disabled={entriesLoading}>
							{entriesLoading ? '…' : 'Refresh'}
						</button>
					</div>

					{#if entriesError}
						<div class="pn-pf-alert error" style="margin-top: 12px;">{entriesError}</div>
					{:else if entriesLoading && entries.length === 0}
						<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); margin-top: 14px;">Loading entries…</p>
					{:else if visibleEntries.length === 0}
						<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em; margin-top: 14px;">
							No entries match the filters
						</p>
					{:else}
						<div class="pn-ad-entries">
							{#each visibleEntries as e (e.id)}
								{@const status = entryDisplayStatus(e)}
								<div class="pn-ad-entry" class:disabled={e.is_disabled} class:withdrawn={!!e.withdrawn_at}>
									<div class="who">
										<div class="nm">
											{e.display_name}
											<span class="ref">{e.reference}</span>
										</div>
										<div class="em">{userNameById(e.user_id)} · {userEmailById(e.user_id)}</div>
									</div>
									<div class="badges">
										<span class={statusChipClass(status)}>{status.toUpperCase()}</span>
										{#if e.paid}<span class="pn-tag got">Paid</span>{:else}<span class="pn-tag">Unpaid</span>{/if}
										{#if !e.prize_eligible}<span class="pn-tag">No prize</span>{/if}
										{#if e.is_disabled && e.disabled_reason}
											<span class="pn-tag red" title={e.disabled_reason}>Reason: {e.disabled_reason}</span>
										{/if}
									</div>
									<div class="actions">
										<button class="pn-btn ghost" type="button" on:click={() => handleEntryTogglePaid(e)} disabled={entryActingId === e.id}>
											{e.paid ? '− Paid' : '+ Paid'}
										</button>
										<button class="pn-btn ghost" type="button" on:click={() => handleEntryTogglePrize(e)} disabled={entryActingId === e.id}>
											{e.prize_eligible ? '− Prize' : '+ Prize'}
										</button>
										{#if e.is_disabled}
											<button class="pn-btn navy" type="button" on:click={() => handleEnable(e)} disabled={entryActingId === e.id}>
												Enable
											</button>
										{:else}
											<button class="pn-btn navy" type="button" on:click={() => openDisableDialog(e)} disabled={entryActingId === e.id}>
												Disable…
											</button>
										{/if}
										<button class="pn-btn ghost" type="button" on:click={() => openAuditDrawer(e.id)}>
											Audit
										</button>
									</div>
								</div>

								<!-- Inline disable dialog -->
								{#if disableTargetId === e.id}
									<div class="pn-ad-inline-dialog">
										<div class="hh">Disable {e.display_name} ({e.reference})</div>
										<input
											type="text"
											class="pn-ad-search"
											style="margin: 8px 0;"
											placeholder="Reason (required)"
											bind:value={disableReason}
										/>
										<div style="display: flex; gap: 8px;">
											<button class="pn-btn red" type="button" on:click={handleConfirmDisable} disabled={!disableReason.trim() || entryActingId === e.id}>
												{entryActingId === e.id ? 'Disabling…' : 'Confirm disable'}
											</button>
											<button class="pn-btn ghost" type="button" on:click={closeDisableDialog}>Cancel</button>
										</div>
									</div>
								{/if}

								<!-- Inline audit drawer -->
								{#if auditEntryId === e.id}
									<div class="pn-ad-audit">
										<div class="hh">
											Audit log · {e.display_name}
											<button class="pn-btn ghost" type="button" on:click={closeAuditDrawer} style="float: right; padding: 4px 10px; font-size: 11px;">Close</button>
										</div>
										{#if auditLoading}
											<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); margin-top: 8px;">Loading…</p>
										{:else if auditError}
											<div class="pn-pf-alert error" style="margin-top: 8px;">{auditError}</div>
										{:else if auditEvents.length === 0}
											<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); margin-top: 8px;">No events.</p>
										{:else}
											<ul class="pn-ad-audit-list">
												{#each auditEvents as ev (ev.id)}
													<li>
														<div class="line">
															<span class="t">{fmtAuditTime(ev.created_at)}</span>
															<span class="transition">{ev.from_status} → <b>{ev.to_status}</b></span>
															{#if ev.phase}<span class="phase">{ev.phase}</span>{/if}
															<span class="actor">by {userNameById(ev.actor_user_id)} ({ev.actor_role})</span>
														</div>
														{#if ev.reason}<div class="reason">"{ev.reason}"</div>{/if}
													</li>
												{/each}
											</ul>
										{/if}
									</div>
								{/if}
							{/each}
						</div>
					{/if}
				</div>
			</section>

			<!-- Bonus question answers -->
			<section class="pn-pf-section">
				<div class="h">
					<span>Bonus Question Answers</span>
					<span class="right">{bonusAnswerViews.filter((v) => v.correct_answer).length} of {bonusAnswerViews.length} resolved</span>
				</div>
				<div class="body">
					{#if bonusError}<div class="pn-pf-alert error" style="margin-bottom: 12px;">{bonusError}</div>{/if}
					{#each ['group_stage', 'top_flop', 'awards'] as cat}
						{@const items = bonusByCategory[cat] ?? []}
						{#if items.length > 0}
							<h3 style="font-family: var(--display); font-size: 14px; text-transform: uppercase; letter-spacing: 0.04em; margin: 14px 0 8px;">
								{BONUS_CATEGORY_LABEL[cat]}
							</h3>
							{#each items as v (v.question_id)}
								<div class="pn-ad-user" style="grid-template-columns: 1fr 1fr auto auto;">
									<div class="who">
										<div class="nm" style="font-size: 13px; text-transform: none; letter-spacing: 0;">{v.label}</div>
										<div class="em">{v.points} pts · {v.input_type} · {fmtResolved(v.resolved_at)}</div>
									</div>
									<input
										type="text"
										class="pn-ad-search"
										style="margin: 0; max-width: 100%;"
										placeholder={v.correct_answer ? '' : 'Enter correct answer…'}
										value={draftFor(v)}
										on:input={(e) => setDraft(v.question_id, e.currentTarget.value)}
									/>
									<div class="badges">
										{#if v.correct_answer}
											<span class="pn-tag got" title="Currently saved: {v.correct_answer}">✓ {v.correct_answer}</span>
										{:else}
											<span class="pn-tag" style="opacity: 0.6;">— Unset</span>
										{/if}
									</div>
									<div class="actions">
										<button
											class="pn-btn ghost"
											type="button"
											on:click={() => handleSaveBonusAnswer(v)}
											disabled={savingQId === v.question_id}
										>
											{savingQId === v.question_id ? 'Saving…' : 'Save'}
										</button>
									</div>
								</div>
							{/each}
						{/if}
					{/each}
					<p style="font-family: var(--mono); font-size: 10.5px; color: var(--ink-3); letter-spacing: 0.06em; text-transform: uppercase; margin-top: 14px;">
						★ Saving a correct answer awards bonus points to every player whose pick matches (case- and accent-insensitive). Leave blank to un-resolve a question.
					</p>
				</div>
			</section>

			<!-- User Management -->
			<section class="pn-pf-section">
				<div class="h"><span>User Management</span><span class="right">{filteredUsers.length} of {users.length}</span></div>
				<div class="body">
					{#if userActionError}<div class="pn-pf-alert error" style="margin-bottom: 12px;">{userActionError}</div>{/if}
					<input
						class="pn-ad-search"
						placeholder="Search by name or email…"
						bind:value={userSearch}
						type="search"
					/>
					<div class="pn-ad-users">
						{#each filteredUsers as u (u.id)}
							{@const isPaid = paidOf(u)}
							<div class="pn-ad-user" class:admin={u.is_admin} class:inactive={!u.is_active} class:paid={isPaid}>
								<label class="paid-toggle" title={isPaid ? 'Mark as unpaid' : 'Mark as paid'}>
									<input
										type="checkbox"
										checked={isPaid}
										disabled={togglingUserId === u.id}
										on:change={() => handleTogglePaid(u)}
									/>
									<span class="box" aria-hidden="true">{isPaid ? '✓' : ''}</span>
									<span class="lbl">{isPaid ? 'Paid' : 'Unpaid'}</span>
								</label>
								<div class="who">
									<div class="nm">{u.name}</div>
									<div class="em">{u.email} · {u.auth_provider === 'google' ? 'GOOGLE' : 'EMAIL'}</div>
								</div>
								<div class="badges">
									{#if u.is_admin}<span class="pn-tag gold">Admin</span>{/if}
									<span class="pn-tag {u.is_active ? 'got' : 'red'}">{u.is_active ? 'Active' : 'Inactive'}</span>
								</div>
								<div class="actions">
									<button class="pn-btn ghost" type="button" on:click={() => handleToggleAdmin(u)} disabled={togglingUserId === u.id}>
										{u.is_admin ? '− Admin' : '+ Admin'}
									</button>
									<button class="pn-btn navy" type="button" on:click={() => handleToggleActive(u)} disabled={togglingUserId === u.id}>
										{u.is_active ? 'Deactivate' : 'Reactivate'}
									</button>
								</div>
							</div>
						{:else}
							<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">No users match search</p>
						{/each}
					</div>
				</div>
			</section>
		{/if}
	</PnPageShell>
{/if}
