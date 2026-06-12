<script lang="ts">
	/** Rank number (gold/silver/bronze chip for 1/2/3) + movement chip. */
	import MoveChip from './MoveChip.svelte';

	export let rank: number;
	export let move: number | null | undefined = null;

	$: medal =
		rank === 1
			? 'bg-primary/15 text-primary'
			: rank === 2
			? 'bg-base-content/15 text-base-content/80'
			: rank === 3
			? 'bg-amber-700/20 text-amber-600'
			: 'text-base-content/70';
</script>

<!-- <880px the movement chip stacks under the rank so the cell fits a
     narrow track and the entry name can hug the left edge; ≥880px the
     pair sits side by side as before. -->
<span class="inline-flex max-[879px]:flex-col max-[879px]:items-start min-[880px]:items-center min-[880px]:gap-1.5">
	<span
		class="min-w-[24px] rounded-[7px] px-0.5 py-0.5 text-center font-display text-sm font-extrabold {medal}"
		>{rank}</span
	>
	<MoveChip {move} />
</span>
