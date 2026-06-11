<script lang="ts">
	/**
	 * V4 Leaderboard (v2.164.0) — Standings / The Race / Insights.
	 *
	 * Spec: mockups/Leaderboard-redesign/ (README + ACCEPTANCE). Three
	 * views over one data load; entry drawer on row click; pool filters
	 * keep global ranks. Pre-deadline (or flag off) renders the same
	 * pre-tournament stub this page has shown since v2.x.
	 */
	import { onDestroy, onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import { fetchAllFixtures, fixtures } from '$stores/fixtures';
	import { phase1Deadline, postDeadlineLive } from '$stores/phase';
	import { pageTitle } from '$stores/pageTitle';
	import { getAllTrajectories, getLeaderboardV4, getScoringRules } from '$api/leaderboard';
	import { getBonusMeta, type BonusMeta } from '$api/bonus';
	import type { LbEntryV4, LbPool, LbResponseV4, LbView } from '$lib/types/leaderboard';
	import type { ScoringRules } from '$lib/types/results';
	import {
		deriveStage,
		filterByPool,
		multiEntryUserIds,
		searchRows
	} from '$lib/utils/leaderboardV4';
	import StandingsTable from '$lib/components/leaderboard/v4/StandingsTable.svelte';
	import YourEntriesStrip from '$lib/components/leaderboard/v4/YourEntriesStrip.svelte';
	import EntryDrawer from '$lib/components/leaderboard/v4/EntryDrawer.svelte';
	import RaceChart from '$lib/components/leaderboard/v4/RaceChart.svelte';
	import InsightsGrid from '$lib/components/leaderboard/v4/InsightsGrid.svelte';

	// v2.166.0: the deadline passing no longer auto-opens the page —
	// release is the admin's manual "Go live" switch on /admin
	// (competitions.post_deadline_live, read via phase-status). Admins
	// always see V4 so they can verify before flipping it.
	const V4_LEADERBOARD_ENABLED = true;
	$: lbOpen = V4_LEADERBOARD_ENABLED && ($user?.is_admin === true || $postDeadlineLive);

	$: if (!$isAuthenticated) goto('/login');

	// ── view + pool persistence ──
	const VIEW_KEY = 'predictor:lb:view';
	const POOL_KEY = 'predictor:lb:pool';
	const VIEWS: { id: LbView; label: string; sub: string }[] = [
		{ id: 'table', label: 'Standings', sub: '' },
		{ id: 'race', label: 'The Race', sub: 'rank over time' },
		{ id: 'insights', label: 'Insights', sub: 'for the nerds' }
	];
	let view: LbView = 'table';
	let pool: LbPool = 'All';
	if (browser) {
		const v = localStorage.getItem(VIEW_KEY);
		if (v === 'table' || v === 'race' || v === 'insights') view = v;
		const p = localStorage.getItem(POOL_KEY);
		if (p === 'All' || p === 'Atlas' || p === 'JMFA' || p === 'Guests') pool = p;
	}
	function setView(v: LbView) {
		view = v;
		if (browser) localStorage.setItem(VIEW_KEY, v);
	}
	function setPool(p: LbPool) {
		pool = p;
		if (browser) localStorage.setItem(POOL_KEY, p);
	}

	// ── data ──
	let board: LbResponseV4 | null = null;
	let rules: ScoringRules | null = null;
	let bonusMeta: BonusMeta | null = null;
	/** entry_id → points-over-time series, for the standings sparkline.
	 *  Populated from the bulk snapshots endpoint; empty if it 403s
	 *  pre-deadline (sparklines fall back to a dash placeholder). */
	let trajectoriesByEntry = new Map<string, number[]>();
	let loading = true;
	let loadError = false;
	let selected: LbEntryV4 | null = null;
	let pollTimer: ReturnType<typeof setInterval> | null = null;

	async function load() {
		loadError = false;
		try {
			// Critical path only — the standings table renders the moment
			// these three land. The snapshots call (every entry × 14 days)
			// is by far the heaviest request and used to gate first paint
			// behind itself; it now hydrates the sparklines in the
			// background, as does the bonus meta (insights-only).
			const [b, , r] = await Promise.all([
				getLeaderboardV4(),
				fetchAllFixtures(),
				getScoringRules()
			]);
			board = b;
			rules = r;
		} catch {
			loadError = true;
		}
		loading = false;

		void getBonusMeta()
			.then((m) => (bonusMeta = m))
			.catch(() => undefined);
		void getAllTrajectories(14)
			.then((traj) => {
				trajectoriesByEntry = new Map(
					traj.entries.map((t) => [t.entry_id, t.points.map((p) => p.total_points)])
				);
			})
			.catch(() => undefined);
	}

	onMount(() => pageTitle.set('Standings'));

	// Load reactively, not in onMount — $phase1Deadline hydrates after this
	// page mounts (same race the results page hit), so a one-shot mount
	// check would skip the fetch and strand the page at "0 entries".
	let loadRequested = false;
	$: if ($isAuthenticated && lbOpen && !loadRequested) {
		loadRequested = true;
		void load();
		// Refresh standings every 60s while the page is open (backend
		// cache TTL is 30s, so this stays cheap).
		pollTimer = setInterval(() => {
			getLeaderboardV4()
				.then((b) => (board = b))
				.catch(() => {});
		}, 60_000);
	}
	onDestroy(() => {
		if (pollTimer) clearInterval(pollTimer);
	});

	let search = '';
	$: rows = board?.entries ?? [];
	$: stage = deriveStage($fixtures);
	$: filteredRows = searchRows(filterByPool(rows, pool), search);
	$: multiOwners = multiEntryUserIds(rows);
	$: playedCount = $fixtures.filter((f) => f.status === 'finished').length;

	function formatKickoff(iso: string | null): string {
		if (!iso) return '';
		try {
			return new Date(iso).toLocaleDateString(undefined, {
				weekday: 'short',
				day: 'numeric',
				month: 'short'
			});
		} catch {
			return '';
		}
	}
</script>

<svelte:head>
	<title>Standings — Predictor v2</title>
</svelte:head>

{#if $isAuthenticated && !lbOpen}
	<div class="hero min-h-[60vh]">
		<div class="hero-content text-center">
			<div class="max-w-md">
				<h2 class="font-display text-3xl tracking-wide">Standings open at kickoff</h2>
				<p class="mt-3 text-base-content/60">
					{#if $phase1Deadline}
						We start scoring once the first match begins —
						<span class="text-warning-text font-semibold">{formatKickoff($phase1Deadline)}</span>.
					{:else}
						We start scoring once the first match of the tournament begins.
					{/if}
				</p>
				<a href="/entries" class="btn btn-primary btn-lg mt-6 shadow-glow-gold">
					Lock in your predictions
				</a>
			</div>
		</div>
	</div>
{/if}

{#if $isAuthenticated && lbOpen}
	<div class="container mx-auto max-w-[1180px] mobile-padding pb-6 pt-3">
		<!-- ── slim header: info line left, view pills right (the navbar
		     already titles the page — no big heading). On mobile the
		     pills shrink and drop their sub-labels so all three fit in
		     one row alongside the info line. ── -->
		<div class="mb-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
			<p class="text-[12px] text-base-content/70 sm:text-[13px]">
				{board?.total_participants ?? rows.length} entries
				{#if playedCount > 0}· {playedCount} of {$fixtures.length} matches played{/if}
				· predictions locked since kick-off
			</p>
			<div class="flex gap-1.5 sm:gap-2">
				{#each VIEWS as v}
					<button
						class="inline-flex items-center gap-1.5 rounded-btn border-[1.5px] px-2.5 py-1 font-display text-[11px] font-bold tracking-[0.04em] transition-all sm:gap-2 sm:px-4 sm:py-2 sm:text-xs {view ===
						v.id
							? 'border-primary bg-primary/15 text-primary ring-4 ring-primary/20'
							: 'border-transparent bg-base-200 text-base-content/70 hover:text-base-content'}"
						on:click={() => setView(v.id)}
					>
						<span>{v.label}</span>
						{#if v.sub}<span class="hidden text-[10px] font-bold opacity-55 sm:inline">{v.sub}</span>{/if}
					</button>
				{/each}
			</div>
		</div>

		<YourEntriesStrip {rows} userId={$user?.id} {pool} onPool={setPool} bind:search />

		{#if loading}
			<!-- skeleton: same card + row rhythm as the real table -->
			<div class="overflow-hidden rounded-xl border border-base-300/60 bg-base-200">
				<div class="bg-base-300/40 px-4 py-2">
					<div class="h-3 w-40 animate-pulse rounded bg-base-300"></div>
				</div>
				{#each Array(10) as _}
					<div class="flex items-center gap-4 border-t border-base-300/40 px-4 py-2">
						<div class="h-4 w-10 animate-pulse rounded bg-base-300"></div>
						<div class="h-6 w-6 animate-pulse rounded-full bg-base-300"></div>
						<div class="h-4 flex-1 animate-pulse rounded bg-base-300"></div>
						<div class="h-4 w-14 animate-pulse rounded bg-base-300"></div>
					</div>
				{/each}
			</div>
		{:else if loadError}
			<div class="rounded-xl border border-error/40 bg-error/10 px-5 py-6 text-center">
				<p class="text-sm text-base-content/80">Couldn't load the leaderboard.</p>
				<button
					class="btn btn-outline btn-sm mt-3"
					on:click={() => {
						loading = true;
						void load();
					}}>Retry</button
				>
			</div>
		{:else if view === 'table'}
			<StandingsTable
				rows={filteredRows}
				{stage}
				userId={$user?.id}
				{multiOwners}
				{trajectoriesByEntry}
				onOpen={(row) => (selected = row)}
			/>
		{:else if view === 'race'}
			<RaceChart {rows} userId={$user?.id} fixtures={$fixtures} />
		{:else if view === 'insights'}
			<InsightsGrid
				{rows}
				{rules}
				{bonusMeta}
				userId={$user?.id}
				fixtures={$fixtures}
			/>
		{/if}

		{#if selected}
			<EntryDrawer
				row={selected}
				isOwn={selected.user_id === $user?.id}
				{rules}
				{multiOwners}
				onClose={() => (selected = null)}
			/>
		{/if}
	</div>
{/if}
