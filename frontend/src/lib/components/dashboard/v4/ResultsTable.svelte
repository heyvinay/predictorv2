<script lang="ts">
	/** Latest results table. Columns: Round | Match | Your call | Pts | ›
	 *  Group rows grade the score prediction; knockout rows grade the
	 *  bracket call (lineup-banked next-stage value on a win). */
	import type { BracketPrediction, Fixture } from '$types';
	import type { MatchPredictionWithPoints, ScoringRules } from '$lib/types/results';
	import { dashCallFor, roundChipForFixture } from '$lib/utils/dashboardV4';
	import RoundChip from './RoundChip.svelte';
	import MatchCell from './MatchCell.svelte';
	import CallChip from './CallChip.svelte';

	export let fixtures: Fixture[];
	export let predictionsByFixture: Map<string, MatchPredictionWithPoints>;
	export let bracket: BracketPrediction | null;
	export let rules: ScoringRules;
	export let derivedMatchdays: Map<string, 1 | 2 | 3>;

	const GRID =
		'grid grid-cols-[44px_minmax(0,1fr)_64px_36px_12px] items-center gap-2 px-3 py-2.5 sm:grid-cols-[84px_minmax(0,1fr)_96px_52px_14px] sm:gap-2.5 sm:px-3.5';
</script>

<section>
	<div class="mb-2 flex items-baseline justify-between gap-3">
		<h2 class="font-display text-lg font-bold tracking-wide text-base-content">Latest results</h2>
		<a
			href="/results"
			class="whitespace-nowrap font-display text-[12px] font-extrabold text-primary transition-opacity hover:opacity-75"
			>Full results →</a
		>
	</div>

	<div class="overflow-hidden rounded-box border border-base-300/70 bg-base-200">
		<div
			class="{GRID} !py-1.5 bg-base-300/20 text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55"
		>
			<span>Round</span>
			<span class="text-center">Match</span>
			<span class="text-center">Your call</span>
			<span class="text-right">Pts</span>
			<span></span>
		</div>

		{#each fixtures as f, i (f.id)}
			{@const call = dashCallFor(f, predictionsByFixture.get(f.id), bracket, rules)}
			<a
				href={`/results/${f.id}`}
				class="group {GRID} border-t border-base-300/40 transition-colors hover:bg-primary/5 {i % 2
					? 'bg-base-300/10'
					: ''}"
			>
				<RoundChip chip={roundChipForFixture(f, derivedMatchdays)} />
				<MatchCell fixture={f} />
				<span class="flex justify-center"><CallChip {call} /></span>
				<span
					class="text-right font-display text-[13px] font-extrabold tabular-nums {call.pts > 0
						? 'text-success'
						: 'text-base-content/30'}">{call.pts > 0 ? `+${call.pts}` : '0'}</span
				>
				<span
					class="text-[14px] text-base-content/30 transition-all group-hover:translate-x-0.5 group-hover:text-primary"
					aria-hidden="true">›</span
				>
			</a>
		{:else}
			<div class="border-t border-base-300/40 px-3.5 py-4 text-center text-[12px] text-base-content/45">
				No finished matches yet — results land here after the first final whistle.
			</div>
		{/each}
	</div>
</section>
