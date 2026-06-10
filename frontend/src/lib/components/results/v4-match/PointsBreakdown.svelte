<script lang="ts">
	/** "How those N points were assigned" — base/rarity/total tiles.
	 *  Values come straight from the entry's B.1 PickPoints; labels from
	 *  scoring-rules (C.1). Hidden by the parent when total = 0. */
	import type { PickPoints } from '$lib/types/results';

	export let points: PickPoints;

	$: baseLabel = points.base_kind === 'exact' ? 'EXACT SCORE' : 'RIGHT WINNER';
	$: baseTone = points.base_kind === 'exact' ? 'text-success' : 'text-warning-text';
</script>

<div class="rounded-box border border-base-300/60 bg-base-200 p-4">
	<div class="mb-2.5 text-[10px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">
		How those {points.total} points were assigned
	</div>
	<div class="flex gap-2">
		<div class="flex flex-1 flex-col items-center gap-1 rounded-btn bg-base-300/25 px-2 py-2.5">
			<span class="text-[9px] font-extrabold tracking-[0.08em] text-base-content/55">{baseLabel}</span>
			<span class="font-display text-[18px] {baseTone}">+{points.base}</span>
		</div>
		{#if points.rarity > 0}
			<div class="flex flex-1 flex-col items-center gap-1 rounded-btn bg-primary/10 px-2 py-2.5">
				<span class="text-[9px] font-extrabold tracking-[0.08em] text-base-content/55">★ RARITY</span>
				<span class="font-display text-[18px] text-primary">+{points.rarity}</span>
			</div>
		{/if}
		<div class="flex flex-1 flex-col items-center gap-1 rounded-btn bg-base-300/25 px-2 py-2.5">
			<span class="text-[9px] font-extrabold tracking-[0.08em] text-base-content/55">TOTAL</span>
			<span class="font-display text-[18px] text-primary">+{points.total}</span>
		</div>
	</div>
</div>
