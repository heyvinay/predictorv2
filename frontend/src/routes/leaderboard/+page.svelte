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
	import { page } from '$app/stores';
	import { isAuthenticated, user } from '$stores/auth';
	import { fetchAllFixtures, fixtures } from '$stores/fixtures';
	import { phase1Deadline, postDeadlineLive, winProbabilityEnabled, tournamentConcluded } from '$stores/phase';
	import { pageTitle } from '$stores/pageTitle';
	import {
		getAllTrajectories,
		getLeaderboardV4,
		getMatchMarkers,
		getScoringRules,
		getWinProbability
	} from '$api/leaderboard';
	import { startLivePoll } from '$lib/utils/livePoll';
	import { relativeAgo } from '$lib/utils/relativeTime';
	import { currentTime } from '$stores/phase';
	import { teamCode } from '$lib/utils/teamCodes';
	import ProvisionalPill from '$lib/components/ProvisionalPill.svelte';
	import LiveProjectionPill from '$lib/components/LiveProjectionPill.svelte';
	import { getBonusMeta, type BonusMeta } from '$api/bonus';
	import { track } from '$lib/analytics';
	import type {
		LbEntryV4,
		LbPool,
		LbResponseV4,
		LbView,
		RaceViewMode,
		MatchMarker,
		EntryTrajectory
	} from '$lib/types/leaderboard';
	import type { ScoringRules } from '$lib/types/results';
	import type { WinProbabilityResponse } from '$lib/types/winProbability';
	import {
		deriveStage,
		filterByPool,
		multiEntryUserIds,
		searchRows,
		selectRaceSlice
	} from '$lib/utils/leaderboardV4';
	import StandingsTable from '$lib/components/leaderboard/v4/StandingsTable.svelte';
	import YourEntriesStrip from '$lib/components/leaderboard/v4/YourEntriesStrip.svelte';
	import EntryDrawer from '$lib/components/leaderboard/v4/EntryDrawer.svelte';
	import RaceChart from '$lib/components/leaderboard/v4/RaceChart.svelte';
	import RaceStoryGrid from '$lib/components/leaderboard/v4/RaceStoryGrid.svelte';
	import RaceViewPills from '$lib/components/leaderboard/v4/RaceViewPills.svelte';
	import PoolDistribution from '$lib/components/dashboard/v4/PoolDistribution.svelte';
	import InsightsGrid from '$lib/components/leaderboard/v4/InsightsGrid.svelte';
	import WinProbabilityView from '$lib/components/leaderboard/v4/WinProbabilityView.svelte';

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
	// Inclusion list, not exclusion — Fixture.stage is plain `string`, so an
	// exclusion check (stage !== 'group' && stage !== 'third_place') gives
	// zero compile-time protection against a new/typo'd stage slipping
	// through. Mirrors the named-stage switch in resultsRounds.ts's
	// roundIdForFixture(), which excludes 'third_place' the same way for
	// the same documented reason (CLAUDE.md ★ third_place invariant).
	const KO_STAGES = ['round_of_32', 'round_of_16', 'quarter_final', 'semi_final', 'final'];
	// Win Probability is admin-gated by default; the /admin toggle flips
	// winProbabilityEnabled to open it to the whole pool (same recipe as
	// V4_LEADERBOARD_ENABLED's postDeadlineLive gate).
	$: VIEWS = (
		[
			{ id: 'table', label: 'Standings', sub: '' },
			{ id: 'race', label: 'The Race', sub: 'rank over time' },
			{ id: 'insights', label: 'Insights', sub: 'for the nerds' }
		] as { id: LbView; label: string; sub: string }[]
	).concat(
		$user?.is_admin === true || $winProbabilityEnabled
			? [{ id: 'win_probability', label: 'Win Probability', sub: 'pool odds' }]
			: []
	);
	let view: LbView = 'table';
	let pool: LbPool = 'All';
	if (browser) {
		const v = localStorage.getItem(VIEW_KEY);
		if (v === 'table' || v === 'race' || v === 'insights' || v === 'win_probability') view = v;
		const p = localStorage.getItem(POOL_KEY);
		if (p === 'All' || p === 'Atlas' || p === 'JMFA' || p === 'Guests') pool = p;
	}
	// A restored 'win_probability' view for someone who can no longer see
	// it (stale localStorage, admin status revoked, or the admin flipped
	// the flag back off) falls back to Standings rather than rendering a
	// tab that isn't in VIEWS.
	$: if (view === 'win_probability' && $user?.is_admin !== true && !$winProbabilityEnabled)
		view = 'table';
	function setView(v: LbView) {
		// Skip the telemetry when the user clicks the already-active tab —
		// adds noise without information.
		if (v !== view) track('leaderboard_view_changed', { view: v, from: view });
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
	/** entry_id → rank-over-time series, for the standings sparkline.
	 *  Populated from the bulk snapshots endpoint; empty if it 403s
	 *  pre-deadline (sparklines fall back to a dash placeholder). */
	let trajectoriesByEntry = new Map<string, number[]>();
	let loading = true;
	let loadError = false;
	let selected: LbEntryV4 | null = null;
	/** Side-by-side compare row (story-card "closest race" opens this). */
	let compareSelected: LbEntryV4 | null = null;
	/** Champion-pick cohort (champion-survival chip opens this). */
	let cohortSelected: { team_code: string; team_name: string; entry_ids: string[] } | null = null;
	let stopPoll: (() => void) | null = null;
	/** Win Probability tab state — lifted up here (not local to the child
	 *  component) so switching away and back to the tab reuses the last
	 *  result instead of refetching. Auto-fetched the first time the tab
	 *  opens (see the reactive below); `onRun` stays wired to the error
	 *  state's "Try again" for a manual retry. */
	let winProbData: WinProbabilityResponse | null = null;
	let winProbLoading = false;
	let winProbFailed = false;
	async function runWinProbability() {
		winProbLoading = true;
		winProbFailed = false;
		try {
			winProbData = await getWinProbability();
		} catch {
			winProbFailed = true;
		} finally {
			winProbLoading = false;
		}
	}
	// Auto-load the moment the tab is opened, reusing whatever's already
	// loaded on return visits. Setting winProbLoading synchronously inside
	// runWinProbability falsifies this guard before the next reactive
	// re-run, so there's no fetch loop. A failed fetch also stops
	// re-firing — the error state's "Try again" button is the only way
	// back in from there.
	$: if (
		browser &&
		lbOpen &&
		view === 'win_probability' &&
		!winProbData &&
		!winProbLoading &&
		!winProbFailed
	) {
		void runWinProbability();
	}
	/** True if the most recent background poll failed (the .catch path in
	 *  the live poll below). Surfaces as an amber dot on the freshness
	 *  strip — silent failures used to be invisible. Resets on success. */
	let pollFailed = false;

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
				// Rank, not total_points — points only ever go up, so a
				// points-trajectory sparkline trended upward for every
				// entry regardless of how they were actually doing.
				trajectoriesByEntry = new Map(
					traj.entries.map((t) => [t.entry_id, t.points.map((p) => p.position)])
				);
			})
			.catch(() => undefined);
	}

	onMount(() => pageTitle.set('Standings'));

	onMount(async () => {
		try {
			const data = await getMatchMarkers();
			matchMarkers = data.markers;
		} catch {
			matchMarkers = [];
		}
	});

	// Load reactively, not in onMount — $phase1Deadline hydrates after this
	// page mounts (same race the results page hit), so a one-shot mount
	// check would skip the fetch and strand the page at "0 entries".
	let loadRequested = false;
	$: if ($isAuthenticated && lbOpen && !loadRequested) {
		loadRequested = true;
		void load();
		// Refresh standings every 60s while the page is open and visible
		// (backend cache TTL is 30s, so this stays cheap; the poll pauses
		// while the tab is hidden and catches up on return). Once the
		// tournament has concluded the board is a frozen final result —
		// no live re-scoring is happening, so skip the poll entirely.
		// (Reactive `$: if (...) {...}` blocks compile as top-level module
		// code, not inside a function — an early `return` here is a
		// SyntaxError, hence the nested `if` instead.)
		if (!$tournamentConcluded) {
			stopPoll = startLivePoll(() => {
				getLeaderboardV4()
					.then((b) => {
						board = b;
						pollFailed = false;
					})
					.catch(() => {
						pollFailed = true;
					});
			});
		}
	}
	onDestroy(() => stopPoll?.());

	let search = '';
	$: liveActive = board?.live_projection_active === true;
	$: rows = liveActive
		? [...(board?.entries ?? [])].sort(
				(a, b) => (a.projected_position ?? a.position) - (b.projected_position ?? b.position)
			)
		: (board?.entries ?? []);
	$: stage = deriveStage($fixtures);
	$: filteredRows = searchRows(filterByPool(rows, pool), search);
	$: multiOwners = multiEntryUserIds(rows);

	// ── Race-tab redesign state (2026-06-22) ──
	let raceMode: RaceViewMode = 'around_me';
	let matchMarkers: MatchMarker[] = [];

	$: hasUserEntries = !!$user && rows.some((r) => r.user_id === $user!.id);

	// If signed-in user has no entries, fall back from around_me to top15
	$: if (!hasUserEntries && raceMode === 'around_me') raceMode = 'top15';

	// Synthesize a thin EntryTrajectory[] for slice computation. RaceChart
	// still owns the full trajectories; this is just the slice's entry-id
	// whitelist input.
	$: synthTrajectories = rows.map<EntryTrajectory>((r) => ({
		entry_id: r.entry_id,
		entry_name: r.entry_name ?? '',
		user_id: r.user_id,
		user_name: r.user_name ?? '',
		points: [{ position: r.position, total_points: r.total_points, captured_date: '' }]
	}));

	$: raceSlice =
		synthTrajectories.length > 0
			? selectRaceSlice(synthTrajectories, raceMode, $user?.id ?? null)
			: null;

	function openCompare(subjectId: string, compareId: string | null) {
		const subject = rows.find((r) => r.entry_id === subjectId);
		if (!subject) return;
		selected = subject;
		if (compareId) {
			compareSelected = rows.find((r) => r.entry_id === compareId) ?? null;
		} else {
			compareSelected = null;
		}
		cohortSelected = null;
	}

	function openCohortDrawer(teamCode: string) {
		// v1: cohort entry-list is a follow-up endpoint; for now we render the
		// drawer with an empty list and a "coming soon" placeholder.
		cohortSelected = { team_code: teamCode, team_name: teamCode, entry_ids: [] };
		// Drawer needs a `row` even in cohort mode; pass the first row as a no-op.
		if (rows.length > 0) selected = rows[0];
		compareSelected = null;
	}

	function closeDrawer() {
		selected = null;
		compareSelected = null;
		cohortSelected = null;
	}

	// Deep-link: when the URL carries ?entry=<id> (e.g. arriving from a
	// dashboard Daily MVP / Personal Trail click — see DashboardV4's
	// openLeaderboardEntry), open the drawer for that entry as soon as
	// `rows` has hydrated. Single-shot: `deepLinkConsumed` flips after
	// the open so the reactive block doesn't refire when `rows` updates
	// during the 60s live-poll. Also strips ?entry= from the URL so a
	// refresh doesn't re-trigger.
	let deepLinkConsumed = false;
	$: if (browser && !deepLinkConsumed && rows.length > 0 && !selected) {
		const targetId = $page.url.searchParams.get('entry');
		if (targetId && rows.find((r) => r.entry_id === targetId)) {
			openCompare(targetId, null);
			deepLinkConsumed = true;
			const cleanUrl = new URL($page.url);
			cleanUrl.searchParams.delete('entry');
			history.replaceState({}, '', cleanUrl);
		}
	}

	// ── Freshness cue ──
	// "Updated Ns ago" ticks via the shared $currentTime store (already
	// driving the navbar countdown — no extra interval). The "includes
	// last result" line uses the most-recently-FINISHED fixture as a
	// proxy for "what just changed": score-sync only expires the cache
	// on FINISHED transitions (v2.173.0), so the latest FT is the
	// meaningful trigger.
	$: updatedAgo = board?.last_calculated
		? relativeAgo(board.last_calculated, $currentTime.getTime())
		: '';
	$: lastFinished = (() => {
		const finished = $fixtures.filter(
			(f) => f.status === 'finished' && f.score && f.kickoff
		);
		if (finished.length === 0) return null;
		// Sort by kickoff desc — final-whistle time isn't stored explicitly;
		// kickoff order matches "most recently played" closely enough.
		finished.sort(
			(a, b) => new Date(b.kickoff).getTime() - new Date(a.kickoff).getTime()
		);
		const f = finished[0];
		return f.score
			? `${teamCode(f.home_team)} ${f.score.home_score}–${f.score.away_score} ${teamCode(f.away_team)}`
			: null;
	})();

	$: liveMatchCue = (() => {
		const live = $fixtures.filter(
			(f) =>
				(f.status === 'live' || f.status === 'halftime') &&
				KO_STAGES.includes(f.stage) &&
				f.score
		);
		if (live.length === 0) return null;
		if (live.length > 1) return `${live.length} matches`;
		const f = live[0];
		const score = f.score;
		if (!score) return null;
		const min = f.minute != null ? ` · ${f.minute}′` : '';
		return `${teamCode(f.home_team)} ${score.home_score}–${score.away_score} ${teamCode(f.away_team)}${min}`;
	})();

	// ── published Google Sheet URL (v2.177.x) ──
	// Backend sets this on the leaderboard response when sheets_sync is
	// configured. The button below renders only when it's present.
	$: publishedSheetUrl = board?.published_sheet_url ?? null;

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
		<!-- ── slim header: view pills only (the navbar already titles the
		     page — no big heading). The freshness/status line used to live
		     here but now renders below the search/filter strip, on every
		     tab instead of just Standings. ── -->
		<div class="mb-3 flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
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
				{#if publishedSheetUrl}
					<a
						class="inline-flex items-center gap-1.5 rounded-btn border-[1.5px] border-transparent bg-base-200 px-2.5 py-1 font-display text-[11px] font-bold tracking-[0.04em] text-base-content/70 transition-all hover:text-base-content sm:gap-2 sm:px-4 sm:py-2 sm:text-xs"
						title="Open the shared Google Sheet of every entry's picks, points, and rank history in a new tab"
						href={publishedSheetUrl}
						target="_blank"
						rel="noopener noreferrer"
						on:click={() => track('view_all_entries_clicked')}
					>
						<svg
							class="h-3.5 w-3.5"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="2"
							stroke-linecap="round"
							stroke-linejoin="round"
							aria-hidden="true"
						>
							<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
							<polyline points="15 3 21 3 21 9" />
							<line x1="10" y1="14" x2="21" y2="3" />
						</svg>
						<span>View All Entries</span>
					</a>
				{/if}
			</div>
		</div>
		<YourEntriesStrip {rows} {pool} onPool={setPool} bind:search />

		<!-- ── freshness/status line — relocated here (was in the header
		     above the view pills) so it shows on every tab, not just
		     Standings. Same content, same reactives, new position. ── -->
		{#if board?.last_calculated}
			<p class="mb-3 mt-0.5 flex flex-wrap items-center justify-end gap-x-1.5 text-[11px] text-base-content/55">
				<span title={`Cache rebuilt ${board.last_calculated}`}>Updated {updatedAgo}</span>
				{#if lastFinished && !(liveActive && liveMatchCue)}
					<span class="text-base-content/40">·</span>
					<span>last result: <b class="text-base-content/70">{lastFinished}</b></span>
				{/if}
				{#if liveActive && liveMatchCue}
					<span class="text-base-content/40">·</span>
					<span class="rounded bg-success px-1.5 py-0.5 text-white"
						>based on live: <b>{liveMatchCue}</b></span
					>
					<span class="ml-1 relative"><LiveProjectionPill /></span>
				{/if}
				{#if pollFailed}
					<span
						class="ml-1 inline-flex items-center gap-1 text-warning-text"
						role="status"
						title="The most recent refresh failed — showing last known standings"
					>
						<span class="inline-block h-1.5 w-1.5 rounded-full bg-warning"></span>
						refresh failed
					</span>
				{/if}
				{#if $tournamentConcluded}
					<span
						class="ml-1 rounded-badge border border-primary/40 bg-primary/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-primary"
						>🏁 Final</span
					>
				{:else}
					<span class="ml-1"><ProvisionalPill /></span>
				{/if}
			</p>
		{/if}

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
				live={liveActive}
				{rules}
				onOpen={(row) => (selected = row)}
			/>
		{:else if view === 'race'}
			<RaceStoryGrid on:open={(e) => openCompare(e.detail.entry_id, e.detail.compare_id)} />

			<RaceViewPills bind:mode={raceMode} {hasUserEntries} />

			<RaceChart
				{rows}
				userId={$user?.id}
				fixtures={$fixtures}
				slice={raceSlice}
				{matchMarkers}
				showMinimap
			/>

			<div class="mt-3">
				<PoolDistribution />
			</div>
		{:else if view === 'insights'}
			<InsightsGrid
				{rows}
				{rules}
				{bonusMeta}
				userId={$user?.id}
				fixtures={$fixtures}
			/>
		{:else if view === 'win_probability'}
			<WinProbabilityView
				rows={filteredRows}
				{multiOwners}
				userId={$user?.id}
				data={winProbData}
				loading={winProbLoading}
				failed={winProbFailed}
				live={liveActive}
				onRun={runWinProbability}
				onOpen={(row) => (selected = row)}
			/>
		{/if}

		{#if selected}
			<EntryDrawer
				row={selected}
				isOwn={selected.user_id === $user?.id}
				{rules}
				{multiOwners}
				compareRow={compareSelected}
				cohort={cohortSelected}
				live={liveActive}
				onClose={closeDrawer}
			/>
		{/if}
	</div>
{/if}
