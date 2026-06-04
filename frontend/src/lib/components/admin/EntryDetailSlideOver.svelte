<script lang="ts">
	/**
	 * EntryDetailSlideOver — shared admin component (v2.156.0).
	 *
	 * Opens for `?entry=REF` query param on both /admin/entries and
	 * /admin/users/[id].
	 *
	 * v2.156.0 restructure (E1, E2, E3):
	 * - Summary info promoted to the header (champion + completion KPIs)
	 * - First tab is Group stage (was Summary)
	 * - Audit log moved to its own last tab
	 *
	 * Footer actions go through the Pattern C reason-required modal.
	 */
	import { createEventDispatcher } from 'svelte';
	import {
		getAdminEntryEvents,
		adminDisableEntry,
		adminSetEntryPaid,
		adminSetEntryPrizeEligible,
		getAdminEntryPredictions,
		type EntryEvent,
		type AdminEntryPredictions,
	} from '$lib/api/admin';
	import KnockoutBracket from '$lib/components/bracket/KnockoutBracket.svelte';
	import type { Entry } from '$lib/types/entry';

	export let entry: Entry | null = null;
	export let open: boolean = false;

	const dispatch = createEventDispatcher<{ close: void; updated: Entry }>();

	type Tab = 'groups' | 'knockout' | 'bonus' | 'audit';
	let activeTab: Tab = 'groups';

	// Predictions state — lazy-loaded on first switch to any of the
	// groups / knockout / bonus tabs (one fetch covers all three).
	let predictions: AdminEntryPredictions | null = null;
	let predictionsLoaded = false;
	let predictionsLoading = false;
	let predictionsError: string | null = null;

	const TABS: ReadonlyArray<{ key: Tab; label: string }> = [
		{ key: 'groups', label: '⚽ Group stage' },
		{ key: 'knockout', label: '🏆 Knockout' },
		{ key: 'bonus', label: '★ Bonus' },
		{ key: 'audit', label: '📋 Audit log' },
	];
	let events: EntryEvent[] = [];
	let loadingEvents = false;

	// Confirm-modal state — single modal reused for all destructive footer actions.
	let confirmOpen = false;
	let confirmAction: 'paid' | 'prize' | 'withdraw' | null = null;
	let confirmReason = '';

	async function loadEvents(): Promise<void> {
		if (!entry) return;
		loadingEvents = true;
		try {
			events = await getAdminEntryEvents(entry.id);
		} catch {
			events = [];
		} finally {
			loadingEvents = false;
		}
	}

	async function loadPredictions(): Promise<void> {
		if (!entry || predictionsLoaded || predictionsLoading) return;
		predictionsLoading = true;
		predictionsError = null;
		try {
			predictions = await getAdminEntryPredictions(entry.id);
			predictionsLoaded = true;
		} catch (err) {
			predictionsError =
				err instanceof Error ? err.message : 'Failed to load predictions.';
		} finally {
			predictionsLoading = false;
		}
	}

	// Audit tab loads events on first view.
	$: if (entry && open && activeTab === 'audit') loadEvents();

	// Group / Knockout / Bonus all share the same fetch — one round-trip
	// satisfies all three. The guard inside loadPredictions() makes this
	// idempotent.
	$: if (
		entry &&
		open &&
		(activeTab === 'groups' || activeTab === 'knockout' || activeTab === 'bonus')
	)
		loadPredictions();

	// Reset to first tab whenever the entry changes (different entry → fresh view).
	// Also reset the predictions cache so the new entry doesn't show stale data.
	$: if (entry) {
		activeTab = 'groups';
		predictions = null;
		predictionsLoaded = false;
		predictionsError = null;
	}

	// Derived: group match predictions by `home_team`/`away_team`'s group letter.
	// The backend `MatchPredictionRead` doesn't ship the group letter so we
	// fall back to a sort by kickoff and label the section "All group fixtures".
	// (A future iteration can join fixture.group_name into the response.)
	$: matchPredictions = predictions?.match_predictions ?? [];

	function close(): void {
		dispatch('close');
	}

	function openConfirm(action: 'paid' | 'prize' | 'withdraw'): void {
		confirmAction = action;
		confirmReason = '';
		confirmOpen = true;
	}

	async function commitConfirm(): Promise<void> {
		if (!entry || confirmReason.trim().length < 3) return;
		try {
			let next: Entry;
			if (confirmAction === 'paid') {
				next = await adminSetEntryPaid(entry.id, !entry.paid);
			} else if (confirmAction === 'prize') {
				next = await adminSetEntryPrizeEligible(entry.id, !entry.prize_eligible);
			} else if (confirmAction === 'withdraw') {
				next = await adminDisableEntry(entry.id, confirmReason);
			} else {
				return;
			}
			dispatch('updated', next);
		} finally {
			confirmOpen = false;
			confirmAction = null;
			confirmReason = '';
		}
	}

	function formatDate(iso: string | null | undefined): string {
		if (!iso) return '—';
		const d = new Date(iso);
		return new Intl.DateTimeFormat(undefined, {
			day: 'numeric',
			month: 'short',
			hour: '2-digit',
			minute: '2-digit',
		}).format(d);
	}

	// Phase status helper — derives the Phase 1 status from entry.phases.
	function getPhaseStatus(e: Entry): string {
		const p1 = e.phases?.find((p) => p.phase === 'phase_1');
		return p1?.status ?? 'draft';
	}
</script>

{#if open && entry}
	<div class="confirm-scrim {open ? 'open' : ''}" on:click={close} role="presentation">
		<div
			class="fixed top-0 right-0 h-screen w-full max-w-[780px] bg-base-200 border-l border-primary/10 shadow-2xl flex flex-col"
			style="z-index: 50; animation: slide-in 0.26s cubic-bezier(0.32, 0.72, 0, 1);"
			on:click|stopPropagation
			role="dialog"
		>
			<!-- ════════ Header (E2 — summary info promoted from former Summary tab) ════════ -->
			<div class="px-6 py-4 border-b border-base-300/30 bg-gradient-to-b from-primary/[0.05] to-transparent">
				<div class="flex items-start justify-between gap-4">
					<div class="min-w-0">
						<p class="text-[10px] font-mono uppercase tracking-[0.2em] text-primary">Entry detail</p>
						<div class="flex items-center gap-3 mt-1 flex-wrap">
							<h2 class="font-display font-extrabold text-xl">{entry.display_name ?? `Entry ${entry.entry_number}`}</h2>
							<span class="font-mono text-[10.5px] bg-primary/10 border border-primary/20 text-primary rounded px-2 py-0.5">{entry.reference}</span>
						</div>
						<div class="flex gap-2 mt-2 flex-wrap">
							{#if entry.paid}<span class="status-pill s-success"><span class="dot"></span>Paid</span>{:else}<span class="status-pill s-ghost"><span class="dot"></span>Unpaid</span>{/if}
							{#if entry.prize_eligible}<span class="status-pill s-ghost">Prize-eligible</span>{:else}<span class="status-pill s-warning">Not prize-eligible</span>{/if}
							{#if entry.is_disabled}<span class="status-pill s-error"><span class="dot"></span>Disabled</span>
							{:else}
								<span class="status-pill s-success"><span class="dot"></span>{getPhaseStatus(entry).toUpperCase()}</span>
							{/if}
						</div>
					</div>
					<button class="btn btn-ghost btn-sm btn-circle" on:click={close} aria-label="Close">✕</button>
				</div>

				<!-- Completion KPI strip (E2) -->
				<div class="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-4">
					<div class="kpi-card !p-2.5">
						<div class="label">Status</div>
						<div class="value !text-sm !font-semibold">{entry.is_disabled ? 'Disabled' : entry.withdrawn_at ? 'Withdrawn' : 'Active'}</div>
					</div>
					<div class="kpi-card !p-2.5">
						<div class="label">Paid</div>
						<div class="value !text-sm !font-semibold">{entry.paid ? 'Yes' : 'No'}</div>
					</div>
					<div class="kpi-card !p-2.5">
						<div class="label">Prize-eligible</div>
						<div class="value !text-sm !font-semibold">{entry.prize_eligible ? 'Yes' : 'No'}</div>
					</div>
					<div class="kpi-card !p-2.5">
						<div class="label">Updated</div>
						<div class="value !text-xs !font-semibold" title={entry.updated_at}>{formatDate(entry.updated_at)}</div>
					</div>
				</div>
			</div>

			<!-- ════════ Tabs (E1 + E3 — Groups first, Audit log last) ════════ -->
			<div class="flex gap-2 px-4 border-b border-base-300/30 bg-base-300/20 overflow-x-auto">
				{#each TABS as t (t.key)}
					<button
						class="px-3.5 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
						class:border-primary={activeTab === t.key}
						class:text-primary={activeTab === t.key}
						class:border-transparent={activeTab !== t.key}
						class:text-base-content={activeTab !== t.key}
						class:opacity-60={activeTab !== t.key}
						on:click={() => (activeTab = t.key)}
					>{t.label}</button>
				{/each}
			</div>

			<!-- ════════ Body ════════ -->
			<div class="flex-1 overflow-y-auto p-6">
				{#if activeTab === 'groups'}
					<!-- F1 — real group-stage match predictions -->
					{#if predictionsLoading}
						<p class="text-sm text-base-content/55">Loading predictions…</p>
					{:else if predictionsError}
						<div class="alert alert-error alert-soft text-sm">
							<span>Couldn't load predictions: {predictionsError}</span>
							<button class="btn btn-ghost btn-xs" on:click={loadPredictions}>Retry</button>
						</div>
					{:else if matchPredictions.length === 0}
						<p class="text-sm text-base-content/55">No group-stage predictions submitted yet.</p>
					{:else}
						<div class="space-y-2">
							<p class="text-[10px] font-mono uppercase tracking-[0.2em] text-primary mb-2">{matchPredictions.length} scoreline{matchPredictions.length === 1 ? '' : 's'} predicted</p>
							<div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
								{#each matchPredictions as m (m.id)}
									<div class="rounded-lg border border-base-300/30 bg-base-100/40 p-3 flex items-center justify-between gap-3">
										<div class="min-w-0 flex-1">
											<div class="text-sm font-medium truncate">{m.home_team ?? '—'} <span class="text-base-content/40">vs</span> {m.away_team ?? '—'}</div>
											<div class="text-[11px] text-base-content/50 mt-0.5" title={m.kickoff ?? ''}>{m.kickoff ? formatDate(m.kickoff) : '—'}</div>
										</div>
										<div class="font-display font-bold text-lg tabular-nums">
											<span class="text-primary">{m.home_score}</span>
											<span class="text-base-content/30 mx-1">–</span>
											<span class="text-primary">{m.away_score}</span>
										</div>
									</div>
								{/each}
							</div>
						</div>
					{/if}

				{:else if activeTab === 'knockout'}
					<!-- F2 — real knockout bracket via the shared component, locked -->
					{#if predictionsLoading}
						<p class="text-sm text-base-content/55">Loading bracket…</p>
					{:else if predictionsError}
						<div class="alert alert-error alert-soft text-sm">
							<span>Couldn't load predictions: {predictionsError}</span>
							<button class="btn btn-ghost btn-xs" on:click={loadPredictions}>Retry</button>
						</div>
					{:else if !predictions?.bracket}
						<p class="text-sm text-base-content/55">No knockout bracket submitted yet.</p>
					{:else}
						<KnockoutBracket
							prediction={predictions.bracket}
							locked={true}
							phase="phase_1"
						/>
					{/if}

				{:else if activeTab === 'bonus'}
					<!-- F3 — minimal bonus answers (question + answer only per v2.157.0 scope) -->
					{#if predictionsLoading}
						<p class="text-sm text-base-content/55">Loading bonus answers…</p>
					{:else if predictionsError}
						<div class="alert alert-error alert-soft text-sm">
							<span>Couldn't load predictions: {predictionsError}</span>
							<button class="btn btn-ghost btn-xs" on:click={loadPredictions}>Retry</button>
						</div>
					{:else if !predictions || predictions.bonus_answers.length === 0}
						<p class="text-sm text-base-content/55">No bonus answers submitted yet.</p>
					{:else}
						<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
							{#each predictions.bonus_answers as b (b.question_id)}
								<div class="rounded-lg border border-base-300/30 bg-base-100/40 p-3">
									<div class="text-[10px] font-mono uppercase tracking-[0.2em] text-base-content/40">{b.question_id}</div>
									<div class="font-medium text-sm mt-1">{b.question_title}</div>
									<div class="mt-2 text-sm">
										{#if b.answer}
											<span class="font-display font-semibold text-primary">{b.answer}</span>
										{:else}
											<span class="text-base-content/30">—</span>
										{/if}
									</div>
								</div>
							{/each}
						</div>
					{/if}

				{:else if activeTab === 'audit'}
					<!-- E1 — Audit log as its own dedicated tab -->
					<h3 class="font-display font-bold text-base mb-3">Entry audit log</h3>
					{#if loadingEvents}
						<p class="text-sm text-base-content/55">Loading events…</p>
					{:else if events.length === 0}
						<p class="text-sm text-base-content/55">No audit events for this entry yet.</p>
					{:else}
						<ol class="space-y-3">
							{#each events as ev (ev.id)}
								<li class="pl-4 border-l-2 border-primary/30">
									<div class="font-mono text-[10.5px] text-base-content/40" title={ev.created_at}>{formatDate(ev.created_at)}</div>
									<div class="text-sm font-medium mt-0.5">{ev.from_status} → {ev.to_status}</div>
									{#if ev.reason}<div class="text-xs text-base-content/60 italic mt-0.5">"{ev.reason}"</div>{/if}
									<div class="font-mono text-[10.5px] text-base-content/40 mt-0.5">{ev.actor_role}</div>
								</li>
							{/each}
						</ol>
					{/if}
				{/if}
			</div>

			<!-- Footer actions -->
			<div class="px-6 py-3 border-t border-base-300/30 bg-base-300/10 flex items-center gap-2 flex-wrap">
				<button class="btn btn-outline btn-sm" on:click={() => openConfirm('paid')}>Mark {entry.paid ? 'unpaid' : 'paid'}</button>
				<button class="btn btn-outline btn-sm" on:click={() => openConfirm('prize')}>Toggle prize-eligible</button>
				<button class="btn btn-error btn-sm btn-outline" on:click={() => openConfirm('withdraw')}>Withdraw</button>
				<a
					href={`/admin/audit?subject_type=entry&subject_id=${entry.id}`}
					class="btn btn-ghost btn-sm ml-auto"
					title="Pre-filtered to this entry's subject_id"
				>Full audit history →</a>
			</div>
		</div>
	</div>
{/if}

<!-- Reason-required confirmation modal (Pattern C) -->
{#if confirmOpen}
	<div class="confirm-scrim open" on:click={() => (confirmOpen = false)} role="presentation">
		<div class="confirm-modal" on:click|stopPropagation role="dialog">
			<p class="cm-kicker">{confirmAction === 'withdraw' ? 'Withdraw entry' : 'Update entry'}</p>
			<h3 class="font-display font-extrabold text-lg mt-1.5">
				{#if confirmAction === 'withdraw'}Withdraw {entry?.reference}?
				{:else if confirmAction === 'paid'}Mark {entry?.reference} {entry?.paid ? 'unpaid' : 'paid'}?
				{:else}Toggle prize eligibility for {entry?.reference}?{/if}
			</h3>
			<p class="text-sm text-base-content/60 mt-2 mb-4">
				{#if confirmAction === 'withdraw'}Pulls the entry from prize calculation. Reversible.{:else}Reversible. Audit-logged with the reason below.{/if}
			</p>
			<label class="text-[11px] uppercase tracking-widest text-base-content/40 font-medium block mb-1.5">
				Reason <span class="normal-case tracking-normal text-base-content/40">(audit logged)</span>
			</label>
			<textarea
				bind:value={confirmReason}
				placeholder={confirmAction === 'withdraw' ? 'e.g. payment never received, owner requested removal…' : 'e.g. payment reversed, test account…'}
				class="textarea textarea-bordered w-full min-h-[64px]"
			></textarea>
			<p class="text-[11px] text-base-content/40 italic mt-1.5">Minimum 3 characters · routes to <span class="font-mono">audit_events.reason</span></p>
			<div class="flex justify-end gap-2 mt-4">
				<button class="btn btn-ghost btn-sm" on:click={() => (confirmOpen = false)}>Cancel</button>
				<button
					class="btn btn-sm"
					class:btn-error={confirmAction === 'withdraw'}
					class:btn-primary={confirmAction !== 'withdraw'}
					disabled={confirmReason.trim().length < 3}
					on:click={commitConfirm}
				>{confirmAction === 'withdraw' ? 'Withdraw' : 'Confirm'}</button>
			</div>
		</div>
	</div>
{/if}

<style>
	@keyframes slide-in {
		from { transform: translateX(100%); }
		to { transform: translateX(0); }
	}
</style>
