<script lang="ts">
	/** Knockout-fixture variant of Match Detail.
	 *
	 *  Renders the ko-detail bundle (pool split + bracket implications +
	 *  most-exposed entries + pool roll) plus the user's personal stake
	 *  card on top, replacing the scoreline-grid layout that fits group
	 *  fixtures. Hero + MatchNav still live in the parent route.
	 *
	 *  Layout: two-column on lg+ (primary stack on the left, sidebar on
	 *  the right). Collapses to a single stack on mobile.
	 */
	import { onMount, onDestroy } from 'svelte';
	import type { Fixture } from '$types';
	import type {
		BracketPrediction
	} from '$types';
	import type {
		KoMatchDetailResponse,
		ScoringRules
	} from '$lib/types/results';
	import { getKoMatchDetail, getBracketPredictions } from '$api/predictions';
	import { ApiResponseError } from '$api/client';
	import { activeEntryId, entries } from '$stores/entries';
	import MatchHero from './MatchHero.svelte';
	import YourStakeKo from './YourStakeKo.svelte';
	import PoolSplitKo from './PoolSplitKo.svelte';
	import BracketImplications from './BracketImplications.svelte';
	import MostExposedEntries from './MostExposedEntries.svelte';
	import PoolRollKo from './PoolRollKo.svelte';
	import FutureCone from './FutureCone.svelte';
	import BracketQuadrant from './BracketQuadrant.svelte';

	export let fixture: Fixture;
	export let mode: 'played' | 'upcoming';
	export let upset = false;
	export let scoringRules: ScoringRules | null = null;

	let bundle: KoMatchDetailResponse | null = null;
	let bracket: BracketPrediction | null = null;
	let bundleUnavailable = false;
	let bundleLoadedFor = '';
	let bracketLoadedFor = '';

	// Bundle fetch — refetches whenever fixture.id changes. 403 means the
	// blind-pool gate hasn't tripped yet (matches the /community pattern).
	$: if (fixture && fixture.id !== bundleLoadedFor) {
		bundleLoadedFor = fixture.id;
		bundle = null;
		bundleUnavailable = false;
		void getKoMatchDetail(fixture.id)
			.then((resp) => {
				if (bundleLoadedFor === fixture.id) bundle = resp;
			})
			.catch((e) => {
				if (bundleLoadedFor !== fixture.id) return;
				bundleUnavailable = true;
				if (!(e instanceof ApiResponseError && e.status === 403)) console.error(e);
			});
	}

	$: youReference = $entries.find((e) => e.id === $activeEntryId)?.reference ?? null;

	// User's own bracket — refetches whenever active entry changes.
	$: if ($activeEntryId && $activeEntryId !== bracketLoadedFor) {
		bracketLoadedFor = $activeEntryId;
		bracket = null;
		void getBracketPredictions($activeEntryId)
			.then((b) => {
				if (bracketLoadedFor === $activeEntryId) bracket = b;
			})
			.catch(() => undefined);
	}
</script>

<div class="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_360px]">
	<!-- LEFT column: primary content stack -->
	<div class="flex flex-col gap-4">
		<MatchHero {fixture} {mode} {upset} />

		{#if bundle}
			<YourStakeKo {fixture} {bundle} {bracket} {scoringRules} {mode} />
			<PoolSplitKo {fixture} {bundle} />
			<BracketImplications {fixture} {bundle} {scoringRules} />
			<MostExposedEntries {fixture} {bundle} />
			<PoolRollKo {fixture} {bundle} {youReference} />
		{:else if bundleUnavailable}
			<div
				class="rounded-box border border-base-300/60 bg-base-200 px-6 py-5 text-center text-[12.5px] text-base-content/55"
			>
				The pool view for this match unlocks once the global deadline passes.
			</div>
		{:else}
			<div class="flex h-32 items-center justify-center">
				<span class="loading loading-spinner loading-md text-primary"></span>
			</div>
		{/if}
	</div>

	<!-- RIGHT column: contextual sidebar -->
	<div class="flex flex-col gap-4">
		<BracketQuadrant {fixture} />
		<FutureCone {fixture} />
	</div>
</div>
