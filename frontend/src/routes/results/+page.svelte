<script lang="ts">
	/** V4 Results page (v2.163.0) — round-tabbed scoreboard.
	 *
	 *  Gated by the admin go-live switch (v2.166.0): pre-release shows the
	 *  "Results open at kickoff" stub; post-deadline renders the V4 shell.
	 *  Entry selection rides the global activeEntryId store so it persists
	 *  to the Match Detail page. Round selection auto-picks the LIVE round
	 *  (spec D.1) and syncs to ?round= for refresh persistence.
	 */
	import { onDestroy, onMount } from 'svelte';
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
	import {
		activeEntryId,
		entries,
		loadEntries,
		setActiveEntry,
		submittedEntries
	} from '$stores/entries';
	import { postDeadlineLive, knockoutScoringEnabled } from '$stores/phase';
	import { pageTitle } from '$stores/pageTitle';
	import { getLeaderboard, getScoringRules } from '$api/leaderboard';
	import { getActualStandings } from '$api/fixtures';
	import type { ActualStandingsResponse } from '$types';
	import type {
		EntryRankInfo,
		MatchPredictionWithPoints,
		RoundId,
		ScoringRules
	} from '$lib/types/results';
	import { buildRounds, NEXT_ROUND, ROUND_LABELS } from '$lib/utils/resultsRounds';
	import { startLivePoll } from '$lib/utils/livePoll';
	import { defaultRound, roundsWithLive } from '$lib/utils/roundsLive';
	import {
		bracketPicksForRound,
		isRoundLineupSeeded,
		missedPicksForRound,
		progressingSplit,
		stagePointsForRound
	} from '$lib/utils/koPoints';
	import EntrySummaryBar from '$lib/components/results/v4/EntrySummaryBar.svelte';
	import RoundTabs from '$lib/components/results/v4/RoundTabs.svelte';
	import RoundExplainer from '$lib/components/results/v4/RoundExplainer.svelte';
	import GroupRoundTable from '$lib/components/results/v4/GroupRoundTable.svelte';
	import KnockoutRoundTable from '$lib/components/results/v4/KnockoutRoundTable.svelte';
	import RoundPicksCard from '$lib/components/results/v4/RoundPicksCard.svelte';
	import ProgressingCard from '$lib/components/results/v4/ProgressingCard.svelte';
	import SummaryView from '$lib/components/results/v4/SummaryView.svelte';
	import WinnerView from '$lib/components/results/v4/WinnerView.svelte';
	import GroupStandingsView from '$lib/components/results/v4/GroupStandingsView.svelte';
	import ResultsBracket from '$lib/components/results/v4/ResultsBracket.svelte';

	$: if (!$isAuthenticated) goto('/login');

	// ── Gate: admin-released → V4; else pre-tournament stub ──
	//
	// v2.166.0: the deadline passing no longer auto-opens the page —
	// release is the admin's manual "Go live" switch on /admin
	// (competitions.post_deadline_live, read via phase-status). Admins
	// always see V4 so they can verify before flipping it.
	const V4_RESULTS_ENABLED = true;
	$: resultsOpen = V4_RESULTS_ENABLED && ($user?.is_admin === true || $postDeadlineLive);

	let loading = true;
	let rules: ScoringRules | null = null;
	let rankByEntry = new Map<string, EntryRankInfo>();

	const VALID_ROUNDS: RoundId[] = [
		'summary',
		'r1',
		'r2',
		'r3',
		'bracket',
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

	// Core data loads reactively, not in onMount — the admin-only gate
	// makes resultsOpen depend on $user, which hydrates after this page
	// mounts (same race as the entries load below).
	let coreRequested = false;
	$: if (resultsOpen && !coreRequested) {
		coreRequested = true;
		void loadCore();
	}

	async function loadCore() {
		const [, leaderboard, scoringRules] = await Promise.all([
			fetchAllFixtures(),
			getLeaderboard().catch(() => null),
			getScoringRules()
		]);
		rules = scoringRules;
		applyLeaderboard(leaderboard);
		loading = false;
		// 60s live refresh (visibility-aware — pauses while the tab is
		// hidden, catches up on return): scores via fetchAllFixtures, the
		// entry's per-fixture points via fetchMatchPredictions, ranks for
		// the summary bar via the leaderboard.
		stopPoll ??= startLivePoll(() => {
			void fetchAllFixtures();
			void fetchMatchPredictions().catch(() => undefined);
			void getLeaderboard()
				.then(applyLeaderboard)
				.catch(() => undefined);
			// Refresh standings only when its tab is selected — avoids
			// burning the request on every tick when the user is on /r3.
			if (selectedRound === 'groups' && standingsRequested) {
				void loadStandings();
			}
		});
	}

	type LeaderboardPayload = Awaited<ReturnType<typeof getLeaderboard>> | null;
	function applyLeaderboard(leaderboard: LeaderboardPayload) {
		if (!leaderboard) return;
		rankByEntry = new Map(
			leaderboard.entries.map((e) => [
				e.entry_id,
				{ position: e.position, total_points: e.total_points }
			])
		);
	}

	let stopPoll: (() => void) | null = null;
	onDestroy(() => stopPoll?.());

	// Group Standings tab data (v2.181.2). Lazy: only loads the first time
	// the user selects the 'groups' tab; refreshes via the same livePoll
	// cycle as the rest of the page.
	let standingsPayload: ActualStandingsResponse | null = null;
	let standingsLoading = false;
	let standingsError: string | null = null;
	let standingsLastUpdated: Date | null = null;
	let standingsRequested = false;

	async function loadStandings() {
		standingsLoading = true;
		try {
			standingsPayload = await getActualStandings();
			standingsLastUpdated = new Date();
			standingsError = null;
		} catch (e) {
			standingsError = e instanceof Error ? e.message : 'Failed to load standings';
		} finally {
			standingsLoading = false;
		}
	}

	$: if (selectedRound === 'groups' && !standingsRequested && resultsOpen) {
		standingsRequested = true;
		void loadStandings();
	}

	// Entries + predictions load reactively once the user store hydrates —
	// at onMount time $user is usually still null (auth/me resolves in the
	// layout after this page mounts), so a one-shot read silently skips
	// loadEntries and the page renders without pills or picks.
	let entriesRequested = false;
	$: if (resultsOpen && $user?.id && !entriesRequested) {
		entriesRequested = true;
		void loadEntriesAndPredictions($user.id);
	}

	async function loadEntriesAndPredictions(userId: string) {
		await loadEntries(userId);
		// Post-deadline the page only shows submitted entries — make sure
		// the active selection is one of those. If a draft was active in
		// the store, fall through to the first submitted entry.
		const visible = $submittedEntries.length > 0 ? $submittedEntries : $entries;
		if (!$activeEntryId || !visible.some((e) => e.id === $activeEntryId)) {
			const candidate = visible[0];
			if (candidate) setActiveEntry(candidate.id);
		}
		await Promise.all([fetchMatchPredictions(), fetchBracketPredictions()]);
	}

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
	// v2.184.x: generalised from R32-only to every KO round so the
	// RoundPicksCard can show ✗ pills on R16/QF/SF/F once the round's
	// lineup is fully seeded. `missedPicksForRound` returns [] when the
	// lineup still has slot:* placeholders — see isRoundLineupSeeded
	// below for the gate.
	$: missedTeams = activeRound?.isKnockout
		? missedPicksForRound(roundFixtures, roundPicks)
		: [];
	$: roundLineupSeeded = activeRound?.isKnockout
		? isRoundLineupSeeded(roundFixtures)
		: true;
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
	$: visibleEntries = $submittedEntries.length > 0 ? $submittedEntries : $entries;
	$: multiEntry = visibleEntries.length > 1;

	// Top-card totals: group = sum of match-points across R1/R2/R3;
	// knockout = sum of bracket hits × stage points across r32..final + winner.
	// Bonus question split (group / knockout) needs a backend addition —
	// today bonus_question_points is a single aggregate, so the sub-line
	// stays at 0. Plumbed as optional props so the cell appears the moment
	// the split lands.
	$: groupTotalPts = typedPredictions.reduce((s, p) => s + (p.points?.total ?? 0), 0);
	// Knockout totals are zeroed in the UI while the admin gate is OFF —
	// matches the backend's `Competition.knockout_scoring_enabled` gate
	// (v2.183.3), so the round-table subtotals, the summary pill's
	// Knockout column, and the grand total all agree with the deferred
	// "pending release" message shown above the round content.
	$: knockoutTotalPts = $knockoutScoringEnabled
		? computeKoTotal(rules, rounds, $fixtureById, $bracketPrediction, winnerHit)
		: 0;

	function computeKoTotal(
		rulesRef: ScoringRules | null,
		roundList: typeof rounds,
		fxById: typeof $fixtureById,
		bracket: typeof $bracketPrediction,
		winnerCorrect: boolean
	): number {
		if (!rulesRef) return 0;
		const advancement = rulesRef.advancement;
		let total = 0;
		for (const r of roundList) {
			if (!r.isKnockout) continue;
			const picks = bracketPicksForRound(bracket, r.id);
			const stagePts = stagePointsForRound(advancement, r.id);
			let hits = 0;
			for (const fid of r.fixtureIds) {
				const f = fxById.get(fid);
				if (!f) continue;
				if (f.stage === 'third_place') continue;
				// Per-side seeded — partial-resolution R16+ rows must still
				// count hits on the resolved side (v2.184.x — same fix as
				// FixtureRowKo / fixtureKoHits). The prior binary check
				// hid the Summary total from users whose R16 winner had
				// landed but whose other-side R32 hadn't kicked off yet.
				const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:');
				const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:');
				if (homeSeeded && picks.has(f.home_team)) hits++;
				if (awaySeeded && picks.has(f.away_team)) hits++;
			}
			total += hits * stagePts;
		}
		if (winnerCorrect) total += advancement.winner;
		return total;
	}
	$: winnerHit = (() => {
		if (!finalFixture || finalFixture.status !== 'finished' || !finalFixture.score) return false;
		const champion =
			finalFixture.score.outcome === '1'
				? finalFixture.home_team
				: finalFixture.score.outcome === '2'
				? finalFixture.away_team
				: null;
		return !!champion && !!$bracketPrediction?.winner && champion === $bracketPrediction.winner;
	})();
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
	<div class="container mx-auto mobile-padding max-w-[1180px] py-2">
		{#if loading || !rules}
			<div class="flex justify-center py-16">
				<span class="loading loading-spinner loading-lg text-primary"></span>
			</div>
		{:else}
			<!-- Top strip: merged identity + points-summary pill, right-
			     aligned. Person-entry label sits in small muted text
			     above the pill; clicking the pill opens the switcher. -->
			{#if $activeEntryId}
				<div class="flex justify-end">
					<EntrySummaryBar
						entries={visibleEntries}
						selectedId={$activeEntryId}
						{rankByEntry}
						onSelect={selectEntry}
						userName={$user?.name ?? $user?.email?.split('@')[0] ?? ''}
						groupTotal={groupTotalPts}
						knockoutTotal={knockoutTotalPts}
					/>
				</div>
			{/if}

			<RoundTabs {rounds} selected={selectedRound} {liveRounds} onSelect={selectRound} />

			<!-- Group / KO round tables move the scoring explainer into a
			     ℹ popover next to the Points header. Summary + Winner
			     views still get the always-on banner here because they
			     don't have a per-round Points column to attach to. -->
			{#if selectedRound === 'summary' || selectedRound === 'winner'}
				<RoundExplainer roundId={selectedRound} {rules} finalDate={finalDateLabel} />
			{/if}

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
			{:else if selectedRound === 'groups'}
				<GroupStandingsView
					payload={standingsPayload}
					loading={standingsLoading}
					error={standingsError}
					lastUpdatedAt={standingsLastUpdated}
				/>
			{:else if selectedRound === 'bracket'}
				<ResultsBracket
					fixtures={$fixtures}
					bracketPrediction={$bracketPrediction}
					{rules}
					knockoutScoringEnabled={$knockoutScoringEnabled}
				/>
			{:else if activeRound?.isKnockout}
				{#if !$knockoutScoringEnabled}
					<!-- v2.183.1: knockout-scoring gate user-facing note.
					     Shown until the admin flips Competition.knockout_scoring_enabled
					     on /admin (typically after the group-stage winner is
					     verified and announced). -->
					<div
						class="mt-3 rounded-xl border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning-text"
						role="status"
					>
						<div class="font-bold uppercase tracking-wider text-[11px] mb-1">
							Knockout points pending release
						</div>
						<p class="text-base-content/80">
							Knockout scoring opens shortly. Until then your pool standings
							reflect group-stage points only.
						</p>
					</div>
				{/if}
				{#if roundPicks.size > 0}
					<RoundPicksCard
						roundLabel={activeRound.label}
						picks={[...roundPicks]}
						{missedTeams}
						stagePoints={stagePts}
						compactCodes={selectedRound === 'r32' || selectedRound === 'r16'}
						lineupSeeded={roundLineupSeeded}
					/>
				{/if}
				<KnockoutRoundTable
					round={activeRound}
					fixtures={roundFixtures}
					{roundPicks}
					stagePoints={stagePts}
					{rules}
					pointsVisible={$knockoutScoringEnabled}
				/>
				{#if progressing && nextId && progressing.inNext.length + progressing.notInNext.length > 0}
					<ProgressingCard
						nextLabel={ROUND_LABELS[nextId]}
						inNext={progressing.inNext}
						notInNext={progressing.notInNext}
						nextStagePoints={nextStagePts}
						compactCodes={selectedRound === 'r32' || selectedRound === 'r16'}
					/>
				{/if}
			{:else if activeRound}
				<GroupRoundTable
					round={activeRound}
					fixtures={roundFixtures}
					{predictionsByFixture}
					{rules}
				/>
			{/if}
		{/if}
	</div>
{/if}
