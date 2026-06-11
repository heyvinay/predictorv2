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

<span class="inline-flex items-center gap-1.5">
	<span
		class="min-w-[24px] rounded-[7px] px-0.5 py-0.5 text-center font-display text-sm font-extrabold {medal}"
		>{rank}</span
	>
	<MoveChip {move} />
</span>
