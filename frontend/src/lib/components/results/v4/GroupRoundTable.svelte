<script lang="ts">
	/** Fixtures card for R1/R2/R3 — header, rows, gold round-subtotal footer. */
	import type { Fixture } from '$types';
	import type { MatchPredictionWithPoints, RoundDef, ScoringRules } from '$lib/types/results';
	import FixtureRowGroup from './FixtureRowGroup.svelte';
	import PointsHelpButton from './PointsHelpButton.svelte';

	export let round: RoundDef;
	export let fixtures: Fixture[];
	export let predictionsByFixture: Map<string, MatchPredictionWithPoints>;
	export let rules: ScoringRules;

	$: subtotal = fixtures.reduce(
		(s, f) => s + (predictionsByFixture.get(f.id)?.points?.total ?? 0),
		0
	);
</script>

<div
	class="mt-4 overflow-hidden rounded-box border border-base-300/60 bg-base-200
	       lg:overflow-visible lg:rounded-none lg:border-0 lg:bg-transparent"
>
	<!-- lg+ section header: round label only, no container chrome.
	     The sm-to-lg-1 grid header below has lg:hidden because its column
	     labels won't align with the 2-col card layout at lg+. -->
	<div class="hidden items-center justify-between px-1 pb-2 lg:flex">
		<span class="text-[12px] font-extrabold uppercase tracking-[0.12em] text-base-content/70">
			{round.label}
		</span>
		<div class="flex items-center gap-1 text-[10px] font-bold uppercase tracking-[0.12em] text-base-content/55">
			<span>Points</span>
			<PointsHelpButton roundId={round.id} {rules} />
		</div>
	</div>

	<div
		class="hidden items-center gap-2 border-b border-base-300/50 bg-base-300/20 px-3 py-1.5 sm:grid lg:hidden sm:grid-cols-[minmax(90px,1fr)_70px_minmax(90px,1fr)_56px_92px]"
	>
		<div class="text-[11px] font-extrabold uppercase tracking-[0.1em] text-base-content/70">
			{round.label}
		</div>
		<div></div>
		<div></div>
		<div class="text-center text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">
			Pick
		</div>
		<div
			class="flex items-center justify-end gap-1 text-right text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55"
		>
			<span>Points</span>
			<PointsHelpButton roundId={round.id} {rules} />
		</div>
	</div>
	<div
		class="border-b border-base-300/50 bg-base-300/20 px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.1em] text-base-content/70 sm:hidden"
	>
		{round.label}
	</div>

	{#if fixtures.length === 0}
		<div class="px-8 py-8 text-center text-[13px] text-base-content/55">
			No fixtures for this round yet.
		</div>
	{:else}
		<!-- lg+ : each fixture becomes its own card in a 2-col grid.
		     Border + rounded corners + subtle background per card so adjacent
		     fixtures don't visually merge. Gap-2 + p-3 provide breathing room.
		     Particularly useful for R1/R2/R3 (24 fixtures per matchday). -->
		<div
			class="lg:grid lg:grid-cols-2 lg:gap-2 lg:p-0
			       lg:[&>a]:!border-t-0 lg:[&>a]:rounded-box lg:[&>a]:border lg:[&>a]:border-base-300/60 lg:[&>a]:bg-base-200 lg:[&>a]:shadow-sm"
		>
			{#each fixtures as f, i (f.id)}
				<FixtureRowGroup
					fixture={f}
					prediction={predictionsByFixture.get(f.id)}
					striped={i % 2 === 1}
				/>
			{/each}
		</div>
	{/if}

	<div
		class="flex items-center justify-end gap-2 border-t border-base-300/50 px-3 py-1.5
		       lg:mt-3 lg:border-0 lg:px-1 lg:py-0"
	>
		<span class="text-[11.5px] font-bold tracking-[0.06em] text-primary">Round Total</span>
		<span class="font-display text-[16px] {subtotal > 0 ? 'text-primary' : 'text-base-content/70'}"
			>{subtotal}</span
		>
	</div>
</div>
