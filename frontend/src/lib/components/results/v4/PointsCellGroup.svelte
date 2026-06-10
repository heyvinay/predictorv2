<script lang="ts">
	/** Group-round per-fixture points pill: EXACT / RESULT / MISS + total.
	 *  `—` until the backend banks points (spec D.2 cell matrix). Display
	 *  logic is pinned by pointsCellFormat.test.ts. */
	import type { PickPoints } from '$lib/types/results';
	import { formatGroupCell } from '$lib/utils/pointsCellFormat';

	export let points: PickPoints | null;

	$: cell = formatGroupCell(points);
	$: toneClass =
		cell.pill?.tone === 'exact'
			? 'bg-success/15 text-success'
			: cell.pill?.tone === 'result'
			? 'bg-warning/15 text-warning-text'
			: 'bg-base-300/30 text-base-content/55';
</script>

{#if !cell.pill}
	<span class="text-xs text-base-content/30">—</span>
{:else}
	<span
		class="inline-flex items-center gap-1 rounded-badge px-2 py-0.5 text-[11px] font-bold {toneClass}"
		title={cell.pill.rarityTitle ?? undefined}
	>
		{#if cell.pill.showRarityStar}
			<span class="text-primary" aria-label="rarity bonus applied">★</span>
		{/if}
		<span class="tracking-[0.06em]">{cell.pill.label}</span>
		<span class="font-display text-[12.5px]">{cell.pill.display}</span>
	</span>
{/if}
