<script lang="ts">
	/** `+{stagePts}×{hits}: {total}` — stage points are stage-specific from
	 *  scoring-rules (R32:20 … F:75), never hardcoded (C.1). Banked at
	 *  lineup-set, so this renders for LIVE and upcoming fixtures too.
	 *  Display logic pinned by pointsCellFormat.test.ts. */
	import { formatKoCell } from '$lib/utils/pointsCellFormat';

	export let stagePoints: number;
	export let hits: number;
	/** False for third_place rows and unseeded fixtures → renders a dash. */
	export let applicable = true;

	$: cell = formatKoCell(stagePoints, hits, applicable);
	$: toneClass =
		cell.line?.tone === 'full'
			? 'text-success'
			: cell.line?.tone === 'half'
			? 'text-warning-text'
			: 'text-base-content/40';
</script>

{#if !cell.line}
	<span class="text-xs text-base-content/30">—</span>
{:else}
	<span class="inline-flex items-baseline gap-1 {toneClass}">
		<span class="text-[11px] font-bold">{cell.line.breakdown}</span>
		<b class="font-display text-[14px]">{cell.line.total}</b>
	</span>
{/if}
