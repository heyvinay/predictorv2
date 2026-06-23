<script lang="ts">
	/** V4 Dashboard (v2.165.0) — the signed-in landing page.
	 *
	 *  Layout (design handoff mockups/DashboardResdesign):
	 *    greeting line ······························· entry bar + switch
	 *    HERO announcements (rotating) ┃ LEADERBOARD (yours + top 10)
	 *    MATCHDAY table                ┃
	 *    UPCOMING MATCHES table        ┃ MOVERS (climb/slide)
	 *    LATEST RESULTS table          ┃
	 *
	 *  One selected entry (the global activeEntryId store — shared with
	 *  the Results page so switching here switches there) drives the
	 *  entry-bar stats, every pick/call chip and the leaderboard
	 *  highlight. Fixtures + leaderboard re-poll every 60s for live
	 *  scores and movement.
	 *
	 *  Data loads are reactive, never onMount — $user and $phase1Deadline
	 *  hydrate after mount (same race as the V4 Results page). */
	import { onDestroy, onMount } from 'svelte';
	import { user } from '$stores/auth';
	import { fetchAllFixtures, fixtures } from '$stores/fixtures';
	import {
		bracketPrediction,
		fetchBracketPredictions,
		fetchMatchPredictions,
		matchPredictions,
		resetPredictions
	} from '$stores/predictions';
	import {
		activeEntryId,
		entries,
		loadEntries,
		setActiveEntry,
		submittedEntries
	} from '$stores/entries';
	import { getLeaderboardV4, getScoringRules } from '$api/leaderboard';
	import { getAnnouncements } from '$api/announcements';
	import { track } from '$lib/analytics';
	import type { EntryRankInfo, MatchPredictionWithPoints, ScoringRules } from '$lib/types/results';
	import type { LbEntryV4 } from '$lib/types/leaderboard';
	import type { Announcement } from '$lib/types/dashboard';
	import { deriveGroupMatchdays } from '$lib/utils/resultsRounds';
	import { startLivePoll } from '$lib/utils/livePoll';
	import {
		bucketDashboardFixtures,
		firstNameOf,
		greetingDate,
		groupTotalFromPredictions,
		koTotalFromFixtures
	} from '$lib/utils/dashboardV4';
	import EntrySummaryBar from '$lib/components/results/v4/EntrySummaryBar.svelte';
	import AnnouncementHero from './AnnouncementHero.svelte';
	import FixturesTable from './FixturesTable.svelte';
	import ResultsTable from './ResultsTable.svelte';
	import MiniLeaderboard from './MiniLeaderboard.svelte';
	import DailyMvpStrip from './DailyMvpStrip.svelte';
	import PersonalTrailStrip from './PersonalTrailStrip.svelte';
	import PoolDistribution from './PoolDistribution.svelte';

	let loading = true;
	let rules: ScoringRules | null = null;
	let lbRows: LbEntryV4[] = [];
	let totalEntries = 0;
	let announcements: Announcement[] = [];
	let now = new Date();

	// ── Core data (fixtures, leaderboard, rules, announcements) ──
	let coreRequested = false;
	$: if ($user?.id && !coreRequested) {
		coreRequested = true;
		void loadCore();
	}

	async function loadCore() {
		const [, lb, scoringRules, news] = await Promise.all([
			fetchAllFixtures(),
			getLeaderboardV4().catch(() => null),
			getScoringRules(),
			getAnnouncements().catch(() => [] as Announcement[])
		]);
		rules = scoringRules;
		announcements = news;
		if (lb) {
			lbRows = lb.entries;
			totalEntries = lb.entries.length;
		}
		loading = false;
	}

	// ── Entries + the selected entry's predictions ──
	let entriesRequested = false;
	$: if ($user?.id && !entriesRequested) {
		entriesRequested = true;
		void loadEntriesAndPredictions($user.id);
	}

	async function loadEntriesAndPredictions(userId: string) {
		await loadEntries(userId);
		// Post-deadline only submitted entries play — keep the selection
		// on one of those (same rule as the V4 Results page).
		const visible = $submittedEntries.length > 0 ? $submittedEntries : $entries;
		if (!$activeEntryId || !visible.some((e) => e.id === $activeEntryId)) {
			const candidate = visible[0];
			if (candidate) setActiveEntry(candidate.id);
		}
		await Promise.all([fetchMatchPredictions(), fetchBracketPredictions()]);
	}

	async function selectEntry(entryId: string) {
		if (entryId === $activeEntryId) return;
		setActiveEntry(entryId);
		resetPredictions();
		await Promise.all([fetchMatchPredictions(), fetchBracketPredictions()]);
	}

	function openLeaderboardEntry(entryId: string) {
		// Dashboard widgets dispatch entry-clicks here; the leaderboard page
		// handles deep-linking via its own ?entry= param logic.
		location.href = `/leaderboard?entry=${entryId}`;
	}

	// ── 60s refresh: live scores + movement (visibility-aware — pauses
	// while the tab is hidden, catches up immediately on return) ──
	const stopPoll = startLivePoll(() => {
		now = new Date();
		void fetchAllFixtures();
		void getLeaderboardV4()
			.then((lb) => {
				lbRows = lb.entries;
				totalEntries = lb.entries.length;
			})
			.catch(() => undefined);
	});
	onDestroy(stopPoll);

	onMount(() => {
		track('dashboard_view', {});
	});

	// ── Derived view data ──
	$: buckets = bucketDashboardFixtures($fixtures, now);
	$: derivedMatchdays = deriveGroupMatchdays($fixtures);
	$: typedPredictions = $matchPredictions as MatchPredictionWithPoints[];
	$: predictionsByFixture = new Map(typedPredictions.map((p) => [p.fixture_id, p]));
	$: groupTotal = groupTotalFromPredictions(typedPredictions);
	$: knockoutTotal = rules ? koTotalFromFixtures($fixtures, $bracketPrediction, rules) : 0;
	$: rankByEntry = new Map<string, EntryRankInfo>(
		lbRows.map((e) => [e.entry_id, { position: e.position, total_points: e.total_points }])
	);
	$: visibleEntries = $submittedEntries.length > 0 ? $submittedEntries : $entries;
</script>

<!-- pb-10 (not the marketing pb-20): the Touchline news band renders
     directly below this container with its own border-t. -->
<div class="container mx-auto mobile-padding max-w-[1180px] py-3 pb-10">
	{#if loading || !rules}
		<div class="flex justify-center py-16">
			<span class="loading loading-spinner loading-lg text-primary"></span>
		</div>
	{:else}
		<!-- Header row: greeting left, entry bar right -->
		<div class="mb-4 flex flex-col gap-3 min-[700px]:flex-row min-[700px]:items-start min-[700px]:justify-between">
			<div class="flex flex-wrap items-baseline gap-2">
				<span class="text-[12px] font-extrabold uppercase tracking-[0.14em] text-primary"
					>World Cup 2026</span
				>
				<span class="text-[13px] text-base-content/30">·</span>
				<span class="text-[15px] font-bold text-base-content"
					>Welcome back, {firstNameOf($user?.name)}</span
				>
				<span class="hidden text-[13px] text-base-content/30 sm:inline">·</span>
				<span class="hidden text-[13px] font-semibold text-base-content/55 sm:inline"
					>{greetingDate(now)}</span
				>
			</div>
			{#if $activeEntryId && visibleEntries.length > 0}
				<div class="flex min-[700px]:justify-end">
					<EntrySummaryBar
						entries={visibleEntries}
						selectedId={$activeEntryId}
						{rankByEntry}
						onSelect={selectEntry}
						userName={$user?.name ?? $user?.email?.split('@')[0] ?? ''}
						{groupTotal}
						{knockoutTotal}
					/>
				</div>
			{/if}
		</div>

		<div class="grid grid-cols-1 items-start gap-5 min-[920px]:grid-cols-[1.55fr_1fr]">
			<!-- Main column -->
			<div class="flex min-w-0 flex-col gap-5">
				<AnnouncementHero {announcements} />

				{#if buckets.matchday.length > 0}
					<FixturesTable
						title="Matchday"
						fixtures={buckets.matchday}
						{predictionsByFixture}
						bracket={$bracketPrediction}
						{derivedMatchdays}
						{now}
					/>
				{/if}

				<FixturesTable
					title="Upcoming matches"
					fixtures={buckets.upcoming}
					{predictionsByFixture}
					bracket={$bracketPrediction}
					{derivedMatchdays}
					{now}
					href="/results"
					linkLabel="All fixtures"
				/>

				<ResultsTable
					fixtures={buckets.recent}
					{predictionsByFixture}
					bracket={$bracketPrediction}
					{rules}
					{derivedMatchdays}
				/>
			</div>

			<!-- Side column -->
			<div class="flex min-w-0 flex-col gap-5">
				<MiniLeaderboard
					rows={lbRows}
					userId={$user?.id ?? null}
					activeEntryId={$activeEntryId}
					{totalEntries}
				/>
				<PoolDistribution />
			</div>
		</div>

		<!-- ============ Dashboard widgets region (2026-06-22) ============ -->
		<div class="my-5 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent opacity-60"></div>
		<div class="flex flex-col gap-4">
			<DailyMvpStrip on:open={e => openLeaderboardEntry(e.detail.entry_id)} />
			<PersonalTrailStrip />
		</div>
	{/if}
</div>
