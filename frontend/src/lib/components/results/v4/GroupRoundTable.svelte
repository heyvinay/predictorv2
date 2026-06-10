<script lang="ts">
	/** Fixtures card for R1/R2/R3 — header, rows, gold round-subtotal footer. */
	import type { Fixture } from '$types';
	import type { MatchPredictionWithPoints, RoundDef } from '$lib/types/results';
	import FixtureRowGroup from './FixtureRowGroup.svelte';

	export let round: RoundDef;
	export let fixtures: Fixture[];
	export let predictionsByFixture: Map<string, MatchPredictionWithPoints>;

	$: subtotal = fixtures.reduce(
		(s, f) => s + (predictionsByFixture.get(f.id)?.points?.total ?? 0),
		0
	);
</script>

<div class="mt-4 overflow-hidden rounded-box border border-base-300/60 bg-base-200">
	<div
		class="hidden items-center gap-2 border-b border-base-300/50 bg-base-300/20 px-3 py-1.5 sm:grid sm:grid-cols-[minmax(130px,1fr)_86px_minmax(130px,1fr)_64px_118px]"
	>
		<div class="text-[11px] font-extrabold uppercase tracking-[0.1em] text-base-content/70">
			{round.label}
		</div>
		<div></div>
		<div></div>
		<div class="text-center text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">
			Pick
		</div>
		<div class="text-right text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">
			Points
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
		{#each fixtures as f, i (f.id)}
			<FixtureRowGroup
				fixture={f}
				prediction={predictionsByFixture.get(f.id)}
				striped={i % 2 === 1}
			/>
		{/each}
	{/if}

	<div class="flex items-center justify-end gap-2 border-t border-base-300/50 px-3 py-1.5">
		<span class="text-[11.5px] font-bold tracking-[0.06em] text-primary">Round Total</span>
		<span class="font-display text-[16px] {subtotal > 0 ? 'text-primary' : 'text-base-content/70'}"
			>{subtotal}</span
		>
	</div>
</div>
