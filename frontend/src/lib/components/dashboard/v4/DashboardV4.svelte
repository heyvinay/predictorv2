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
	import { getGroupStagePodium, getLeaderboardV4, getScoringRules } from '$api/leaderboard';
	import { getAnnouncements } from '$api/announcements';
	import { track } from '$lib/analytics';
	import type { EntryRankInfo, MatchPredictionWithPoints, ScoringRules } from '$lib/types/results';
	import type { GroupStagePodium, LbEntryV4 } from '$lib/types/leaderboard';
	import type { Announcement } from '$lib/types/dashboard';
	import { deriveGroupMatchdays } from '$lib/utils/resultsRounds';
	import { teamCode } from '$lib/utils/teamCodes';
	import { startLivePoll } from '$lib/utils/livePoll';
	import {
		bucketDashboardFixtures,
		firstNameOf,
		greetingDate,
		groupTotalFromPredictions,
		koTotalFromFixtures
	} from '$lib/utils/dashboardV4';
	import { displayRank, displayTotal } from '$lib/utils/leaderboardV4';
	import EntrySummaryBar from '$lib/components/results/v4/EntrySummaryBar.svelte';
	import AnnouncementHero from './AnnouncementHero.svelte';
	import FixturesTable from './FixturesTable.svelte';
	import ResultsTable from './ResultsTable.svelte';
	import MiniLeaderboard from './MiniLeaderboard.svelte';
	import DailyMvpStrip from './DailyMvpStrip.svelte';
	import PersonalTrailStrip from './PersonalTrailStrip.svelte';
	import PoolDistribution from './PoolDistribution.svelte';
	import GroupStageWinnerCard from './GroupStageWinnerCard.svelte';
	import MatchdayStrip from './MatchdayStrip.svelte';

	let loading = true;
	let rules: ScoringRules | null = null;
	let lbRows: LbEntryV4[] = [];
	let liveProjectionActive = false;
	let totalEntries = 0;
	let announcements: Announcement[] = [];
	let announcementHeroEnabled = true;
	let now = new Date();
	// v2.181.0 — Group Stage Winner card (v2.183.x: upgraded to top-3
	// podium). Null until the admin flips the release flag on /admin;
	// backend gates the payload so the card stays hidden until release.
	// Refetched on the same 60s tick as the leaderboard so a mid-session
	// admin flip surfaces it within a minute.
	let groupStagePodium: GroupStagePodium | null = null;

	// ── Core data (fixtures, leaderboard, rules, announcements) ──
	let coreRequested = false;
	$: if ($user?.id && !coreRequested) {
		coreRequested = true;
		void loadCore();
	}

	async function loadCore() {
		const [, lb, scoringRules, announcementsData, gsw] = await Promise.all([
			fetchAllFixtures(),
			getLeaderboardV4().catch(() => null),
			getScoringRules(),
			getAnnouncements().catch(() => ({ hero_enabled: true, items: [] as Announcement[] })),
			getGroupStagePodium().catch(() => null)
		]);
		rules = scoringRules;
		announcements = announcementsData.items;
		announcementHeroEnabled = announcementsData.hero_enabled;
		if (lb) {
			liveProjectionActive = lb.live_projection_active === true;
			lbRows = liveProjectionActive
				? [...lb.entries].sort(
						(a, b) => (a.projected_position ?? a.position) - (b.projected_position ?? b.position)
					)
				: lb.entries;
			totalEntries = lb.entries.length;
		}
		groupStagePodium = gsw;
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
				liveProjectionActive = lb.live_projection_active === true;
				lbRows = liveProjectionActive
					? [...lb.entries].sort(
							(a, b) => (a.projected_position ?? a.position) - (b.projected_position ?? b.position)
						)
					: lb.entries;
				totalEntries = lb.entries.length;
			})
			.catch(() => undefined);
		// Re-poll the GSW endpoint so an admin's mid-session toggle
		// flip surfaces within ~60s (no hard refresh needed).
		void getGroupStagePodium()
			.then((gsp) => {
				groupStagePodium = gsp;
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
		lbRows.map((e) => [
			e.entry_id,
			{
				position: displayRank(e, liveProjectionActive),
				total_points: displayTotal(e, liveProjectionActive)
			}
		])
	);
	$: visibleEntries = $submittedEntries.length > 0 ? $submittedEntries : $entries;

	// ── "Last result" cue for the MiniLeaderboard footer ──
	// Most-recently-finished fixture, formatted as "BRA 5–0 UZB". Mirrors
	// the `lastFinished` derivation on /leaderboard so the dashboard
	// surfaces the same freshness signal.
	$: lastResult = (() => {
		const finished = $fixtures.filter((f) => f.status === 'finished' && f.score && f.kickoff);
		if (finished.length === 0) return null;
		finished.sort((a, b) => new Date(b.kickoff).getTime() - new Date(a.kickoff).getTime());
		const f = finished[0];
		if (!f.score) return null;
		return `${teamCode(f.home_team)} ${f.score.home_score}–${f.score.away_score} ${teamCode(f.away_team)}`;
	})();
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

		<!-- Matchday scoreboard (v2.181.0): ESPN-style pill row, full
		     container width. Promoted above the GSW card in v2.183.x —
		     during knockouts, today's fixtures are the most time-
		     sensitive content and should sit at the top of the page.
		     v2.191.4: flanked by the most recent finished game and
		     tomorrow's fixtures when there's room (buckets.strip).
		     Self-collapsing on empty days. -->
		{#if buckets.strip.length > 0}
			<div class="mb-5">
				<MatchdayStrip items={buckets.strip} />
			</div>
		{/if}

		<!-- Mobile-only: leaderboard right after the matchday score cards,
		     ahead of the tables/trail content below. Same component + props
		     as the side-column instance below — just a different position
		     at narrow widths, where the 2-col grid collapses to one column
		     and DOM order becomes visual order. Hidden at min-[920px] so
		     desktop keeps the side-column instance only (no duplicate). -->
		<div class="mb-5 block min-[920px]:hidden">
			<MiniLeaderboard
				rows={lbRows}
				live={liveProjectionActive}
				userId={$user?.id ?? null}
				activeEntryId={$activeEntryId}
				{totalEntries}
				{lastResult}
			/>
		</div>

		<!-- v2.181.0: DailyMvpStrip moved out of the top-of-page slot
		     and into the side column below (above MiniLeaderboard).
		     v2.184.x: GroupStageWinnerCard moved INTO the main column
		     (was full-width above the grid). At its old size the card
		     pushed the side widgets — DailyMVP, MiniLeaderboard — too
		     far down. Inside the main column it sits at top-left while
		     those widgets pull up to top-right. -->

		<div class="grid grid-cols-1 items-start gap-5 min-[920px]:grid-cols-[1.55fr_1fr]">
			<!-- Main column -->
			<div class="flex min-w-0 flex-col gap-5">
					{#if announcementHeroEnabled}
					<AnnouncementHero {announcements} />
				{/if}

				<!-- Matchday FixturesTable removed in v2.181.0 — replaced
				     by the full-width MatchdayStrip above the 2-col grid.
				     Upcoming and Recent stay tabular below. -->
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

				<!-- Fills the whitespace that opens up under Latest results
				     once the side column (MiniLeaderboard + PoolDistribution)
				     grows taller than the main column's tables. -->
				<PersonalTrailStrip />
			</div>

			<!-- Side column -->
			<div class="flex min-w-0 flex-col gap-5">
				<!-- v2.181.0: DailyMvpStrip lives here now, above the
				     leaderboard. 3 compact chips in a side-column-width
				     row (was 5 full-width chips at top-of-page in
				     v2.180.0). -->
				<DailyMvpStrip on:open={e => openLeaderboardEntry(e.detail.entry_id)} />
				<!-- Desktop-only: the mobile-width instance moved above,
				     right after the matchday strip (see comment there). -->
				<div class="hidden min-[920px]:block">
					<MiniLeaderboard
						rows={lbRows}
						live={liveProjectionActive}
						userId={$user?.id ?? null}
						activeEntryId={$activeEntryId}
						{totalEntries}
						{lastResult}
					/>
				</div>
				<PoolDistribution />
			</div>
		</div>

		<!-- PersonalTrailStrip moved into the main column (above, after
		     ResultsTable) so it fills the side column's overflow instead of
		     sitting in its own full-width row. This region now holds only
		     the Group Stage Winner card, once released. -->
		{#if groupStagePodium && groupStagePodium.entries.length > 0}
			<div class="my-5 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent opacity-60"></div>
			<GroupStageWinnerCard podium={groupStagePodium} />
		{/if}
	{/if}
</div>
