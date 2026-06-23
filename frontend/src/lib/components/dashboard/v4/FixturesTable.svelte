<script lang="ts">
	/** Shared fixtures table for the Matchday and Upcoming sections.
	 *  Columns: Round | Match | Your pick | When | ›
	 *  Every row links to the Match Detail page. Live rows carry the
	 *  pulsing red minute badge. */
	import type { BracketPrediction, Fixture } from '$types';
	import type { MatchPredictionWithPoints } from '$lib/types/results';
	import { dashPickFor, kickoffLabel, roundChipForFixture } from '$lib/utils/dashboardV4';
	import RoundChip from './RoundChip.svelte';
	import MatchCell from './MatchCell.svelte';
	import PickChip from './PickChip.svelte';

	export let title: string;
	export let fixtures: Fixture[];
	export let predictionsByFixture: Map<string, MatchPredictionWithPoints>;
	export let bracket: BracketPrediction | null;
	export let derivedMatchdays: Map<string, 1 | 2 | 3>;
	export let now: Date;
	export let href: string | null = null;
	export let linkLabel = '';

	const GRID =
		'grid grid-cols-[44px_minmax(0,1fr)_60px_72px_12px] items-center gap-2 px-3 py-2.5 sm:grid-cols-[84px_minmax(0,1fr)_96px_104px_14px] sm:gap-2.5 sm:px-3.5';

	function isLive(f: Fixture): boolean {
		return f.status === 'live' || f.status === 'halftime';
	}
</script>

<section>
	<slot name="head">
		<div class="mb-2 flex items-baseline justify-between gap-3">
			<h2 class="font-display text-lg font-bold tracking-wide text-base-content">{title}</h2>
			{#if href}
				<a
					{href}
					class="whitespace-nowrap font-display text-[12px] font-extrabold text-primary transition-opacity hover:opacity-75"
					>{linkLabel} →</a
				>
			{/if}
		</div>
	</slot>

	<div class="overflow-hidden rounded-box border border-base-300/70 bg-base-200">
		<div
			class="{GRID} !py-1.5 bg-base-300/20 text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55"
		>
			<span>Round</span>
			<span class="text-center">Match</span>
			<span class="text-center">Your pick</span>
			<span class="text-right">When</span>
			<span></span>
		</div>

		{#each fixtures as f, i (f.id)}
			<a
				href={`/results/${f.id}`}
				class="group {GRID} border-t border-base-300/40 transition-colors hover:bg-primary/5 {i % 2
					? 'bg-base-300/10'
					: ''} {isLive(f) ? 'border-l-4 border-l-success bg-success/5' : ''}"
			>
				<RoundChip chip={roundChipForFixture(f, derivedMatchdays)} />
				<MatchCell fixture={f} />
				<span class="flex justify-center">
					<PickChip pick={dashPickFor(f, predictionsByFixture.get(f.id), bracket)} />
				</span>
				<span class="text-right">
					{#if isLive(f)}
						<span
							class="inline-flex items-center gap-1 rounded-badge bg-success px-1.5 py-0.5 text-[10px] font-extrabold text-white"
						>
							<!-- Pulsing dot stays red (error) — it's the universal
							     "live action happening right now" visual signal even
							     when its surround is green. -->
							<span class="h-1.5 w-1.5 rounded-full bg-error animate-pulse"></span>
							{f.minute != null ? `${f.minute}'` : 'LIVE'}
						</span>
					{:else}
						<span class="text-[10.5px] font-bold text-base-content/55"
							>{kickoffLabel(f.kickoff, now)}</span
						>
					{/if}
				</span>
				<span
					class="text-[14px] text-base-content/30 transition-all group-hover:translate-x-0.5 group-hover:text-primary"
					aria-hidden="true">›</span
				>
			</a>
		{:else}
			<div class="border-t border-base-300/40 px-3.5 py-4 text-center text-[12px] text-base-content/45">
				No matches here yet.
			</div>
		{/each}
	</div>
</section>
