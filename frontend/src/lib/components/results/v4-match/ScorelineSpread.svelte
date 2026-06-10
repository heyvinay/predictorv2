<script lang="ts">
	/** 4×4(+axis) pick-distribution bubble grid, 0..3+ each side.
	 *  mode='played': exact (actual∩your) / actual / your rings.
	 *  mode='upcoming': cells tinted by the side they imply. */
	import type { Fixture } from '$types';
	import type { SpreadGrid } from '$lib/types/results';
	import { displayTeamName } from '$lib/utils/teamName';

	export let fixture: Fixture;
	export let mode: 'played' | 'upcoming';
	export let grid: SpreadGrid;
	export let yourCell: [number, number] | null = null; // [home, away], clamped 0..3
	export let actualCell: [number, number] | null = null;

	$: max = Math.max(1, ...grid.flat());
	$: totalPicks = grid.flat().reduce((s, n) => s + n, 0);
	$: axis = grid.length > 0 ? grid[0].map((_, i) => i) : [];

	function cellClasses(h: number, a: number, n: number): string {
		const isYour = !!yourCell && yourCell[0] === h && yourCell[1] === a;
		const isActual = !!actualCell && actualCell[0] === h && actualCell[1] === a;
		let cls = '';
		if (mode === 'upcoming' && n > 0) {
			cls +=
				h > a ? ' bg-warning/10' : h < a ? ' bg-error/10' : ' bg-base-300/20';
		}
		if (isYour && isActual) cls += ' ring-2 ring-success';
		else if (isActual) cls += ' ring-2 ring-success/60';
		else if (isYour) cls += ' ring-2 ring-primary';
		return cls;
	}
</script>

<div class="rounded-box border border-base-300/60 bg-base-200 p-4">
	<div class="mb-2 flex items-center justify-between">
		<span class="font-display text-[15px]">
			{mode === 'played' ? 'Scoreline spread' : 'Predicted scorelines'}
		</span>
		<span class="text-[11px] text-base-content/55">{totalPicks} entries · size ∝ picks</span>
	</div>

	<!-- away axis -->
	<div class="grid grid-cols-[22px_repeat(4,1fr)] gap-1 px-0.5 pb-1">
		<span></span>
		{#each axis as a (a)}
			<span class="text-center text-[10px] font-bold text-base-content/55">{a === 3 ? '3+' : a}</span>
		{/each}
	</div>

	<div class="grid grid-cols-[22px_repeat(4,1fr)] gap-1">
		{#each grid as row, h (h)}
			<span class="flex items-center justify-center text-[10px] font-bold text-base-content/55"
				>{h === 3 ? '3+' : h}</span
			>
			{#each row as n, a (a)}
				<span
					class="grid aspect-square place-items-center rounded-btn border border-base-300/30 {cellClasses(
						h,
						a,
						n
					)}"
				>
					{#if n > 0}
						<span
							class="grid place-items-center rounded-full bg-base-content/15 font-display text-[11px]"
							style="width: {30 + (n / max) * 55}%; aspect-ratio: 1;"
						>
							{n}
						</span>
					{/if}
				</span>
			{/each}
		{/each}
	</div>

	<div class="mt-3 flex flex-wrap gap-3 text-[10.5px] font-semibold text-base-content/70">
		{#if mode === 'played'}
			{#if actualCell}
				<span class="inline-flex items-center gap-1">
					<span class="h-2 w-2 rounded-full ring-2 ring-success"></span>
					actual ({actualCell[0] === 3 ? '3+' : actualCell[0]}-{actualCell[1] === 3 ? '3+' : actualCell[1]})
				</span>
			{/if}
			<span class="inline-flex items-center gap-1">
				<span class="h-2 w-2 rounded-full ring-2 ring-primary"></span> your pick
			</span>
		{:else}
			<span class="inline-flex items-center gap-1">
				<span class="h-2 w-2 rounded-sm bg-warning/40"></span>
				{displayTeamName(fixture.home_team)} win
			</span>
			<span class="inline-flex items-center gap-1">
				<span class="h-2 w-2 rounded-sm bg-base-300/60"></span> Draw
			</span>
			<span class="inline-flex items-center gap-1">
				<span class="h-2 w-2 rounded-sm bg-error/40"></span>
				{displayTeamName(fixture.away_team)} win
			</span>
			<span class="inline-flex items-center gap-1">
				<span class="h-2 w-2 rounded-full ring-2 ring-primary"></span> your pick
			</span>
		{/if}
	</div>
	<div class="mt-1.5 text-[10px] text-base-content/40">
		{displayTeamName(fixture.home_team).toUpperCase()} ↓ · {displayTeamName(
			fixture.away_team
		).toUpperCase()} →
	</div>
</div>
