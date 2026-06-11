<script lang="ts">
	/** 4×4(+axis) pick-distribution bubble grid, 0..3+ each side.
	 *
	 *  Layout: the grid stretches to fill the card width (1fr columns)
	 *  with a max-w cap so it doesn't dominate wide containers. Each
	 *  cell is `aspect-square`, so cells scale together as the card
	 *  resizes. Bubble area inside each cell is sized ∝ pick count
	 *  (30%–90% of the cell).
	 *
	 *  Bubble colour encodes the outcome — amber for home win, neutral
	 *  for draw, green for away win — with the user's pick taking gold
	 *  precedence and a gold ring around its cell. Match result (played
	 *  mode) gets a green ring; an exact-match pick stacks both rings.
	 */
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

	function cellRing(h: number, a: number): string {
		const isYour = !!yourCell && yourCell[0] === h && yourCell[1] === a;
		const isActual = !!actualCell && actualCell[0] === h && actualCell[1] === a;
		if (isYour && isActual) return 'ring-2 ring-success bg-success/[0.08]';
		if (isActual) return 'ring-2 ring-success/70';
		if (isYour) return 'ring-2 ring-primary bg-primary/[0.06]';
		return '';
	}

	// Chart-fill palette (Tailwind utility colours, not DaisyUI semantics).
	// The mockup uses #fbbf24 / #34d399 directly — `bg-warning`/`bg-success`
	// in this theme are surface tokens with dark foregrounds, which made
	// the bubbles render brown/illegible. Tailwind's amber-400 / emerald-400
	// + their 900 text companions give bright bubbles with readable counts
	// in both themes (CLAUDE.md "text-warning is a surface trap" rule).
	function bubbleColour(h: number, a: number): string {
		const isYour = !!yourCell && yourCell[0] === h && yourCell[1] === a;
		if (isYour) return 'bg-primary text-base-100';
		if (h > a) return 'bg-amber-400 text-amber-900';
		if (h < a) return 'bg-emerald-400 text-emerald-900';
		return 'bg-slate-400/80 text-slate-900';
	}
</script>

<div class="rounded-box border border-base-300/60 bg-base-200 p-4">
	<div class="mb-2 flex items-center justify-between">
		<span class="font-display text-sm font-bold">
			{mode === 'played' ? 'Scoreline spread' : 'Predicted scorelines'}
		</span>
		<span class="text-[10px] text-base-content/55">bubble size ∝ # picks</span>
	</div>

	<!-- Responsive grid: 1fr columns scale to fill the card; cells stay
	     square via aspect-square. A max-w cap stops the chart from
	     ballooning on very wide containers. -->
	<div class="mx-auto w-full max-w-[480px]">
		<!-- away axis -->
		<div class="mb-1 grid grid-cols-[24px_repeat(4,1fr)] gap-1">
			<span></span>
			{#each axis as a (a)}
				<span class="text-center text-[11px] font-bold text-base-content/55"
					>{a === 3 ? '3+' : a}</span
				>
			{/each}
		</div>

		<div class="grid grid-cols-[24px_repeat(4,1fr)] gap-1">
			{#each grid as row, h (h)}
				<span
					class="flex items-center justify-center text-[11px] font-bold text-base-content/55"
					>{h === 3 ? '3+' : h}</span
				>
				{#each row as n, a (a)}
					<div
						class="grid aspect-square place-items-center rounded-md border border-base-300/40 {cellRing(
							h,
							a
						)}"
					>
						{#if n > 0}
							<span
								class="grid place-items-center rounded-full font-display text-xs font-bold shadow-sm {bubbleColour(
									h,
									a
								)}"
								style="width: {30 + (n / max) * 60}%; aspect-ratio: 1;"
							>
								{n}
							</span>
						{/if}
					</div>
				{/each}
			{/each}
		</div>
	</div>

	<div class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[10.5px] font-semibold text-base-content/70">
		{#if mode === 'played' && actualCell}
			<span class="inline-flex items-center gap-1.5">
				<span class="h-2 w-2 rounded-full bg-success"></span>
				actual ({actualCell[0] === 3 ? '3+' : actualCell[0]}-{actualCell[1] === 3
					? '3+'
					: actualCell[1]})
			</span>
		{/if}
		<span class="inline-flex items-center gap-1.5">
			<span class="h-2 w-2 rounded-full bg-amber-400"></span>
			{displayTeamName(fixture.home_team)} win
		</span>
		<span class="inline-flex items-center gap-1.5">
			<span class="h-2 w-2 rounded-full bg-slate-400/80"></span> Draw
		</span>
		<span class="inline-flex items-center gap-1.5">
			<span class="h-2 w-2 rounded-full bg-emerald-400"></span>
			{displayTeamName(fixture.away_team)} win
		</span>
		<span class="inline-flex items-center gap-1.5">
			<span class="h-2 w-2 rounded-full bg-primary"></span> your pick
		</span>
		<span class="ml-auto text-base-content/40">
			{displayTeamName(fixture.home_team).toUpperCase()} ↓ · {displayTeamName(
				fixture.away_team
			).toUpperCase()} →
		</span>
	</div>
</div>
