<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import changelogData from '$lib/data/changelog.json';
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
	import { adminWithdrawEntry, adminReinstateEntry } from '$lib/api/entries';
	import type { Entry, EntrySettings, EntryStatus } from '$lib/types/entry';
	import { computeDisplayStatus } from '$lib/types/entry';
	import type { PredictionPhase } from '$types';
	import Toolbar from '$lib/components/Toolbar.svelte';
	import Pagination from '$lib/components/Pagination.svelte';
	import OverflowMenu from '$lib/components/OverflowMenu.svelte';

	$: if ($isAuthenticated && !$user?.is_admin) goto('/');
	$: if (!$isAuthenticated) goto('/login');

	/** Display name for an admin-view user. Falls back to the email-prefix
	 *  for magic-link sign-ups that haven't completed /onboarding yet
	 *  (where `name === null`). */
	function userDisplayName(u: UserAdminView): string {
		return u.name ?? u.email.split('@')[0];
	}

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

	// --- Competition entry settings (the 11-field form) ----------------------
	type BoolSettingKey =
		| 'auto_create_first_entry'
		| 'allow_duplicate_from_existing'
		| 'allow_user_rename'
		| 'block_unpaid_entry_submission'
		| 'show_entry_reference_publicly'
		| 'phase_scoped_status_enabled';
	const BOOL_SETTINGS: { key: BoolSettingKey; label: string }[] = [
		{ key: 'auto_create_first_entry', label: "Auto-create user's first entry" },
		{ key: 'allow_duplicate_from_existing', label: 'Allow duplicate from existing' },
		{ key: 'allow_user_rename', label: 'Allow users to rename entries' },
		{ key: 'block_unpaid_entry_submission', label: 'Block unpaid entry submission' },
		{ key: 'show_entry_reference_publicly', label: 'Show entry reference publicly' },
		{ key: 'phase_scoped_status_enabled', label: 'Per-phase status (vs. competition-wide)' }
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

	// --- Phase II open --------------------------------------------------------
	let openingPhase2 = false;
	let phase2OpenResult: Phase2OpenResponse | null = null;
	let phase2OpenError: string | null = null;

	// --- Entries admin table --------------------------------------------------
	let entries: Entry[] = [];
	let entriesTotal = 0;
	let entriesOffset = 0;
	const entriesLimit = 25;
	let entriesLoading = false;
	let entriesExporting = false;
	let entriesError: string | null = null;
	let entryFilters: AdminEntryFilters = {};
	// Free-text search: matches user email OR entry reference (substring,
	// case-insensitive) via the new backend `search` param. Tweak 6 in
	// stay-in-plan-mode-dynamic-adleman.md.
	let entrySearch = '';
	let entryStatusFilter: '' | EntryStatus = '';
	let entryPaidFilter: '' | 'paid' | 'unpaid' = '';
	let entryDisabledFilter: '' | 'disabled' | 'active' = '';

	let entryActionError: string | null = null;
	let entryActingId: string | null = null;

	// Audit drawer state.
	let auditEntryId: string | null = null;
	let auditEvents: EntryEvent[] = [];
	let auditLoading = false;
	let auditError: string | null = null;

	// Disable dialog state.
	let disableTargetId: string | null = null;
	let disableReason = '';

	// Withdraw dialog state (admin-only, irreversible elimination).
	let withdrawTargetId: string | null = null;
	let withdrawReason = '';

	// Reinstate dialog state (admin-only, withdrawn → submitted rescue).
	let reinstateTargetId: string | null = null;
	let reinstateReason = '';

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
			await loadEntries();
		} catch (e) {
			phase2OpenError = e instanceof Error ? e.message : 'Failed to open Phase II';
		} finally {
			openingPhase2 = false;
		}
	}

	function buildFilters(): AdminEntryFilters {
		const f: AdminEntryFilters = {};
		// Use the wider `search` field (matches email OR reference) so admins
		// can find entries by whichever fragment they remember.
		if (entrySearch.trim()) f.search = entrySearch.trim();
		if (entryStatusFilter) f.status = entryStatusFilter;
		if (entryPaidFilter === 'paid') f.paid = true;
		else if (entryPaidFilter === 'unpaid') f.paid = false;
		if (entryDisabledFilter === 'disabled') f.disabled = true;
		else if (entryDisabledFilter === 'active') f.disabled = false;
		return f;
	}

	async function loadEntries({ resetOffset = true }: { resetOffset?: boolean } = {}) {
		entriesLoading = true;
		entriesError = null;
		try {
			entryFilters = buildFilters();
			if (resetOffset) entriesOffset = 0;
			const page = await adminListEntries(entryFilters, {
				limit: entriesLimit,
				offset: entriesOffset
			});
			entries = page.items;
			entriesTotal = page.total;
		} catch (e) {
			entriesError = e instanceof Error ? e.message : 'Failed to load entries';
		} finally {
			entriesLoading = false;
		}
	}

	async function handleEntriesPrev() {
		if (entriesOffset === 0) return;
		entriesOffset = Math.max(0, entriesOffset - entriesLimit);
		await loadEntries({ resetOffset: false });
	}

	async function handleEntriesNext() {
		if (entriesOffset + entriesLimit >= entriesTotal) return;
		entriesOffset += entriesLimit;
		await loadEntries({ resetOffset: false });
	}

	/** CSV export of the full filtered result set (no pagination applied). */
	async function handleExportEntries() {
		entriesExporting = true;
		entryActionError = null;
		try {
			const all = await adminListEntries(buildFilters());
			const csv = entriesToCsv(all.items);
			const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
			a.href = url;
			a.download = `entries-${stamp}.csv`;
			document.body.appendChild(a);
			a.click();
			a.remove();
			URL.revokeObjectURL(url);
		} catch (e) {
			entryActionError = e instanceof Error ? e.message : 'Export failed';
		} finally {
			entriesExporting = false;
		}
	}

	function entriesToCsv(rows: Entry[]): string {
		const header = [
			'reference',
			'display_name',
			'user_name',
			'user_email',
			'status',
			'paid',
			'prize_eligible',
			'is_disabled',
			'disabled_reason',
			'withdrawn_at',
			'updated_at'
		];
		const lines = [header.join(',')];
		for (const e of rows) {
			const status = computeDisplayStatus(e, 'phase_1' as PredictionPhase);
			const cells = [
				e.reference,
				e.display_name,
				userNameById(e.user_id),
				userEmailById(e.user_id),
				status,
				e.paid ? 'true' : 'false',
				e.prize_eligible ? 'true' : 'false',
				e.is_disabled ? 'true' : 'false',
				e.disabled_reason ?? '',
				e.withdrawn_at ?? '',
				e.updated_at
			].map(csvEscape);
			lines.push(cells.join(','));
		}
		return lines.join('\n');
	}

	function csvEscape(value: string): string {
		if (value == null) return '';
		const s = String(value);
		if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
		return s;
	}

	function userNameById(userId: string): string {
		const u = users.find((x) => x.id === userId);
		return u?.name ?? userId.slice(0, 8);
	}

	function userEmailById(userId: string): string {
		const u = users.find((x) => x.id === userId);
		return u?.email ?? '—';
	}

	// Client-side user-name search was removed when pagination landed —
	// it would have only filtered the current page. Reintroduce later as
	// a server-side user_id filter (the backend already supports it).

	function entryDisplayStatus(e: Entry): EntryStatus {
		return computeDisplayStatus(e, 'phase_1' as PredictionPhase);
	}

	function statusChipClass(s: EntryStatus): string {
		switch (s) {
			case 'submitted':
				return 'badge badge-success';
			case 'withdrawn':
				return 'badge badge-error';
			case 'draft':
			default:
				return 'badge badge-ghost';
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

	function openWithdrawDialog(e: Entry) {
		withdrawTargetId = e.id;
		withdrawReason = '';
	}

	function closeWithdrawDialog() {
		withdrawTargetId = null;
		withdrawReason = '';
	}

	async function handleConfirmWithdraw() {
		if (!withdrawTargetId) return;
		const reason = withdrawReason.trim();
		if (!reason) {
			entryActionError = 'A reason is required to withdraw an entry';
			return;
		}
		entryActingId = withdrawTargetId;
		entryActionError = null;
		try {
			const updated = await adminWithdrawEntry(withdrawTargetId, { reason });
			entries = entries.map((x) => (x.id === updated.id ? updated : x));
			closeWithdrawDialog();
		} catch (err) {
			entryActionError = err instanceof Error ? err.message : 'Failed to withdraw entry';
		} finally {
			entryActingId = null;
		}
	}

	function openReinstateDialog(e: Entry) {
		reinstateTargetId = e.id;
		reinstateReason = '';
	}

	function closeReinstateDialog() {
		reinstateTargetId = null;
		reinstateReason = '';
	}

	async function handleConfirmReinstate() {
		if (!reinstateTargetId) return;
		const reason = reinstateReason.trim();
		if (!reason) {
			entryActionError = 'A reason is required to reinstate an entry';
			return;
		}
		entryActingId = reinstateTargetId;
		entryActionError = null;
		try {
			const updated = await adminReinstateEntry(reinstateTargetId, { reason });
			entries = entries.map((x) => (x.id === updated.id ? updated : x));
			closeReinstateDialog();
		} catch (err) {
			entryActionError = err instanceof Error ? err.message : 'Failed to reinstate entry';
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
		// Bonus answers may have multiple correct values (ties — added in
		// main's auto-resolver). The admin enters them as a comma-separated
		// list; we display the joined list when no draft is in flight.
		return bonusDrafts.get(view.question_id) ?? view.correct_answers.join(', ') ?? '';
	}

	function setDraft(qid: string, value: string) {
		const next = new Map(bonusDrafts);
		next.set(qid, value);
		bonusDrafts = next;
	}

	async function handleSaveBonusAnswer(view: BonusAnswerView) {
		const rawValue = draftFor(view).trim();
		// Split on commas to support ties. Empty string → empty array → un-resolve.
		const values = rawValue
			.split(',')
			.map((s) => s.trim())
			.filter((s) => s.length > 0);
		savingQId = view.question_id;
		bonusError = null;
		try {
			const updated = await setBonusAnswer(view.question_id, values);
			bonusAnswerViews = bonusAnswerViews.map((v) =>
				v.question_id === view.question_id ? updated : v
			);
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
		// Internal literal `top_flop` preserved; display is the longer
		// phrase so admins see the same heading users do.
		top_flop: 'Knockout Stage — Top / Flop',
		// Kept defensively; no current YAML question uses this category.
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
		if (!confirm(`Are you sure you want to ${action} ${userDisplayName(u)}?`)) return;
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
		if (!confirm(`Are you sure you want to ${action} ${userDisplayName(u)}?`)) return;
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
				return userDisplayName(u).toLowerCase().includes(q) || u.email.toLowerCase().includes(q);
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

	// ---- Release Notes ---------------------------------------------------
	// Static JSON bundled at build time. Each entry is { version, date,
	// type, summary, commit }. Latest first; filterable by category.
	type ReleaseEntry = {
		version: string;
		date: string;
		type: string;
		summary: string;
		commit: string;
	};
	const allReleases: ReleaseEntry[] = ([...changelogData.entries] as ReleaseEntry[])
		.reverse();
	const releaseTypes = ['all', 'feature', 'improvement', 'fix', 'internal', 'merge'] as const;
	let releaseFilter: (typeof releaseTypes)[number] = 'all';
	let releaseLimit = 50;
	$: filteredReleases =
		releaseFilter === 'all'
			? allReleases
			: allReleases.filter((r) => r.type === releaseFilter);
	$: visibleReleases = filteredReleases.slice(0, releaseLimit);
	$: latestVersion = allReleases[0]?.version ?? '—';

	const RELEASE_TYPE_BADGE: Record<string, string> = {
		feature: 'badge-success',
		improvement: 'badge-info',
		fix: 'badge-warning',
		internal: 'badge-ghost',
		merge: 'badge-primary'
	};
	const RELEASE_TYPE_LABEL: Record<string, string> = {
		feature: 'New',
		improvement: 'Polish',
		fix: 'Fix',
		internal: 'Internal',
		merge: 'Merge'
	};
</script>

<svelte:head>
	<title>Admin - Predictor v2</title>
</svelte:head>

{#if $isAuthenticated && $user?.is_admin}
	<div class="container mx-auto mobile-padding py-6 space-y-6">
		<!-- Hero -->
		<div class="flex items-center justify-between flex-wrap gap-3">
			<div>
				<h1 class="text-3xl sm:text-4xl font-display tracking-wide">Admin Console</h1>
				<p class="text-sm text-base-content/50">Manage competition, phases, scores, and users</p>
			</div>
			<div class="text-right">
				<div class="stat-title">Phase</div>
				<div class="font-display text-2xl tracking-wide text-accent">{$isPhase2Active ? 'II' : 'I'}</div>
				<div class="text-xs text-base-content/40">{activeCompetition?.name ?? 'no competition active'}</div>
			</div>
		</div>

		{#if loading}
			<p class="text-sm text-base-content/50">Loading admin data…</p>
		{:else if error}
			<div class="alert alert-error">{error}<button class="btn btn-sm btn-ghost" on:click={loadData}>Retry</button></div>
		{:else}
			<!-- Stats -->
			{#if stats}
				<div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
					<div class="stat-card"><p class="stat-title">Users</p><p class="stat-value">{stats.total_users}</p><p class="text-xs text-base-content/40 mt-1">{stats.active_users} active</p></div>
					<div class="stat-card"><p class="stat-title">Fixtures</p><p class="stat-value">{stats.total_fixtures}</p><p class="text-xs text-base-content/40 mt-1">{stats.completed_fixtures} completed</p></div>
					<div class="stat-card"><p class="stat-title">Predictions</p><p class="stat-value">{stats.total_predictions}</p></div>
					<div class="stat-card"><p class="stat-title">Live</p><p class="stat-value text-error">{stats.live_fixtures}</p><p class="text-xs text-base-content/40 mt-1">matches</p></div>
				</div>
			{/if}

			<!-- Score Sync -->
			<section class="rounded-xl border bg-base-200 shadow-card p-5">
				<h2 class="text-lg font-display tracking-wide mb-3">Score Sync <span class="text-xs text-base-content/40">· Football-Data.org</span></h2>
				{#if syncError}<div class="alert alert-error text-sm mb-3">{syncError}</div>{/if}
				{#if syncResult}
					<div class="mb-3 text-sm">
						<div>Last sync: <b>{syncedAt?.toLocaleTimeString() ?? ''}</b></div>
						<div class="flex gap-2 mt-1 flex-wrap">
							<span class="badge badge-success">{syncResult.synced} created</span>
							<span class="badge badge-ghost">{syncResult.updated} updated</span>
							{#if syncResult.errors.length > 0}<span class="badge badge-error">{syncResult.errors.length} errors</span>{/if}
						</div>
						{#if syncResult.errors.length > 0}
							<div class="mt-2 text-xs text-error">{#each syncResult.errors as err}<div>• {err}</div>{/each}</div>
						{/if}
					</div>
				{/if}
				<p class="text-xs text-base-content/50 mb-3">The background scheduler runs every 60s during match windows; this is the manual escape hatch.</p>
				<button class="btn btn-primary btn-sm" type="button" on:click={handleSyncScores} disabled={syncing}>
					{syncing ? 'Syncing…' : 'Sync scores now'}
				</button>
			</section>

			<!-- Competition start datetime — at this moment, any DRAFT entries
			     auto-flip to WITHDRAWN (scheduler tick), and SUBMITTED entries
			     become read-only and start scoring. -->
			<section class="rounded-xl border bg-base-200 shadow-card p-5">
				<h2 class="text-lg font-display tracking-wide mb-3">Competition starts at <span class="text-xs text-base-content/40">· locks predictions, kicks off scoring</span></h2>
				<div class="text-sm mb-3">
					<b>Starts:</b>
					{#if $phase1Deadline}{new Date($phase1Deadline).toLocaleString()} · <span class={$phase1Countdown === 'Locked' ? 'text-error' : 'text-success'}>{$phase1Countdown}</span>{:else}<span class="text-warning-text">NOT SET</span>{/if}
				</div>
				{#if phase1Error}<div class="alert alert-error text-sm mb-3">{phase1Error}</div>{/if}
				{#if phase1Success}<div class="alert alert-success text-sm mb-3">{phase1Success}</div>{/if}
				<div class="flex gap-3 items-end flex-wrap">
					<div class="form-control"><label class="label" for="p1-date"><span class="label-text">Date</span></label><input id="p1-date" type="date" class="input input-bordered input-sm" bind:value={phase1DeadlineDate} /></div>
					<div class="form-control"><label class="label" for="p1-time"><span class="label-text">Time</span></label><input id="p1-time" type="time" class="input input-bordered input-sm" bind:value={phase1DeadlineTime} /></div>
					<button class="btn btn-primary btn-sm" type="button" on:click={handleSetPhase1Deadline} disabled={settingPhase1}>{settingPhase1 ? 'Setting…' : 'Set competition start'}</button>
				</div>
			</section>

			<!-- Phase 2 Activation -->
			<section class="rounded-xl border bg-base-200 shadow-card p-5">
				<h2 class="text-lg font-display tracking-wide mb-3">Phase II Activation <span class="text-xs text-base-content/40">· Knockout stage</span></h2>
				<div class="text-sm mb-3">
					<b>Status:</b>
					{#if $isPhase2Active}<span class="text-success">ACTIVE</span>{#if $phase2BracketDeadline} · Bracket locks {new Date($phase2BracketDeadline).toLocaleString()} · <span class={$phase2Countdown === 'Locked' ? 'text-error' : 'text-success'}>{$phase2Countdown}</span>{/if}{:else}<span class="text-warning-text">NOT ACTIVE</span>{/if}
				</div>
				{#if activationError}<div class="alert alert-error text-sm mb-3">{activationError}</div>{/if}
				{#if activationSuccess}<div class="alert alert-success text-sm mb-3">{activationSuccess}</div>{/if}
				<div class="flex gap-3 items-end flex-wrap">
					<div class="form-control"><label class="label" for="p2-date"><span class="label-text">Bracket lock date</span></label><input id="p2-date" type="date" class="input input-bordered input-sm" bind:value={bracketDeadlineDate} /></div>
					<div class="form-control"><label class="label" for="p2-time"><span class="label-text">Time</span></label><input id="p2-time" type="time" class="input input-bordered input-sm" bind:value={bracketDeadlineTime} /></div>
					<button class="btn btn-primary btn-sm" type="button" on:click={handleActivatePhase2} disabled={activating}>{activating ? 'Working…' : $isPhase2Active ? 'Update Phase II deadline' : 'Activate Phase II'}</button>
					{#if $isPhase2Active}<button class="btn btn-outline btn-error btn-sm" type="button" on:click={handleDeactivatePhase2} disabled={activating}>Deactivate Phase II</button>{/if}
				</div>
			</section>

			<!-- Phase II open — hidden in the simplified-lifecycle build. Phase 2 stays
			     dormant in the backend; the markup + handler are dropped from the UI. -->

			<!-- Entry Settings -->
			<section class="rounded-xl border bg-base-200 shadow-card p-5">
				<h2 class="text-lg font-display tracking-wide mb-3">Entry Settings {#if entrySettings}<span class="text-xs text-base-content/40">· max {entrySettings.max_entries_per_user}/user · {entrySettings.payment_mode}</span>{/if}</h2>
				{#if settingsLoading && !entrySettings}
					<p class="text-sm text-base-content/50">Loading…</p>
				{:else if settingsError}
					<div class="alert alert-error text-sm">{settingsError}<button class="btn btn-xs btn-ghost" on:click={loadEntrySettings}>Retry</button></div>
				{:else if settingsDraft}
					{#if settingsSuccess}<div class="alert alert-success text-sm mb-3">{settingsSuccess}</div>{/if}
					<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
						<label class="form-control">
							<span class="label-text mb-1">Max entries per user</span>
							<input type="number" min="1" class="input input-bordered input-sm" bind:value={settingsDraft.max_entries_per_user} />
						</label>
						<label class="form-control">
							<span class="label-text mb-1">Payment mode</span>
							<select class="select select-bordered select-sm" bind:value={settingsDraft.payment_mode}>
								<option value="per_entry">per_entry</option>
								<option value="per_user">per_user</option>
							</select>
						</label>
						{#each BOOL_SETTINGS as f (f.key)}
							<label class="flex items-center gap-2 cursor-pointer">
								<input type="checkbox" class="checkbox checkbox-sm" checked={settingsDraft[f.key]} on:change={(e) => setBoolSetting(f.key, e.currentTarget.checked)} />
								<span class="text-sm">{f.label}</span>
							</label>
						{/each}
					</div>
					<div class="flex gap-3 mt-4 flex-wrap">
						<button class="btn btn-primary btn-sm" type="button" on:click={handleSaveSettings} disabled={!settingsDirty || settingsSaving}>{settingsSaving ? 'Saving…' : settingsDirty ? 'Save changes' : 'Saved'}</button>
						<button class="btn btn-outline btn-sm" type="button" on:click={handleResetSettings} disabled={!settingsDirty || settingsSaving}>Reset</button>
					</div>
				{/if}
			</section>

			<!-- Entries admin table -->
			<section class="rounded-xl border bg-base-200 shadow-card p-5">
				<h2 class="text-lg font-display tracking-wide mb-3">
					Entries
					<span class="text-xs text-base-content/40">· {entriesTotal} total</span>
				</h2>
				{#if entryActionError}<div class="alert alert-error text-sm mb-3">{entryActionError}</div>{/if}

				<Toolbar
					bind:search={entrySearch}
					searchPlaceholder="Email or reference (e.g. vinay or 000020)"
					onSearchCommit={() => loadEntries()}
				>
					<svelte:fragment slot="filters">
						<select class="select select-bordered select-sm" bind:value={entryStatusFilter} on:change={() => loadEntries()}>
							<option value="">Any status</option>
							<option value="draft">draft</option>
							<option value="submitted">submitted</option>
							<option value="withdrawn">withdrawn</option>
						</select>
						<select class="select select-bordered select-sm" bind:value={entryPaidFilter} on:change={() => loadEntries()}>
							<option value="">Any paid</option>
							<option value="paid">Paid</option>
							<option value="unpaid">Unpaid</option>
						</select>
						<select class="select select-bordered select-sm" bind:value={entryDisabledFilter} on:change={() => loadEntries()}>
							<option value="">Any state</option>
							<option value="active">Active</option>
							<option value="disabled">Disabled</option>
						</select>
					</svelte:fragment>
					<svelte:fragment slot="actions">
						<button
							class="btn btn-outline btn-sm"
							type="button"
							on:click={handleExportEntries}
							disabled={entriesExporting || entriesTotal === 0}
						>
							{entriesExporting ? 'Exporting…' : 'Export CSV'}
						</button>
					</svelte:fragment>
				</Toolbar>

				{#if entriesError}
					<div class="alert alert-error text-sm">{entriesError}</div>
				{:else if entriesLoading && entries.length === 0}
					<p class="text-sm text-base-content/50">Loading entries…</p>
				{:else if entries.length === 0}
					<p class="text-sm text-base-content/50">No entries match the filters</p>
				{:else}
					<div class="overflow-x-auto rounded-xl border border-base-300/50 bg-base-200">
						<table class="table table-hover">
							<thead>
								<tr class="text-xs uppercase tracking-wider text-base-content/60">
									<th>Reference</th>
									<th>Entry</th>
									<th class="hidden md:table-cell">User</th>
									<th>Status</th>
									<th class="hidden sm:table-cell">Paid</th>
									<th class="hidden lg:table-cell">Prize</th>
									<th class="hidden xl:table-cell">Updated</th>
									<th class="text-right"><span class="sr-only">Actions</span></th>
								</tr>
							</thead>
							<tbody>
								{#each entries as e (e.id)}
									{@const status = entryDisplayStatus(e)}
									{@const dimmed = e.is_disabled || !!e.withdrawn_at}
									<tr class={dimmed ? 'opacity-60' : ''}>
										<td>
											<span class="text-xs font-mono text-base-content/60">{e.reference}</span>
										</td>
										<td>
											<div class="font-medium truncate">{e.display_name}</div>
											{#if e.is_disabled && e.disabled_reason}
												<div class="text-xs text-error truncate" title={e.disabled_reason}>
													Disabled: {e.disabled_reason}
												</div>
											{/if}
										</td>
										<td class="hidden md:table-cell">
											<div class="text-sm truncate">{userNameById(e.user_id)}</div>
											<div class="text-xs text-base-content/50 truncate">{userEmailById(e.user_id)}</div>
										</td>
										<td>
											<span class={statusChipClass(status)}>{status.toUpperCase()}</span>
										</td>
										<td class="hidden sm:table-cell">
											<span class="badge badge-sm {e.paid ? 'badge-success' : 'badge-ghost'}">
												{e.paid ? 'Paid' : 'Unpaid'}
											</span>
										</td>
										<td class="hidden lg:table-cell">
											{#if e.prize_eligible}
												<span class="text-xs text-base-content/60">Eligible</span>
											{:else}
												<span class="badge badge-sm badge-ghost">No prize</span>
											{/if}
										</td>
										<td class="hidden xl:table-cell">
											<span class="text-xs text-base-content/60">{new Date(e.updated_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</span>
										</td>
										<td class="text-right">
											<OverflowMenu label="Actions for {e.display_name}">
												<li>
													<button type="button" on:click={() => handleEntryTogglePaid(e)} disabled={entryActingId === e.id}>
														{e.paid ? '− Mark Unpaid' : '+ Mark Paid'}
													</button>
												</li>
												<li>
													<button type="button" on:click={() => handleEntryTogglePrize(e)} disabled={entryActingId === e.id}>
														{e.prize_eligible ? '− Remove Prize' : '+ Mark Prize-eligible'}
													</button>
												</li>
												{#if e.is_disabled}
													<li>
														<button type="button" on:click={() => handleEnable(e)} disabled={entryActingId === e.id}>
															Enable
														</button>
													</li>
												{:else}
													<li>
														<button type="button" class="text-error" on:click={() => openDisableDialog(e)} disabled={entryActingId === e.id}>
															Disable…
														</button>
													</li>
												{/if}
												{#if status === 'withdrawn'}
													<li>
														<button type="button" class="text-success" on:click={() => openReinstateDialog(e)} disabled={entryActingId === e.id}>
															Reinstate…
														</button>
													</li>
												{:else}
													<li>
														<button type="button" class="text-error" on:click={() => openWithdrawDialog(e)} disabled={entryActingId === e.id}>
															Withdraw…
														</button>
													</li>
												{/if}
												<li>
													<button type="button" on:click={() => openAuditDrawer(e.id)}>
														Audit log
													</button>
												</li>
											</OverflowMenu>
										</td>
									</tr>

									<!-- Inline action dialogs — expand under their row when targeted. -->
									{#if disableTargetId === e.id || withdrawTargetId === e.id || reinstateTargetId === e.id || auditEntryId === e.id}
										<tr class="bg-base-300/20">
											<td colspan="8" class="p-3">
												{#if disableTargetId === e.id}
													<div class="text-sm font-semibold mb-2">Disable {e.display_name} ({e.reference})</div>
													<input type="text" class="input input-bordered input-sm w-full mb-2" placeholder="Reason (required)" bind:value={disableReason} />
													<div class="flex gap-2">
														<button class="btn btn-xs btn-error" type="button" on:click={handleConfirmDisable} disabled={!disableReason.trim() || entryActingId === e.id}>{entryActingId === e.id ? 'Disabling…' : 'Confirm disable'}</button>
														<button class="btn btn-xs btn-ghost" type="button" on:click={closeDisableDialog}>Cancel</button>
													</div>
												{/if}

												{#if withdrawTargetId === e.id}
													<div class="text-sm font-semibold mb-2">Withdraw {e.display_name} ({e.reference})</div>
													<p class="text-xs text-base-content/60 mb-2">Removes the entry from scoring. Reinstate is available later if needed.</p>
													<input type="text" class="input input-bordered input-sm w-full mb-2" placeholder="Reason (required)" bind:value={withdrawReason} />
													<div class="flex gap-2">
														<button class="btn btn-xs btn-error" type="button" on:click={handleConfirmWithdraw} disabled={!withdrawReason.trim() || entryActingId === e.id}>{entryActingId === e.id ? 'Withdrawing…' : 'Confirm withdraw'}</button>
														<button class="btn btn-xs btn-ghost" type="button" on:click={closeWithdrawDialog}>Cancel</button>
													</div>
												{/if}

												{#if reinstateTargetId === e.id}
													<div class="text-sm font-semibold mb-2">Reinstate {e.display_name} ({e.reference}) as SUBMITTED</div>
													<p class="text-xs text-base-content/60 mb-2">Qualifies for scoring from this moment. Use for users who filled all picks but missed the deadline.</p>
													<input type="text" class="input input-bordered input-sm w-full mb-2" placeholder="Reason (required)" bind:value={reinstateReason} />
													<div class="flex gap-2">
														<button class="btn btn-xs btn-success" type="button" on:click={handleConfirmReinstate} disabled={!reinstateReason.trim() || entryActingId === e.id}>{entryActingId === e.id ? 'Reinstating…' : 'Confirm reinstate'}</button>
														<button class="btn btn-xs btn-ghost" type="button" on:click={closeReinstateDialog}>Cancel</button>
													</div>
												{/if}

												{#if auditEntryId === e.id}
													<div class="flex items-center justify-between mb-2">
														<span class="text-sm font-semibold">Audit log · {e.display_name}</span>
														<button class="btn btn-xs btn-ghost" type="button" on:click={closeAuditDrawer}>Close</button>
													</div>
													{#if auditLoading}
														<p class="text-xs text-base-content/50">Loading…</p>
													{:else if auditError}
														<div class="alert alert-error text-xs">{auditError}</div>
													{:else if auditEvents.length === 0}
														<p class="text-xs text-base-content/50">No events.</p>
													{:else}
														<ul class="space-y-1.5">
															{#each auditEvents as ev (ev.id)}
																<li class="text-xs">
																	<div class="flex gap-2 flex-wrap items-center">
																		<span class="font-mono text-base-content/50">{fmtAuditTime(ev.created_at)}</span>
																		<span>{ev.from_status} → <b>{ev.to_status}</b></span>
																		{#if ev.phase}<span class="badge badge-xs">{ev.phase}</span>{/if}
																		<span class="text-base-content/40">by {userNameById(ev.actor_user_id)} ({ev.actor_role})</span>
																	</div>
																	{#if ev.reason}<div class="text-base-content/50 italic">"{ev.reason}"</div>{/if}
																</li>
															{/each}
														</ul>
													{/if}
												{/if}
											</td>
										</tr>
									{/if}
								{/each}
							</tbody>
						</table>
					</div>

					<Pagination
						total={entriesTotal}
						limit={entriesLimit}
						offset={entriesOffset}
						on:prev={handleEntriesPrev}
						on:next={handleEntriesNext}
					/>
				{/if}
			</section>

			<!-- Bonus question answers -->
			<section class="rounded-xl border bg-base-200 shadow-card p-5">
				<h2 class="text-lg font-display tracking-wide mb-3">Bonus Question Answers <span class="text-xs text-base-content/40">· {bonusAnswerViews.filter((v) => v.correct_answers.length > 0).length} of {bonusAnswerViews.length} resolved</span></h2>
				{#if bonusError}<div class="alert alert-error text-sm mb-3">{bonusError}</div>{/if}
				{#each ['group_stage', 'top_flop', 'awards'] as cat}
					{@const items = bonusByCategory[cat] ?? []}
					{#if items.length > 0}
						<h3 class="text-sm font-display uppercase tracking-wide mt-4 mb-2">{BONUS_CATEGORY_LABEL[cat]}</h3>
						{#each items as v (v.question_id)}
							<div class="flex items-center gap-3 py-2 flex-wrap">
								<div class="flex-1 min-w-[200px]">
									<div class="text-sm font-medium">{v.label}</div>
									<div class="text-xs text-base-content/40">{v.points} pts · {v.input_type} · {fmtResolved(v.resolved_at)}</div>
								</div>
								<input type="text" class="input input-bordered input-sm flex-1 min-w-[160px]" placeholder={v.correct_answers.length > 0 ? '' : 'Enter correct answer (comma-separate for ties)…'} value={draftFor(v)} on:input={(e) => setDraft(v.question_id, e.currentTarget.value)} />
								{#if v.correct_answers.length > 0}<span class="badge badge-success" title="Currently saved: {v.correct_answers.join(', ')}">✓ {v.correct_answers.join(', ')}</span>{:else}<span class="badge badge-ghost">Unset</span>{/if}
								<button class="btn btn-xs btn-outline" type="button" on:click={() => handleSaveBonusAnswer(v)} disabled={savingQId === v.question_id}>{savingQId === v.question_id ? 'Saving…' : 'Save'}</button>
							</div>
						{/each}
					{/if}
				{/each}
				<p class="text-xs text-base-content/50 mt-3">★ Saving a correct answer awards bonus points to every player whose pick matches (case- and accent-insensitive). Leave blank to un-resolve a question.</p>
			</section>

			<!-- User Management -->
			<section class="rounded-xl border bg-base-200 shadow-card p-5">
				<h2 class="text-lg font-display tracking-wide mb-3">User Management <span class="text-xs text-base-content/40">· {filteredUsers.length} of {users.length}</span></h2>
				{#if userActionError}<div class="alert alert-error text-sm mb-3">{userActionError}</div>{/if}
				<input class="input input-bordered input-sm w-full max-w-md mb-3" placeholder="Search by name or email…" bind:value={userSearch} type="search" />
				<div class="space-y-2">
					{#each filteredUsers as u (u.id)}
						{@const isPaid = paidOf(u)}
						<div class="flex items-center gap-3 rounded-lg border border-base-300/50 p-3 flex-wrap">
							<label class="flex items-center gap-2 cursor-pointer" title={isPaid ? 'Mark as unpaid' : 'Mark as paid'}>
								<input type="checkbox" class="checkbox checkbox-sm" checked={isPaid} disabled={togglingUserId === u.id} on:change={() => handleTogglePaid(u)} />
								<span class="text-xs">{isPaid ? 'Paid' : 'Unpaid'}</span>
							</label>
							<div class="flex-1 min-w-0">
								<div class="font-semibold" class:italic={u.name === null} class:opacity-70={u.name === null} title={u.name === null ? 'No display name set' : ''}>{userDisplayName(u)}</div>
								<div class="text-xs text-base-content/50">{u.email} · {u.auth_provider === 'google' ? 'GOOGLE' : 'EMAIL'}</div>
							</div>
							<div class="flex items-center gap-1.5">
								{#if u.is_admin}<span class="badge badge-warning">Admin</span>{/if}
								<span class="badge {u.is_active ? 'badge-success' : 'badge-error'}">{u.is_active ? 'Active' : 'Inactive'}</span>
							</div>
							<div class="flex gap-2">
								<button class="btn btn-xs btn-outline" type="button" on:click={() => handleToggleAdmin(u)} disabled={togglingUserId === u.id}>{u.is_admin ? '− Admin' : '+ Admin'}</button>
								<button class="btn btn-xs btn-outline" type="button" on:click={() => handleToggleActive(u)} disabled={togglingUserId === u.id}>{u.is_active ? 'Deactivate' : 'Reactivate'}</button>
							</div>
						</div>
					{:else}
						<p class="text-sm text-base-content/50">No users match search</p>
					{/each}
				</div>
			</section>

			<!-- Release Notes — every May 2026+ commit noted, latest first.
			     Sourced from frontend/src/lib/data/changelog.json (bundled
			     at build time). Filterable by type; defaults to showing
			     the 50 most-recent entries with a "Show more" button. -->
			<section class="rounded-xl border bg-base-200 shadow-card p-5">
				<h2 class="text-lg font-display tracking-wide mb-3">
					Release Notes
					<span class="text-xs text-base-content/40">
						· latest {latestVersion} · {allReleases.length} entries
					</span>
				</h2>

				<div class="flex flex-wrap gap-1.5 mb-4">
					{#each releaseTypes as t}
						<button
							type="button"
							class="btn btn-xs {releaseFilter === t ? 'btn-primary' : 'btn-ghost'}"
							on:click={() => {
								releaseFilter = t;
								releaseLimit = 50;
							}}
						>
							{t === 'all' ? 'All' : RELEASE_TYPE_LABEL[t] ?? t}
							<span class="ml-1 opacity-60">
								{t === 'all'
									? allReleases.length
									: allReleases.filter((r) => r.type === t).length}
							</span>
						</button>
					{/each}
				</div>

				{#if filteredReleases.length === 0}
					<p class="text-sm text-base-content/50">
						No entries match this filter.
					</p>
				{:else}
					<ol class="space-y-2">
						<!-- Composite each-key: version + commit, not just commit. Rationale:
						     entries can briefly hold commit: "pending" as a placeholder
						     between committing-with-the-entry and filling in the real SHA.
						     A bare `r.commit` key crashes the render with "duplicate keys"
						     if two pending entries coexist. Version is always unique
						     (enforced by src/lib/data/changelog.test.ts) and discriminates. -->
						{#each visibleReleases as r (`${r.version}-${r.commit}`)}
							<li
								class="flex items-start gap-3 rounded-lg border border-base-300/40 p-3"
							>
								<div class="flex-shrink-0 w-20 text-right">
									<div class="font-mono text-xs font-semibold tracking-tight">
										{r.version}
									</div>
									<div class="text-[10px] text-base-content/50 mt-0.5">
										{r.date}
									</div>
								</div>
								<div class="flex-1 min-w-0">
									<div class="flex items-start gap-2 flex-wrap">
										<span class="badge badge-sm {RELEASE_TYPE_BADGE[r.type] ?? 'badge-ghost'}">
											{RELEASE_TYPE_LABEL[r.type] ?? r.type}
										</span>
										<p class="text-sm text-base-content/90 flex-1 min-w-0">
											{r.summary}
										</p>
									</div>
									<div class="text-[10px] text-base-content/40 font-mono mt-1">
										{r.commit}
									</div>
								</div>
							</li>
						{/each}
					</ol>

					{#if visibleReleases.length < filteredReleases.length}
						<div class="text-center mt-4">
							<button
								type="button"
								class="btn btn-sm btn-outline"
								on:click={() => (releaseLimit += 50)}
							>
								Show more
								<span class="opacity-60">
									({filteredReleases.length - visibleReleases.length} remaining)
								</span>
							</button>
						</div>
					{/if}
				{/if}
			</section>
		{/if}
	</div>
{/if}
