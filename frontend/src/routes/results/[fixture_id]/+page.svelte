<script lang="ts">
	/** V4 Match Detail (v2.163.0) — /results/[fixture_id].
	 *
	 *  Played/live and upcoming/locked layouts share this shell. Pool data
	 *  comes from /community (403 pre-lock → placeholder card). Entry
	 *  selection persists from /results via the activeEntryId store. The
	 *  entry's own points come from the B.1 `points` field — never
	 *  recomputed locally. Prev/next: click, ←/→, horizontal swipe;
	 *  instant swap, no animation (spec §8.7).
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { isAuthenticated, user } from '$stores/auth';
	import { fetchAllFixtures, fixtureById, fixtures } from '$stores/fixtures';
	import { fetchMatchPredictions, matchPredictions } from '$stores/predictions';
	import { activeEntryId, entries, loadEntries, setActiveEntry } from '$stores/entries';
	import { pageTitle } from '$stores/pageTitle';
	import { getCommunityPredictions } from '$api/predictions';
	import { getScoringRules } from '$api/leaderboard';
	import { ApiResponseError } from '$api/client';
	import type {
		CommunityPredictionWithRank,
		MatchPredictionWithPoints,
		ScoringRules
	} from '$lib/types/results';
	import { buildRounds } from '$lib/utils/resultsRounds';
	import {
		isUpset,
		outcomeOf,
		outcomePayouts,
		poolRows,
		prevNextInRound,
		sideCallers,
		sideOf,
		spreadGrid
	} from '$lib/utils/matchDetailV4';
	import MatchNav from '$lib/components/results/v4-match/MatchNav.svelte';
	import MatchHero from '$lib/components/results/v4-match/MatchHero.svelte';
	import YourPickCard from '$lib/components/results/v4-match/YourPickCard.svelte';
	import PointsBreakdown from '$lib/components/results/v4-match/PointsBreakdown.svelte';
	import RarityExplainer from '$lib/components/results/v4-match/RarityExplainer.svelte';
	import ScorelineSpread from '$lib/components/results/v4-match/ScorelineSpread.svelte';
	import PoolList from '$lib/components/results/v4-match/PoolList.svelte';
	import PoolPickedWhat from '$lib/components/results/v4-match/PoolPickedWhat.svelte';
	import PoolSplit from '$lib/components/results/v4-match/PoolSplit.svelte';

	$: if (!$isAuthenticated) goto('/login');
	$: fixtureId = $page.params.fixture_id ?? '';

	let rules: ScoringRules | null = null;
	let loading = true;

	onMount(() => pageTitle.set('Match detail'));
	onMount(async () => {
		const [, scoringRules] = await Promise.all([fetchAllFixtures(), getScoringRules()]);
		rules = scoringRules;
		loading = false;
	});

	// Entries + own predictions — reactive on user hydration (same pattern
	// as the Results page; $user is null at onMount).
	let entriesRequested = false;
	$: if ($user?.id && !entriesRequested) {
		entriesRequested = true;
		void (async () => {
			await loadEntries($user.id);
			if (!$activeEntryId || !$entries.some((e) => e.id === $activeEntryId)) {
				const candidate = $entries[0];
				if (candidate) setActiveEntry(candidate.id);
			}
			await fetchMatchPredictions();
		})();
	}

	// Pool — refetched whenever the fixture id changes. 403 = blind pool
	// still closed for this fixture → placeholder.
	let pool: CommunityPredictionWithRank[] = [];
	let poolUnavailable = false;
	let poolLoadedFor = '';
	$: if (fixtureId && fixtureId !== poolLoadedFor) {
		poolLoadedFor = fixtureId;
		pool = [];
		poolUnavailable = false;
		void getCommunityPredictions(fixtureId)
			.then((resp) => {
				if (poolLoadedFor === fixtureId)
					pool = resp.predictions as CommunityPredictionWithRank[];
			})
			.catch((e) => {
				if (poolLoadedFor !== fixtureId) return;
				poolUnavailable = true;
				if (!(e instanceof ApiResponseError && e.status === 403)) console.error(e);
			});
	}

	// ── Derived view state ──
	$: fixture = $fixtureById.get(fixtureId) ?? null;
	$: mode =
		fixture &&
		(fixture.status === 'finished' || fixture.status === 'live' || fixture.status === 'halftime')
			? ('played' as const)
			: ('upcoming' as const);
	$: rounds = buildRounds($fixtures);
	$: pos = prevNextInRound(rounds, fixtureId);
	$: prevFixture = pos?.prevId ? $fixtureById.get(pos.prevId) ?? null : null;
	$: nextFixture = pos?.nextId ? $fixtureById.get(pos.nextId) ?? null : null;

	$: prediction = ($matchPredictions as MatchPredictionWithPoints[]).find(
		(p) => p.fixture_id === fixtureId
	);
	$: youReference = $entries.find((e) => e.id === $activeEntryId)?.reference ?? null;

	$: actual = fixture?.score
		? { home: fixture.score.home_score, away: fixture.score.away_score }
		: null;
	$: actualOutcome = actual ? outcomeOf(actual.home, actual.away) : null;
	$: poolReady = pool.length > 0 && !poolUnavailable;

	$: rows = poolReady && actual && rules ? poolRows(pool, actual, rules, youReference) : null;
	$: payouts = poolReady && rules ? outcomePayouts(pool, rules) : null;
	$: grid = poolReady ? spreadGrid(pool) : null;
	$: yourCell = prediction
		? ([Math.min(prediction.home_score, 3), Math.min(prediction.away_score, 3)] as [
				number,
				number
		  ])
		: null;
	$: actualCell = actual
		? ([Math.min(actual.home, 3), Math.min(actual.away, 3)] as [number, number])
		: null;
	$: upset =
		mode === 'played' && fixture?.status === 'finished' && poolReady && actualOutcome
			? isUpset(pool, actualOutcome)
			: false;
	$: yourSide = prediction ? sideOf(prediction.home_score, prediction.away_score) : null;
	$: yourPayout = yourSide && payouts ? payouts[yourSide] : null;
	$: rarityCallers =
		poolReady && prediction
			? sideCallers(pool, sideOf(prediction.home_score, prediction.away_score))
			: 0;

	// ── Prev/next navigation: click, keyboard, swipe ──
	function go(id: string | null) {
		if (id) void goto(`/results/${id}`);
	}
	function onKeydown(e: KeyboardEvent) {
		const tag = (e.target as HTMLElement | null)?.tagName;
		if (tag === 'INPUT' || tag === 'TEXTAREA') return;
		if (e.key === 'ArrowLeft') {
			e.preventDefault();
			go(pos?.prevId ?? null);
		} else if (e.key === 'ArrowRight') {
			e.preventDefault();
			go(pos?.nextId ?? null);
		}
	}
	let touch = { x: 0, y: 0, t: 0 };
	function onTouchStart(e: TouchEvent) {
		const t = e.touches[0];
		touch = { x: t.clientX, y: t.clientY, t: Date.now() };
	}
	function onTouchEnd(e: TouchEvent) {
		const t = e.changedTouches[0];
		const dx = t.clientX - touch.x;
		const dy = t.clientY - touch.y;
		const dt = Date.now() - touch.t;
		if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5 && dt < 600) {
			if (dx < 0) go(pos?.nextId ?? null);
			else go(pos?.prevId ?? null);
		}
	}
</script>

<svelte:head>
	<title>Match detail — Predictor v2</title>
</svelte:head>
<svelte:window on:keydown={onKeydown} />

{#if $isAuthenticated}
	<div
		class="container mx-auto mobile-padding max-w-[1180px] py-6"
		on:touchstart={onTouchStart}
		on:touchend={onTouchEnd}
	>
		{#if loading || !rules}
			<div class="flex justify-center py-16">
				<span class="loading loading-spinner loading-lg text-primary"></span>
			</div>
		{:else if !fixture || !pos}
			<div
				class="rounded-box border border-base-300/60 bg-base-200 px-8 py-12 text-center text-base-content/55"
			>
				Pick a fixture from the <a href="/results" class="link text-primary">Results page</a> to see
				its breakdown.
			</div>
		{:else}
			<MatchNav
				roundId={pos.roundId}
				roundLabel={pos.label}
				index={pos.index}
				count={pos.count}
				{prevFixture}
				{nextFixture}
				onPrev={() => go(pos?.prevId ?? null)}
				onNext={() => go(pos?.nextId ?? null)}
			/>

			<div class="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
				<!-- LEFT column -->
				<div class="flex flex-col gap-4">
					<MatchHero {fixture} {mode} {upset} />
					{#if mode === 'played' && rows}
						<PoolList banked={rows.banked} missed={rows.missed} totalPlayers={pool.length} />
					{:else if mode === 'upcoming' && poolReady && payouts}
						<PoolPickedWhat {fixture} preds={pool} {payouts} {youReference} />
					{/if}
				</div>

				<!-- RIGHT column -->
				<div class="flex flex-col gap-4">
					<YourPickCard {fixture} {mode} {prediction} payout={yourPayout} />
					{#if mode === 'played' && prediction?.points && prediction.points.total > 0}
						<PointsBreakdown points={prediction.points} />
					{/if}
					{#if mode === 'played' && prediction?.points && prediction.points.rarity > 0 && poolReady}
						<RarityExplainer
							n={rarityCallers}
							total={pool.length}
							pts={prediction.points.rarity}
							finished={fixture.status === 'finished'}
						/>
					{/if}
					{#if mode === 'upcoming' && poolReady && payouts}
						<PoolSplit {fixture} {payouts} {yourSide} />
					{/if}
					{#if grid}
						<ScorelineSpread
							{fixture}
							{mode}
							{grid}
							{yourCell}
							actualCell={mode === 'played' ? actualCell : null}
						/>
					{/if}
					{#if poolUnavailable}
						<div
							class="rounded-box border border-base-300/60 bg-base-200 px-6 py-5 text-center text-[12.5px] text-base-content/55"
						>
							Pool detail loads once the matchday window opens.
						</div>
					{/if}
				</div>
			</div>
		{/if}
	</div>
{/if}
