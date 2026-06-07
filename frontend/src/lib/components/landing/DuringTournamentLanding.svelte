<!--
  DuringTournamentLanding — mission-control dashboard. Mounted by the
  landing dispatcher when uxPhase === 'during_tournament' (phase 1
  locked, final not yet finished).

  Composition ported from upstream's DashGroupStage with single-phase
  simplifications:
    - Drops phase_2 fetches / branches
    - Drops Pn shell wrappers (our +layout.svelte owns chrome)
    - Wraps in active-entry context via missionDerived

  Data fetched on mount:
    - leaderboard (for KPI row, You-vs-Field, sibling-entry context)
    - fixtures (for points strip, match carousel)
    - active entry's predictions + agreements + rank trajectory
    - sibling entries' rank trajectories (for ghost sparklines)
    - per-fixture community predictions (for crowd histogram bars)
    - scoring config (for matchBreakdown computeBreakdown)
-->
<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { isAuthenticated, user } from '$stores/auth';
	import { loadEntries, entries, activeEntry, activeEntryId } from '$stores/entries';
	import { pageTitle } from '$stores/pageTitle';
	import { fetchLeaderboard, totalParticipants } from '$stores/leaderboard';
	import { fetchAllFixtures, fixtures, finishedFixtures } from '$stores/fixtures';
	import {
		getMatchPredictions,
		getAgreements,
		getCommunityPredictions,
		type FixtureAgreement
	} from '$api/predictions';
	import {
		getMyRankTrajectory,
		getEntryTrajectory,
		type RankTrajectoryResponse,
		type RankSnapshotPoint
	} from '$api/leaderboard';
	import { getScoringConfig, type ScoringConfig } from '$api/competition';
	import { siblingEntryIds, isOnlyEntry } from '$stores/missionDerived';
	import type { MatchPrediction, CommunityPredictionsResponse } from '$types';

	import MissionEntrySwitcher from './mc/MissionEntrySwitcher.svelte';
	import MissionHero from './mc/MissionHero.svelte';
	import MissionKpiRow from './mc/MissionKpiRow.svelte';
	import MissionPointsStrip from './mc/MissionPointsStrip.svelte';
	import MissionMatchCarousel from './mc/MissionMatchCarousel.svelte';
	import MissionResultsBreakdown from './mc/MissionResultsBreakdown.svelte';
	import MissionVsField from './mc/MissionVsField.svelte';

	let predictions: MatchPrediction[] = [];
	let agreements: FixtureAgreement[] = [];
	let community = new Map<string, CommunityPredictionsResponse>();
	let trajectoryData: RankTrajectoryResponse | null = null;
	let ghostSeries: { entry_id: string; points: RankSnapshotPoint[] }[] = [];
	let scoringConfig: ScoringConfig | null = null;
	let loaded = false;

	$: predictionByFixture = new Map(predictions.map((p) => [p.fixture_id, p]));
	$: agreementByFixture = new Map(agreements.map((a) => [a.fixture_id, a]));

	async function refreshActive() {
		if (!$activeEntryId) return;
		try {
			const [preds, agrees, traj] = await Promise.all([
				getMatchPredictions($activeEntryId),
				getAgreements($activeEntryId),
				getMyRankTrajectory(8, $activeEntryId)
			]);
			predictions = preds;
			agreements = agrees;
			trajectoryData = traj;
		} catch {
			// soft-fail — components handle missing data with fallback states
		}
	}

	async function refreshGhostSparks() {
		const siblings = $siblingEntryIds;
		if (siblings.length === 0) {
			ghostSeries = [];
			return;
		}
		try {
			const results = await Promise.all(
				siblings.map((id) =>
					getEntryTrajectory(id, 8)
						.then((t) => ({ entry_id: id, points: t.points }))
						.catch(() => null)
				)
			);
			ghostSeries = results.filter((r): r is { entry_id: string; points: RankSnapshotPoint[] } => r !== null);
		} catch {
			ghostSeries = [];
		}
	}

	async function refreshCommunity() {
		// Lazy-load community predictions only for live + upcoming fixtures
		// (finished cards use the rarity payoff line, not the histogram bar).
		// Cap to first 12 to avoid burning bandwidth on the full slate.
		const visible = $fixtures
			.filter((f) => f.status !== 'finished')
			.slice(0, 12);
		const next = new Map<string, CommunityPredictionsResponse>();
		await Promise.all(
			visible.map(async (f) => {
				try {
					next.set(f.id, await getCommunityPredictions(f.id));
				} catch {
					// silent per-fixture; the crowd bar hides itself when data missing
				}
			})
		);
		community = next;
	}

	let hasInitialized = false;

	onMount(() => {
		pageTitle.set('Mission Control');
	});

	// Reactive boot — waits for the auth store to hydrate before kicking
	// off the loads. onMount fires once at mount time and would race auth
	// (running before $user.id is populated); a reactive declaration
	// re-evaluates when the auth store ticks and fires exactly once.
	// Unauthenticated visitors land on the empty-state card (no goto —
	// avoids the dev pill's ?uxPhase override causing a redirect loop
	// against the auth-store hydration tick).
	$: if ($isAuthenticated && $user?.id && !hasInitialized) {
		hasInitialized = true;
		void boot($user.id);
	}

	/**
	 * Load entries with one retry. The first call after fresh navigate can
	 * race the token subscription in $api/client — by the time api.get
	 * fires for /entries, token.subscribe(api.setToken) may not have run
	 * yet for the freshly-mounted module instance. A single retry after a
	 * microtask gives subscriptions time to settle.
	 */
	async function loadEntriesWithRetry(userId: string): Promise<void> {
		await loadEntries(userId);
		// If entries populated, we're done. Otherwise wait a tick + retry.
		const { get } = await import('svelte/store');
		if (get(entries).length === 0) {
			await tick();
			await new Promise((r) => setTimeout(r, 50));
			await loadEntries(userId);
		}
	}

	async function boot(userId: string) {
		// loadEntries failure (e.g. transient 401 while api.client.token
		// is being set in a separate microtask) shouldn't kill the rest
		// of the boot — the entries-store stays empty and the user lands
		// on the "No entry to show" fallback. The retry inside
		// loadEntriesWithRetry handles the auth-race in most cases.
		try {
			await loadEntriesWithRetry(userId);
		} catch {
			// soft-fail; UI degrades gracefully
		}
		await Promise.all([
			fetchAllFixtures(),
			fetchLeaderboard(),
			getScoringConfig()
				.then((c) => (scoringConfig = c))
				.catch(() => {})
		]);
		await refreshActive();
		await Promise.all([refreshGhostSparks(), refreshCommunity()]);
		loaded = true;
	}

	// Re-fetch entry-scoped data when the active entry changes (after mount)
	$: if (loaded && $activeEntryId) {
		void refreshActive();
		void refreshGhostSparks();
	}
</script>

<svelte:head>
	<title>Mission Control — Atlas World Cup 2026 Pools</title>
</svelte:head>

<section class="max-w-[1200px] mx-auto mobile-padding py-6 sm:py-8">
	{#if !loaded}
		<p class="text-base-content/55 py-12 text-center">Loading your dashboard…</p>
	{:else if !$activeEntry}
		<div class="stadium-card no-glow p-7 max-w-xl mx-auto">
			<p class="font-display font-semibold text-lg mb-2">No entry to show.</p>
			<p class="text-base-content/70 text-sm">
				Mission Control needs at least one submitted entry.
				<a class="text-primary underline" href="/entries">View your entries →</a>
			</p>
		</div>
	{:else}
		{#if !$isOnlyEntry}
			<MissionEntrySwitcher />
		{/if}

		<MissionHero />

		<MissionKpiRow trajectory={trajectoryData?.points ?? []} {ghostSeries} />

		<MissionPointsStrip {predictions} />

		{#if scoringConfig}
			<MissionMatchCarousel
				fixtures={$fixtures}
				{predictionByFixture}
				{agreementByFixture}
				communityByFixture={community}
				{scoringConfig}
			/>
		{/if}

		<div class="grid grid-cols-1 lg:grid-cols-[1.55fr_1fr] gap-6 mt-6 items-start">
			{#if scoringConfig}
				<MissionResultsBreakdown
					finishedFixtures={$finishedFixtures}
					{predictionByFixture}
					{agreementByFixture}
					{scoringConfig}
				/>
			{/if}
			<MissionVsField />
		</div>
	{/if}
</section>
