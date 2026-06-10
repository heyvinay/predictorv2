<script lang="ts">
	/** V4 Results page (v2.163.0) — round-tabbed scoreboard.
	 *
	 *  Gated by `phase1Deadline < now` (spec D.2): pre-deadline shows the
	 *  "Results open at kickoff" stub; post-deadline renders the V4 shell.
	 *  Entry selection rides the global activeEntryId store so it persists
	 *  to the Match Detail page. Round selection auto-picks the LIVE round
	 *  (spec D.1) and syncs to ?round= for refresh persistence.
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { isAuthenticated, user } from '$stores/auth';
	import { fetchAllFixtures, fixtureById, fixtures } from '$stores/fixtures';
	import {
		bracketPrediction,
		fetchBracketPredictions,
		fetchMatchPredictions,
		matchPredictions,
		resetPredictions
	} from '$stores/predictions';
	import { activeEntryId, entries, loadEntries, setActiveEntry } from '$stores/entries';
	import { phase1Deadline } from '$stores/phase';
	import { pageTitle } from '$stores/pageTitle';
	import { getLeaderboard, getScoringRules } from '$api/leaderboard';
	import type {
		EntryRankInfo,
		MatchPredictionWithPoints,
		RoundId,
		ScoringRules
	} from '$lib/types/results';
	import { buildRounds, NEXT_ROUND, ROUND_LABELS } from '$lib/utils/resultsRounds';
	import { defaultRound, roundsWithLive } from '$lib/utils/roundsLive';
	import {
		bracketPicksForRound,
		missedR32Picks,
		progressingSplit,
		stagePointsForRound
	} from '$lib/utils/koPoints';
	import EntryPillBar from '$lib/components/results/v4/EntryPillBar.svelte';
	import PointsSummary from '$lib/components/results/v4/PointsSummary.svelte';
	import RoundTabs from '$lib/components/results/v4/RoundTabs.svelte';
	import RoundExplainer from '$lib/components/results/v4/RoundExplainer.svelte';
	import GroupRoundTable from '$lib/components/results/v4/GroupRoundTable.svelte';
	import KnockoutRoundTable from '$lib/components/results/v4/KnockoutRoundTable.svelte';
	import MissedPicksCard from '$lib/components/results/v4/MissedPicksCard.svelte';
	import ProgressingCard from '$lib/components/results/v4/ProgressingCard.svelte';
	import SummaryView from '$lib/components/results/v4/SummaryView.svelte';
	import WinnerView from '$lib/components/results/v4/WinnerView.svelte';

	$: if (!$isAuthenticated) goto('/login');

	// ── Gate (spec D.2): deadline passed → V4; else pre-tournament stub ──
	$: resultsOpen = $phase1Deadline ? new Date($phase1Deadline).getTime() < Date.now() : false;

	let loading = true;
	let rules: ScoringRules | null = null;
	let rankByEntry = new Map<string, EntryRankInfo>();

	const VALID_ROUNDS: RoundId[] = [
		'summary',
		'r1',
		'r2',
		'r3',
		'r32',
		'r16',
		'qf',
		'sf',
		'f',
		'winner'
	];
	let selectedRound: RoundId = 'r1';
	let roundInitialised = false;

	onMount(() => pageTitle.set('Results'));

	onMount(async () => {
		if (!$isAuthenticated || !resultsOpen) {
			loading = false;
			return;
		}
		await Promise.all([
			fetchAllFixtures(),
			$user?.id ? loadEntries($user.id) : Promise.resolve()
		]);

		// Keep the store's selection if it belongs to this user; else first entry.
		if (!$activeEntryId || !$entries.some((e) => e.id === $activeEntryId)) {
			const candidate = $entries[0];
			if (candidate) setActiveEntry(candidate.id);
		}

		const [leaderboard, scoringRules] = await Promise.all([
			getLeaderboard().catch(() => null),
			getScoringRules()
		]);
		rules = scoringRules;
		if (leaderboard) {
			rankByEntry = new Map(
				leaderboard.entries.map((e) => [
					e.entry_id,
					{ position: e.position, total_points: e.total_points }
				])
			);
		}

		await Promise.all([fetchMatchPredictions(), fetchBracketPredictions()]);
		loading = false;
	});

	// ── Round selection: URL param → default logic (D.1) ──
	$: rounds = buildRounds($fixtures);
	$: liveRounds = roundsWithLive(rounds, $fixtureById);
	$: if (!roundInitialised && !loading && $fixtures.length > 0) {
		const fromUrl = $page.url.searchParams.get('round') as RoundId | null;
		selectedRound =
			fromUrl && VALID_ROUNDS.includes(fromUrl)
				? fromUrl
				: defaultRound(rounds, $fixtureById, new Date());
		roundInitialised = true;
	}

	function selectRound(id: RoundId) {
		selectedRound = id;
		const url = new URL($page.url);
		url.searchParams.set('round', id);
		history.replaceState(history.state, '', url);
	}

	async function selectEntry(entryId: string) {
		if (entryId === $activeEntryId) return;
		setActiveEntry(entryId);
		resetPredictions();
		await Promise.all([fetchMatchPredictions(), fetchBracketPredictions()]);
	}

	// ── Derived view data ──
	$: typedPredictions = $matchPredictions as MatchPredictionWithPoints[];
	$: predictionsByFixture = new Map(typedPredictions.map((p) => [p.fixture_id, p]));
	$: activeRound = rounds.find((r) => r.id === selectedRound);
	$: roundFixtures = (activeRound?.fixtureIds ?? [])
		.map((fid) => $fixtureById.get(fid))
		.filter((f): f is NonNullable<typeof f> => !!f);
	$: roundPicks = bracketPicksForRound($bracketPrediction, selectedRound);
	$: stagePts = rules ? stagePointsForRound(rules.advancement, selectedRound) : 0;
	$: nextId = NEXT_ROUND[selectedRound] ?? null;
	$: nextStagePts = rules && nextId ? stagePointsForRound(rules.advancement, nextId) : 0;
	$: nextPicks = nextId ? bracketPicksForRound($bracketPrediction, nextId) : new Set<string>();
	$: progressing =
		activeRound?.isKnockout && nextId ? progressingSplit(roundFixtures, nextPicks) : null;
	$: missedTeams = selectedRound === 'r32' ? missedR32Picks(roundFixtures, roundPicks) : [];
	$: finalFixture =
		rounds
			.find((r) => r.id === 'f')
			?.fixtureIds.map((fid) => $fixtureById.get(fid))
			.find((f) => f?.stage === 'final') ?? null;
	$: finalDateLabel = finalFixture
		? new Date(finalFixture.kickoff).toLocaleDateString('en-GB', {
				day: 'numeric',
				month: 'short'
		  })
		: '';
	$: multiEntry = $entries.length > 1;
</script>

<svelte:head>
	<title>Results — Predictor v2</title>
</svelte:head>

{#if $isAuthenticated && !resultsOpen}
	<!-- Pre-deadline stub (carried over from the V3 page) -->
	<div class="hero min-h-[60vh]">
		<div class="hero-content text-center">
			<div class="max-w-md">
				<h2 class="font-display text-3xl tracking-wide">Results open at kickoff</h2>
				<p class="mt-3 text-base-content/60">
					You'll see your match results here as the tournament unfolds.
				</p>
				<a href="/entries" class="btn btn-primary btn-lg mt-6 shadow-glow-gold">
					Lock in your predictions
				</a>
			</div>
		</div>
	</div>
{:else if $isAuthenticated}
	<div class="container mx-auto mobile-padding max-w-[1180px] py-6">
		<h1 class="font-display text-3xl tracking-wide sm:text-4xl">Results</h1>

		{#if loading || !rules}
			<div class="flex justify-center py-16">
				<span class="loading loading-spinner loading-lg text-primary"></span>
			</div>
		{:else}
			<!-- Top strip: pills (multi-entry) + points summary -->
			<div class="mt-4 flex flex-col gap-3 lg:flex-row lg:items-stretch lg:justify-between">
				{#if multiEntry && $activeEntryId}
					<EntryPillBar
						entries={$entries}
						selectedId={$activeEntryId}
						{rankByEntry}
						onSelect={selectEntry}
					/>
				{/if}
				<PointsSummary predictions={typedPredictions} fullWidth={!multiEntry} />
			</div>

			<RoundTabs {rounds} selected={selectedRound} {liveRounds} onSelect={selectRound} />

			<RoundExplainer roundId={selectedRound} {rules} finalDate={finalDateLabel} />

			{#if selectedRound === 'summary'}
				<SummaryView
					{rounds}
					fixtureById={$fixtureById}
					{predictionsByFixture}
					bracket={$bracketPrediction}
					{rules}
					{liveRounds}
					onJump={selectRound}
				/>
			{:else if selectedRound === 'winner'}
				<WinnerView bracket={$bracketPrediction} {finalFixture} {rules} />
			{:else if activeRound?.isKnockout}
				{#if missedTeams.length > 0}
					<MissedPicksCard
						roundLabel={activeRound.label}
						teams={missedTeams}
						stagePoints={stagePts}
					/>
				{/if}
				<KnockoutRoundTable
					round={activeRound}
					fixtures={roundFixtures}
					{roundPicks}
					stagePoints={stagePts}
				/>
				{#if progressing && nextId && progressing.inNext.length + progressing.notInNext.length > 0}
					<ProgressingCard
						nextLabel={ROUND_LABELS[nextId]}
						inNext={progressing.inNext}
						notInNext={progressing.notInNext}
						nextStagePoints={nextStagePts}
					/>
				{/if}
			{:else if activeRound}
				<GroupRoundTable round={activeRound} fixtures={roundFixtures} {predictionsByFixture} />
			{/if}
		{/if}
	</div>
{/if}
