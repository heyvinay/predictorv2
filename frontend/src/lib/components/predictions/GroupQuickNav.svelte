<!--
	GroupQuickNav — horizontal scrollable A-L letter strip.

	Each letter button is a small square (44px tap target). Tapping
	smooth-scrolls the page to that group's accordion and emits
	an `open` event so the parent can ensure the accordion is expanded.

	Letters turn success/green when their group is 100% predicted;
	otherwise muted. No horizontal scrollbar visible (overflow-x:auto
	with the scrollbar visually hidden via .scrollbar-hide style).

	Sits between the progress section and the accordion list.
-->
<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import type { FixturesByGroup } from '$lib/types';

	export let groups: FixturesByGroup[] = [];
	export let getPrediction: (fixtureId: string) => { home: number; away: number } | null = () =>
		null;

	const dispatch = createEventDispatcher<{ navigate: { groupLetter: string } }>();

	// Per-letter completion: count fixtures with non-null prediction.
	$: groupMeta = groups
		.filter((g) => g.group !== 'thirdplace')
		.map((g) => {
			const done = g.fixtures.filter((f) => getPrediction(f.id) !== null).length;
			const total = g.fixtures.length;
			return {
				letter: g.group,
				done,
				total,
				complete: total > 0 && done === total
			};
		});

	function handleTap(letter: string) {
		// Smooth-scroll target: the accordion header element. Parent uses
		// the navigate event to also force-open the accordion.
		const header = document.querySelector(`[aria-controls="group-${letter}-body"]`);
		header?.scrollIntoView({ behavior: 'smooth', block: 'start' });
		dispatch('navigate', { groupLetter: letter });
	}
</script>

<div
	class="flex gap-1.5 overflow-x-auto py-1 px-1 -mx-1 scrollbar-hide"
	role="navigation"
	aria-label="Jump to group"
>
	{#each groupMeta as g (g.letter)}
		<button
			type="button"
			class="flex-shrink-0 min-w-11 min-h-11 px-2 rounded-lg border font-mono font-bold text-sm flex items-center justify-center transition-colors
				{g.complete
				? 'bg-success/15 border-success/40 text-success'
				: 'bg-base-300/30 border-base-content/10 text-base-content/60 hover:text-base-content'}"
			on:click={() => handleTap(g.letter)}
			aria-label="Group {g.letter}, {g.done} of {g.total} predicted"
			title="Group {g.letter} · {g.done}/{g.total}"
		>
			{g.letter}
		</button>
	{/each}
</div>

<style>
	/* Hide the scrollbar visually while keeping scroll behavior. */
	.scrollbar-hide {
		scrollbar-width: none; /* Firefox */
	}
	.scrollbar-hide::-webkit-scrollbar {
		display: none; /* Chrome / Safari */
	}
</style>
