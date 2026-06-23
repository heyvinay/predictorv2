<script lang="ts">
	import type { MinimapMarker } from '$lib/types/leaderboard';

	export let markers: MinimapMarker[];
	export let rankRange: [number, number];
	export let totalParticipants: number;

	$: x = (rank: number) => ((rank - 1) / Math.max(1, totalParticipants - 1)) * 100;
	$: sliceStart = x(rankRange[0]);
	$: sliceEnd = x(rankRange[1]);
</script>

<div class="mt-2">
	<p class="text-xs text-base-content/40 mb-1">Where this slice sits in the pool of {totalParticipants}</p>
	<div class="relative h-3.5 bg-base-100 border border-base-300 rounded">
		<div
			class="absolute h-full bg-primary/15 border-x border-primary/40 rounded"
			style="left:{sliceStart}%; width:{sliceEnd - sliceStart}%"
		></div>
		{#each markers as m (m.rank + '-' + m.kind)}
			<div
				class="absolute w-1.5 h-1.5 rounded-full top-1/2 -translate-y-1/2"
				class:bg-primary={m.kind === 'you'}
				class:bg-success={m.kind === 'leader'}
				style="left:calc({x(m.rank)}% - 3px)"
			></div>
		{/each}
	</div>
	<div class="flex justify-between text-[10px] text-base-content/40 mt-1 font-mono">
		<span>#1</span><span>#{totalParticipants}</span>
	</div>
</div>
