<script lang="ts">
	// /admin Overview — slimmed down in v2.160.0 from a 1300-line
	// kitchen-sink page into its focused sub-tabs:
	//
	//   Score Sync card         → /admin/sync
	//   Entries panel           → /admin/entries (already lived there)
	//   Bonus Question Answers  → /admin/bonus
	//   User Management         → /admin/users + /admin/users/[id]
	//   Release Notes           → /admin/releases
	//
	// Overview now hosts ONLY the cards that don't fit anywhere else:
	// stats, Competition Start, Phase II Activation, Entry Settings,
	// and the new Broadcast Emails card (P0 — admin nudges three
	// audience segments before the 2026-06-11 deadline).
	//
	// Auth guards live in admin/+layout.svelte:33-34 only — duplicating
	// them here caused a goto('/') race during the brief $user-null
	// hydration window.
	import { onMount } from 'svelte';
	import { isAuthenticated, user } from '$stores/auth';
	import {
		fetchPhaseStatus,
		groupStageWinnerReleased,
		isPhase2Active,
		phase1Deadline,
		phase2BracketDeadline,
		phase1Countdown,
		phase2Countdown,
		postDeadlineLive
	} from '$stores/phase';
	import {
		getAdminStats,
		getCompetitions,
		setPhase1Deadline,
		activatePhase2,
		deactivatePhase2,
		getAdminEntrySettings,
		updateAdminEntrySettings,
		getBroadcastAudienceCounts,
		sendBroadcast,
		sendBroadcastTest,
		setGroupStageWinnerReleased,
		setPostDeadlineLive,
		getPoolClosePreview,
		runPoolClose,
		type PoolClosePreview,
		type AdminStats,
		type CompetitionAdminView,
		type EntrySettingsUpdate,
		type BroadcastSegment,
		type BroadcastAudienceCounts,
		type BroadcastSendResult
	} from '$lib/api/admin';
	import type { EntrySettings } from '$lib/types/entry';
	import SitePulsePanel from '$lib/components/admin/SitePulsePanel.svelte';

	// ─── Stats / competition state ─────────────────────────────────────────
	let stats: AdminStats | null = null;
	let competitions: CompetitionAdminView[] = [];
	let loading = true;
	let error: string | null = null;

	// ─── Phase 1 deadline form ─────────────────────────────────────────────
	let phase1DeadlineDate = '';
	let phase1DeadlineTime = '12:00';
	let settingPhase1 = false;
	let phase1Error: string | null = null;
	let phase1Success: string | null = null;

	// ─── Post-deadline go-live switch (v2.166.0) ──────────────────────────
	let togglingLive = false;
	let goLiveError: string | null = null;

	async function handleToggleGoLive() {
		const next = !$postDeadlineLive;
		const message = next
			? 'Open the dashboard, results and leaderboard to the WHOLE pool? Every signed-in player sees them immediately.'
			: 'Pull the post-deadline pages back behind the holding screen for non-admins?';
		if (!confirm(message)) return;
		togglingLive = true;
		goLiveError = null;
		try {
			await setPostDeadlineLive(next);
			await fetchPhaseStatus();
		} catch (e) {
			goLiveError = e instanceof Error ? e.message : 'Toggle failed';
		} finally {
			togglingLive = false;
		}
	}

	// ─── Group Stage Winner release (v2.181.0) ────────────────────────────
	let togglingGsw = false;
	let gswError: string | null = null;

	async function handleToggleGsw() {
		const next = !$groupStageWinnerReleased;
		const message = next
			? 'RELEASE the Group Stage Winner card + broadcast? The card will appear on every dashboard within ~60s; the GROUP_STAGE_FINAL broadcast template will pull live winner data when sent.'
			: 'RETRACT the Group Stage Winner card + broadcast? Use this only to fix a late scoring correction; recipients of the email won\'t get a second one if you re-flip.';
		if (!confirm(message)) return;
		togglingGsw = true;
		gswError = null;
		try {
			await setGroupStageWinnerReleased(next);
			await fetchPhaseStatus();
		} catch (e) {
			gswError = e instanceof Error ? e.message : 'Toggle failed';
		} finally {
			togglingGsw = false;
		}
	}

	// ─── Close the pool (v2.166.0) ─────────────────────────────────────────
	let poolPreview: PoolClosePreview | null = null;
	let poolPreviewLoading = false;
	let poolClosing = false;
	let poolCloseError: string | null = null;
	let poolCloseSuccess: string | null = null;

	async function loadPoolPreview() {
		poolPreviewLoading = true;
		poolCloseError = null;
		try {
			poolPreview = await getPoolClosePreview();
		} catch (e) {
			poolCloseError = e instanceof Error ? e.message : 'Failed to load preview';
		} finally {
			poolPreviewLoading = false;
		}
	}

	async function handleClosePool() {
		if (!poolPreview) return;
		const n = poolPreview.accounts_to_disable;
		if (
			!confirm(
				`Disable ${n} account${n === 1 ? '' : 's'} with no submitted entry? ` +
					'They will no longer be able to sign in. Admins are exempt; ' +
					'individual accounts can be re-enabled from Users.'
			)
		)
			return;
		poolClosing = true;
		poolCloseError = null;
		poolCloseSuccess = null;
		try {
			const result = await runPoolClose();
			poolCloseSuccess = `Done — ${result.disabled_count} account${
				result.disabled_count === 1 ? '' : 's'
			} disabled.`;
			await loadPoolPreview();
		} catch (e) {
			poolCloseError = e instanceof Error ? e.message : 'Close failed';
		} finally {
			poolClosing = false;
		}
	}

	// ─── Phase 2 activation form ───────────────────────────────────────────
	let bracketDeadlineDate = '';
	let bracketDeadlineTime = '12:00';
	let activating = false;
	let activationError: string | null = null;
	let activationSuccess: string | null = null;

	// ─── Entry settings form ───────────────────────────────────────────────
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
			settingsError =
				e instanceof Error ? e.message : 'Failed to load entry settings';
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
			settingsError =
				e instanceof Error ? e.message : 'Failed to save settings';
		} finally {
			settingsSaving = false;
		}
	}

	function handleResetSettings() {
		if (entrySettings) settingsDraft = { ...entrySettings };
		settingsError = null;
		settingsSuccess = null;
	}

	// ─── Broadcast email card (v2.160.0) ──────────────────────────────────
	type Segment = BroadcastSegment;

	const SEGMENT_LABELS: Record<Segment, { title: string; description: string }> = {
		submitters: {
			title: 'Thank submitters',
			description:
				"Players who've submitted at least one entry. The message thanks them and encourages additional entries."
		},
		no_entry: {
			title: 'Nudge signed-up users',
			description:
				"Players who completed signup but haven't created any entry yet. Encourages them to make their picks."
		},
		draft_holders: {
			title: 'Push draft holders to submit',
			description:
				"Players with at least one draft entry but no submitted entries. Reminds them drafts don't count toward scoring."
		},
		// v2.176.0 — re-engagement cohorts during the live tournament.
		pool_ghost: {
			title: 'Wake up Pool Ghosts',
			description:
				"Players who submitted an entry but haven't been on the site since the tournament started. Friendly nudge to come check results. Audience refreshes on page load."
		},
		lapsing: {
			title: 'Pull back lapsing players',
			description:
				"Players who were active early but haven't visited in the last 3-7 days. Soft 'matchday is coming up' nudge with leaderboard CTA."
		},
		// v2.178.0 — one-off recap nudge sent when Round 1 of the group
		// stage wraps. Same audience as Thank Submitters, but the body
		// is a tournament-progress recap (standings, sheet, prize pot).
		group_r1_recap: {
			title: 'Group Stage Round 1 recap',
			description:
				"One-off round-recap email. Same audience as Thank Submitters (everyone with a submitted entry), but the body summarises live standings, the public Google Sheet, and the prize breakdown. CTA lands on /leaderboard with UTM tagging so PostHog can attribute click-throughs."
		},
		// v2.180.0 — Round 2 recap. Twin of R1; sent the morning Round 2
		// wraps, ahead of the Sunday 28 Group Stage winner announcement.
		// Body has placeholder slots ({{TOP_1}}, {{R2_HERO}}, etc.) that
		// MUST be filled in inside services/email.py before pressing
		// "Send broadcast" — otherwise recipients see literal braces.
		group_r2_recap: {
			title: 'Group Stage Round 2 recap',
			description:
				"One-off Round 2 recap. Same audience as Thank Submitters. Body has leaderboard-highlight placeholders ({{TOP_1}}, {{R2_HERO}}, {{CLIMBERS}}, etc.) that need filling in services/email.py before sending. CTA tagged utm_campaign=group_r2_recap."
		},
		// v2.181.0 — Group Stage champion announcement. Sent ~7pm Malta
		// Sunday 28 June, after admin flips the release toggle. Body
		// auto-fills the winner's name + 4-part points breakdown + story
		// line. GATED: backend returns empty tokens until release flag
		// flips, so a test send before release surfaces literal
		// {{WINNER_NAME}} placeholders. Test only AFTER pressing release.
		group_stage_final: {
			title: 'Group Stage champion announcement',
			description:
				"Sunday 28 June ~7pm Malta. Auto-fills winner name + 4-part points breakdown + story line. Flip the 'Group Stage Winner release' switch above FIRST; test-send only after release, otherwise placeholders surface as literal {{WINNER_NAME}} text."
		}
	};

	const SEGMENT_ORDER: Segment[] = [
		'submitters',
		'no_entry',
		'draft_holders',
		'pool_ghost',
		'lapsing',
		'group_r1_recap',
		'group_r2_recap',
		'group_stage_final'
	];

	let audienceCounts: BroadcastAudienceCounts | null = null;
	let countsLoading = false;
	let countsError: string | null = null;

	// Per-segment in-flight state (one segment active at a time is fine).
	let testingSegment: Segment | null = null;
	let testResult: { segment: Segment; sent: boolean; to: string; error: string | null } | null = null;

	// Confirmation modal state.
	let modalSegment: Segment | null = null;
	let modalPreview: BroadcastSendResult | null = null;
	let modalPreviewLoading = false;
	let modalSending = false;
	let modalError: string | null = null;
	let lastSendResult: BroadcastSendResult | null = null;

	async function loadAudienceCounts() {
		countsLoading = true;
		countsError = null;
		try {
			audienceCounts = await getBroadcastAudienceCounts();
		} catch (e) {
			countsError =
				e instanceof Error ? e.message : 'Failed to load audience counts';
		} finally {
			countsLoading = false;
		}
	}

	async function handleTestSend(segment: Segment) {
		testingSegment = segment;
		testResult = null;
		try {
			const r = await sendBroadcastTest(segment);
			testResult = {
				segment,
				sent: r.sent,
				to: r.to_email,
				error: r.error
			};
		} catch (e) {
			testResult = {
				segment,
				sent: false,
				to: '',
				error: e instanceof Error ? e.message : 'Test send failed'
			};
		} finally {
			testingSegment = null;
			setTimeout(() => {
				if (testResult?.segment === segment) testResult = null;
			}, 6000);
		}
	}

	async function openBroadcastModal(segment: Segment) {
		modalSegment = segment;
		modalPreview = null;
		modalError = null;
		modalPreviewLoading = true;
		try {
			modalPreview = await sendBroadcast(segment, true);
		} catch (e) {
			modalError = e instanceof Error ? e.message : 'Failed to preview broadcast';
		} finally {
			modalPreviewLoading = false;
		}
	}

	function closeBroadcastModal() {
		modalSegment = null;
		modalPreview = null;
		modalSending = false;
		modalError = null;
	}

	async function confirmBroadcastSend() {
		if (!modalSegment) return;
		modalSending = true;
		modalError = null;
		try {
			lastSendResult = await sendBroadcast(modalSegment, false);
			closeBroadcastModal();
			await loadAudienceCounts();
			// Auto-dismiss the result toast after 12s.
			setTimeout(() => {
				lastSendResult = null;
			}, 12000);
		} catch (e) {
			modalError = e instanceof Error ? e.message : 'Broadcast send failed';
		} finally {
			modalSending = false;
		}
	}

	// ─── Lifecycle ─────────────────────────────────────────────────────────
	// Unconditional load — the admin layout guards auth, and the
	// backend's cookie-based auth handles the per-call check. Gating on
	// `$user?.is_admin` here introduced a hydration race: onMount fires
	// once, and if the auth store hasn't hydrated by then the loaders
	// never run and `loading` stays true forever.
	onMount(async () => {
		await loadData();
		await Promise.all([loadEntrySettings(), loadAudienceCounts(), loadPoolPreview()]);
	});

	async function loadData() {
		loading = true;
		error = null;
		try {
			[stats, competitions] = await Promise.all([
				getAdminStats(),
				getCompetitions()
			]);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load admin data';
		} finally {
			loading = false;
		}
	}

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
			phase1Error =
				e instanceof Error ? e.message : 'Failed to set Phase 1 deadline';
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
			activationSuccess = `Phase 2 activated! Bracket deadline: ${new Date(
				result.bracket_deadline
			).toLocaleString()}`;
			await Promise.all([loadData(), fetchPhaseStatus()]);
		} catch (e) {
			activationError =
				e instanceof Error ? e.message : 'Failed to activate Phase 2';
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
			activationError =
				e instanceof Error ? e.message : 'Failed to deactivate Phase 2';
		} finally {
			activating = false;
		}
	}

	$: activeCompetition = competitions.find((c) => c.is_active);

	function audienceCountFor(s: Segment): number | null {
		if (!audienceCounts) return null;
		return audienceCounts[s];
	}
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
				<p class="text-sm text-base-content/50">
					Configuration, phases, and broadcast nudges
				</p>
			</div>
			<div class="text-right text-xs text-base-content/40">
				{activeCompetition?.name ?? 'no competition active'}
			</div>
		</div>

		{#if loading}
			<p class="text-sm text-base-content/50">Loading admin data…</p>
		{:else if error}
			<div class="alert alert-error">
				{error}
				<button class="btn btn-sm btn-ghost" on:click={loadData}>Retry</button>
			</div>
		{:else}
			<!-- Site Pulse panel (v2.176.0) — at-a-glance engagement.
			     Mounted FIRST: 4 widgets (DAU sparkline, top pages w/ trend,
			     top events w/ trend, recent logins). PostHog widgets silent-
			     fail if PostHog is down. -->
			<SitePulsePanel />

			<!-- Stats: Users · Entries · Prize money (v2.160.0).
			     Fixtures + Live moved off the Overview — Fixtures live on
			     /admin/sync; live match counts haven't proven useful on
			     this page so they're dropped. -->
			{#if stats}
				<div class="grid grid-cols-2 sm:grid-cols-3 gap-4">
					<div class="stat-card">
						<p class="stat-title">Users</p>
						<p class="stat-value">{stats.total_users}</p>
						<p class="text-xs text-base-content/40 mt-1">{stats.active_users} active</p>
					</div>
					<div class="stat-card">
						<p class="stat-title">Entries</p>
						<p class="stat-value">{stats.total_entries}</p>
						<p class="text-xs text-base-content/40 mt-1">
							{stats.submitted_entries} submitted
						</p>
					</div>
					<div class="stat-card">
						<p class="stat-title">Prize money</p>
						<p class="stat-value">
							{stats.prize_pool.toLocaleString(undefined, {
								maximumFractionDigits: 0
							})}
						</p>
						<p class="text-xs text-base-content/40 mt-1">
							fee × {stats.submitted_entries} submitted
						</p>
					</div>
				</div>
			{/if}

			<!-- Competition starts at -->
			<section class="rounded-xl border bg-base-200 shadow-card p-5">
				<h2 class="text-lg font-display tracking-wide mb-3">
					Competition starts at
					<span class="text-xs text-base-content/40">
						· locks predictions, kicks off scoring
					</span>
				</h2>
				<div class="text-sm mb-3">
					<b>Starts:</b>
					{#if $phase1Deadline}
						{new Date($phase1Deadline).toLocaleString()} ·
						<span class={$phase1Countdown === 'Locked' ? 'text-error' : 'text-success'}>
							{$phase1Countdown}
						</span>
					{:else}
						<span class="text-warning-text">NOT SET</span>
					{/if}
				</div>
				{#if phase1Error}<div class="alert alert-error text-sm mb-3">{phase1Error}</div>{/if}
				{#if phase1Success}<div class="alert alert-success text-sm mb-3">{phase1Success}</div>{/if}
				<div class="flex gap-3 items-end flex-wrap">
					<div class="form-control">
						<label class="label" for="p1-date"><span class="label-text">Date</span></label>
						<input
							id="p1-date"
							type="date"
							class="input input-bordered input-sm"
							bind:value={phase1DeadlineDate}
						/>
					</div>
					<div class="form-control">
						<label class="label" for="p1-time"><span class="label-text">Time</span></label>
						<input
							id="p1-time"
							type="time"
							class="input input-bordered input-sm"
							bind:value={phase1DeadlineTime}
						/>
					</div>
					<button
						class="btn btn-primary btn-sm"
						type="button"
						on:click={handleSetPhase1Deadline}
						disabled={settingPhase1}
					>
						{settingPhase1 ? 'Setting…' : 'Set competition start'}
					</button>
				</div>
			</section>

			<!-- Post-deadline release (v2.166.0) -->
			<section
				class="rounded-xl border bg-base-200 shadow-card p-5 {$postDeadlineLive
					? 'border-success/40'
					: 'border-warning/40'}"
			>
				<h2 class="text-lg font-display tracking-wide mb-1">
					Post-deadline release
					<span class="text-xs text-base-content/40">
						· dashboard, results &amp; leaderboard for the pool
					</span>
				</h2>
				<p class="text-xs text-base-content/55 mb-3 max-w-prose">
					The deadline passing does <b>not</b> open anything by itself. Non-admins see the
					"you're locked in" holding screen until you flip this. Admins always see the
					full pages — use the "View as pool" toggle on the home page to preview.
				</p>
				<div class="flex flex-wrap items-center gap-3">
					<span
						class="rounded-badge px-2.5 py-1 text-[11px] font-extrabold uppercase tracking-[0.12em] {$postDeadlineLive
							? 'bg-success/20 text-success'
							: 'bg-warning/20 text-warning-text'}"
					>
						{$postDeadlineLive ? 'LIVE — pool sees everything' : 'HOLDING — pool is waiting'}
					</span>
					<button
						class="btn btn-sm {$postDeadlineLive ? 'btn-ghost' : 'btn-primary'}"
						type="button"
						on:click={handleToggleGoLive}
						disabled={togglingLive}
					>
						{togglingLive ? 'Switching…' : $postDeadlineLive ? 'Pull back to holding' : '🚀 Go live'}
					</button>
				</div>
				{#if goLiveError}<div class="alert alert-error text-sm mt-3">{goLiveError}</div>{/if}
			</section>

			<!-- Group Stage Winner release (v2.181.0) -->
			<section
				class="rounded-xl border bg-base-200 shadow-card p-5 {$groupStageWinnerReleased
					? 'border-primary/50'
					: 'border-base-300'}"
			>
				<h2 class="text-lg font-display tracking-wide mb-1">
					Group Stage Winner release
					<span class="text-xs text-base-content/40">
						· dashboard card + champion broadcast
					</span>
				</h2>
				<p class="text-xs text-base-content/55 mb-3 max-w-prose">
					Press <b>Release champion</b> after R3 settles and you've verified final standings (≤7pm Malta, Sunday 28 June 2026). The
					GroupStageWinnerCard surfaces on every dashboard within ~60s and the GROUP_STAGE_FINAL broadcast template starts
					pulling live winner data. If a late scoring correction changes the standings, retract here and re-flip
					once corrected — the card and broadcast both re-render on the next 60s tick.
				</p>
				<div class="flex flex-wrap items-center gap-3">
					<span
						class="rounded-badge px-2.5 py-1 text-[11px] font-extrabold uppercase tracking-[0.12em] {$groupStageWinnerReleased
							? 'bg-primary/20 text-primary'
							: 'bg-base-300 text-base-content/55'}"
					>
						{$groupStageWinnerReleased ? '🏆 RELEASED — card visible to pool' : 'HOLDING — card hidden'}
					</span>
					<button
						class="btn btn-sm {$groupStageWinnerReleased ? 'btn-ghost' : 'btn-primary'}"
						type="button"
						on:click={handleToggleGsw}
						disabled={togglingGsw}
					>
						{togglingGsw ? 'Switching…' : $groupStageWinnerReleased ? 'Retract release' : '🏆 Release champion'}
					</button>
				</div>
				{#if gswError}<div class="alert alert-error text-sm mt-3">{gswError}</div>{/if}
			</section>

			<!-- Close the pool (v2.166.0) -->
			<section class="rounded-xl border border-error/30 bg-base-200 shadow-card p-5">
				<h2 class="text-lg font-display tracking-wide mb-1">
					Close the pool
					<span class="text-xs text-base-content/40">
						· disable accounts with no submitted entry
					</span>
				</h2>
				<p class="text-xs text-base-content/55 mb-3 max-w-prose">
					Post-deadline clean-up. Disables sign-in for every account that ended the
					competition without a counting submission — admins are exempt, drafts were
					already auto-withdrawn, and any account can be re-enabled individually from
					Users. Runs once; a re-run finds nothing left.
				</p>

				{#if poolPreviewLoading && !poolPreview}
					<span class="loading loading-spinner loading-sm text-primary"></span>
				{:else if poolPreview}
					<div class="mb-3 flex flex-wrap gap-x-5 gap-y-1 text-sm">
						<span>
							<b class="font-display {poolPreview.accounts_to_disable > 0 ? 'text-error' : ''}"
								>{poolPreview.accounts_to_disable}</b
							>
							<span class="text-base-content/60">accounts to disable</span>
						</span>
						<span>
							<b class="font-display text-success">{poolPreview.submitters_kept}</b>
							<span class="text-base-content/60">submitters kept</span>
						</span>
						<span>
							<b class="font-display">{poolPreview.eligible_submitted_entries}</b>
							<span class="text-base-content/60">entries in the prize pool</span>
						</span>
						<span>
							<b class="font-display">{poolPreview.drafts_withdrawn}</b>
							<span class="text-base-content/60">drafts auto-withdrawn</span>
						</span>
						<span>
							<b class="font-display">{poolPreview.admins_exempt}</b>
							<span class="text-base-content/60">admins exempt</span>
						</span>
					</div>
					<div class="flex flex-wrap items-center gap-3">
						<button
							class="btn btn-error btn-sm"
							type="button"
							on:click={handleClosePool}
							disabled={poolClosing ||
								!poolPreview.deadline_passed ||
								poolPreview.accounts_to_disable === 0}
						>
							{poolClosing
								? 'Closing…'
								: `Close the pool — disable ${poolPreview.accounts_to_disable} account${
										poolPreview.accounts_to_disable === 1 ? '' : 's'
								  }`}
						</button>
						<button
							class="btn btn-ghost btn-sm"
							type="button"
							on:click={loadPoolPreview}
							disabled={poolPreviewLoading}
						>
							Refresh counts
						</button>
						{#if poolPreview.accounts_to_disable > 0}
							<a
								href="/admin/users?cohort=no_submission"
								class="btn btn-ghost btn-sm text-primary"
							>
								View the {poolPreview.accounts_to_disable} accounts →
							</a>
						{/if}
						{#if !poolPreview.deadline_passed}
							<span class="text-xs text-warning-text">
								Locked until the deadline passes.
							</span>
						{/if}
					</div>
				{/if}
				{#if poolCloseSuccess}
					<div class="alert alert-success text-sm mt-3">{poolCloseSuccess}</div>
				{/if}
				{#if poolCloseError}
					<div class="alert alert-error text-sm mt-3">{poolCloseError}</div>
				{/if}
			</section>

			<!-- Phase 2 Activation -->
			<section class="rounded-xl border bg-base-200 shadow-card p-5">
				<h2 class="text-lg font-display tracking-wide mb-3">
					Phase II Activation
					<span class="text-xs text-base-content/40">· Knockout stage</span>
				</h2>
				<div class="text-sm mb-3">
					<b>Status:</b>
					{#if $isPhase2Active}
						<span class="text-success">ACTIVE</span>
						{#if $phase2BracketDeadline}
							· Bracket locks {new Date($phase2BracketDeadline).toLocaleString()} ·
							<span class={$phase2Countdown === 'Locked' ? 'text-error' : 'text-success'}>
								{$phase2Countdown}
							</span>
						{/if}
					{:else}
						<span class="text-warning-text">NOT ACTIVE</span>
					{/if}
				</div>
				{#if activationError}<div class="alert alert-error text-sm mb-3">{activationError}</div>{/if}
				{#if activationSuccess}<div class="alert alert-success text-sm mb-3">{activationSuccess}</div>{/if}
				<div class="flex gap-3 items-end flex-wrap">
					<div class="form-control">
						<label class="label" for="p2-date"><span class="label-text">Bracket lock date</span></label>
						<input
							id="p2-date"
							type="date"
							class="input input-bordered input-sm"
							bind:value={bracketDeadlineDate}
						/>
					</div>
					<div class="form-control">
						<label class="label" for="p2-time"><span class="label-text">Time</span></label>
						<input
							id="p2-time"
							type="time"
							class="input input-bordered input-sm"
							bind:value={bracketDeadlineTime}
						/>
					</div>
					<button
						class="btn btn-primary btn-sm"
						type="button"
						on:click={handleActivatePhase2}
						disabled={activating}
					>
						{activating ? 'Working…' : $isPhase2Active ? 'Update Phase II deadline' : 'Activate Phase II'}
					</button>
					{#if $isPhase2Active}
						<button
							class="btn btn-outline btn-error btn-sm"
							type="button"
							on:click={handleDeactivatePhase2}
							disabled={activating}
						>
							Deactivate Phase II
						</button>
					{/if}
				</div>
			</section>

			<!-- Entry Settings -->
			<section class="rounded-xl border bg-base-200 shadow-card p-5">
				<h2 class="text-lg font-display tracking-wide mb-3">
					Entry Settings
					{#if entrySettings}
						<span class="text-xs text-base-content/40">
							· max {entrySettings.max_entries_per_user}/user · {entrySettings.payment_mode}
						</span>
					{/if}
				</h2>
				{#if settingsLoading && !entrySettings}
					<p class="text-sm text-base-content/50">Loading…</p>
				{:else if settingsError}
					<div class="alert alert-error text-sm">
						{settingsError}
						<button class="btn btn-xs btn-ghost" on:click={loadEntrySettings}>Retry</button>
					</div>
				{:else if settingsDraft}
					{#if settingsSuccess}<div class="alert alert-success text-sm mb-3">{settingsSuccess}</div>{/if}
					<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
						<label class="form-control">
							<span class="label-text mb-1">Max entries per user</span>
							<input
								type="number"
								min="1"
								class="input input-bordered input-sm"
								bind:value={settingsDraft.max_entries_per_user}
							/>
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
								<input
									type="checkbox"
									class="checkbox checkbox-sm"
									checked={settingsDraft[f.key]}
									on:change={(e) => setBoolSetting(f.key, e.currentTarget.checked)}
								/>
								<span class="text-sm">{f.label}</span>
							</label>
						{/each}
					</div>
					<div class="flex gap-3 mt-4 flex-wrap">
						<button
							class="btn btn-primary btn-sm"
							type="button"
							on:click={handleSaveSettings}
							disabled={!settingsDirty || settingsSaving}
						>
							{settingsSaving ? 'Saving…' : settingsDirty ? 'Save changes' : 'Saved'}
						</button>
						<button
							class="btn btn-outline btn-sm"
							type="button"
							on:click={handleResetSettings}
							disabled={!settingsDirty || settingsSaving}
						>
							Reset
						</button>
					</div>
				{/if}
			</section>

			<!-- Broadcast Emails (v2.160.0) -->
			<section class="rounded-xl border bg-base-200 shadow-card p-5">
				<h2 class="text-lg font-display tracking-wide mb-3">
					Broadcast Emails
					<span class="text-xs text-base-content/40">
						· five audience segments · Resend
					</span>
				</h2>
				{#if countsError}
					<div class="alert alert-error text-sm mb-3">
						{countsError}
						<button class="btn btn-xs btn-ghost" on:click={loadAudienceCounts}>Retry</button>
					</div>
				{/if}
				{#if lastSendResult}
					<div class="alert alert-success text-sm mb-3">
						Broadcast sent to {lastSendResult.sent} users
						{#if lastSendResult.failed > 0}
							· <span class="text-error">{lastSendResult.failed} failed</span>
						{/if}
					</div>
				{/if}
				{#if testResult}
					<div class="alert {testResult.sent ? 'alert-success' : 'alert-error'} text-sm mb-3">
						{#if testResult.sent}
							Test email sent to {testResult.to}. Check your inbox.
						{:else}
							Test send failed: {testResult.error ?? 'unknown error'}
						{/if}
					</div>
				{/if}

				<div class="space-y-3">
					{#each SEGMENT_ORDER as seg}
						{@const meta = SEGMENT_LABELS[seg]}
						{@const count = audienceCountFor(seg)}
						<div class="rounded-lg border border-base-300/50 p-4 flex gap-4 items-start flex-wrap">
							<div class="flex-1 min-w-[240px]">
								<div class="flex items-center gap-2 flex-wrap">
									<span class="text-sm font-display tracking-wide">{meta.title}</span>
									{#if count !== null}
										<span class="badge badge-ghost text-xs">
											{count} {count === 1 ? 'user' : 'users'}
										</span>
									{:else if countsLoading}
										<span class="badge badge-ghost text-xs">…</span>
									{/if}
								</div>
								<p class="text-xs text-base-content/55 mt-1">{meta.description}</p>
							</div>
							<div class="flex gap-2 flex-wrap items-center">
								<button
									type="button"
									class="btn btn-outline btn-xs"
									on:click={() => handleTestSend(seg)}
									disabled={testingSegment === seg}
									title="Send the templated email to your own address"
								>
									{testingSegment === seg ? 'Sending…' : 'Send test to me'}
								</button>
								<button
									type="button"
									class="btn btn-primary btn-xs"
									on:click={() => openBroadcastModal(seg)}
									disabled={count === 0}
								>
									Send broadcast
								</button>
							</div>
						</div>
					{/each}
				</div>
				<p class="text-xs text-base-content/45 mt-3">
					Broadcasts emit one audit event per send (
					<code>admin.broadcast_sent</code>) — see <a href="/admin/audit" class="link">/admin/audit</a>.
					Tests do not emit audit events. With <code>RESEND_API_KEY</code> unset locally, the
					template body prints to the backend logs instead of sending.
				</p>
			</section>
		{/if}
	</div>

	<!-- Broadcast confirmation modal -->
	{#if modalSegment}
		<div
			class="fixed inset-0 z-40 bg-black/60 flex items-center justify-center p-4"
			role="dialog"
			aria-modal="true"
		>
			<div class="rounded-2xl border border-base-300 bg-base-200 shadow-xl max-w-md w-full p-6">
				<h3 class="text-lg font-display tracking-wide mb-2">
					Send broadcast: {SEGMENT_LABELS[modalSegment].title}
				</h3>
				{#if modalPreviewLoading}
					<p class="text-sm text-base-content/55">Looking up audience…</p>
				{:else if modalError}
					<div class="alert alert-error text-sm mb-3">{modalError}</div>
				{:else if modalPreview}
					<p class="text-sm mb-3">
						This will email <strong>{modalPreview.audience_count}</strong>
						{modalPreview.audience_count === 1 ? 'user' : 'users'}.
					</p>
					{#if modalPreview.sample_emails.length > 0}
						<p class="text-xs text-base-content/55 mb-2">First few recipients:</p>
						<ul class="text-xs font-mono space-y-0.5 mb-3">
							{#each modalPreview.sample_emails as e}
								<li class="text-base-content/70">{e}</li>
							{/each}
						</ul>
					{/if}
					<p class="text-xs text-base-content/55 mb-4">
						You can't undo a broadcast. If you need to bail, hit Cancel now.
					</p>
				{/if}
				<div class="flex justify-end gap-2">
					<button
						type="button"
						class="btn btn-ghost btn-sm"
						on:click={closeBroadcastModal}
						disabled={modalSending}
					>
						Cancel
					</button>
					<button
						type="button"
						class="btn btn-primary btn-sm"
						on:click={confirmBroadcastSend}
						disabled={modalSending || modalPreviewLoading || !modalPreview || modalPreview.audience_count === 0}
					>
						{modalSending ? 'Sending…' : `Send to ${modalPreview?.audience_count ?? 0} users`}
					</button>
				</div>
			</div>
		</div>
	{/if}
{/if}
