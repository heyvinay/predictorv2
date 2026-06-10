<script lang="ts">
	/** Fixtures card for KO rounds — bracket-call column + stage-specific
	 *  points. Subtotal counts each fixture's hits × stage points. */
	import type { Fixture } from '$types';
	import type { RoundDef } from '$lib/types/results';
	import FixtureRowKo from './FixtureRowKo.svelte';
	import { fixtureKoHits } from '$lib/utils/koPoints';

	export let round: RoundDef;
	export let fixtures: Fixture[];
	export let roundPicks: Set<string>;
	export let stagePoints: number;

	$: subtotal = fixtures.reduce(
		(s, f) => s + fixtureKoHits(f, roundPicks).hits * stagePoints,
		0
	);
</script>

<div class="mt-4 overflow-hidden rounded-box border border-base-300/60 bg-base-200">
	<div
		class="hidden items-center gap-2.5 border-b border-base-300/50 bg-base-300/20 px-3.5 py-2 sm:grid sm:grid-cols-[minmax(130px,1fr)_86px_minmax(130px,1fr)_64px_118px]"
	>
		<div class="text-[11px] font-extrabold uppercase tracking-[0.1em] text-base-content/70">
			{round.label}
		</div>
		<div></div>
		<div></div>
		<div class="text-center text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">
			Your bracket
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
			<FixtureRowKo fixture={f} {roundPicks} {stagePoints} striped={i % 2 === 1} />
		{/each}
	{/if}

	<div class="flex items-center justify-end gap-3 border-t border-base-300/50 px-3.5 py-2.5">
		<span class="text-[12.5px] font-bold tracking-[0.06em] text-primary">Round Total</span>
		<span class="font-display text-[18px] {subtotal > 0 ? 'text-primary' : 'text-base-content/70'}"
			>{subtotal}</span
		>
	</div>
</div>
