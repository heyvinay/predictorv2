<script lang="ts">
	import type { RaceStory } from '$lib/types/leaderboard';
	import { createEventDispatcher } from 'svelte';

	export let story: RaceStory;
	const dispatch = createEventDispatcher<{ open: { entry_id: string; compare_id: string | null } }>();

	const EYEBROWS: Record<RaceStory['kind'], string> = {
		biggest_climb: '▲ Biggest climber',
		steepest_fall: '▼ Steepest fall',
		hottest_streak: '🔥 Hottest streak',
		phoenix: '🦅 Phoenix',
		slow_burn: '🌱 Slow burn',
		steady_hand: '🐢 Steady hand'
	};

	const COLORS: Record<RaceStory['kind'], string> = {
		biggest_climb: 'text-success',
		steepest_fall: 'text-error',
		hottest_streak: 'text-primary',
		phoenix: 'text-success',
		slow_burn: 'text-success',
		steady_hand: 'text-primary'
	};

	$: minR = Math.min(...story.sparkline.map(p => p.rank));
	$: maxR = Math.max(...story.sparkline.map(p => p.rank));
	$: range = Math.max(1, maxR - minR);

	function pathFor(points: typeof story.sparkline): string {
		const w = 280, h = 50;
		return points
			.map((p, i) => {
				const x = (i / Math.max(1, points.length - 1)) * w;
				const y = ((p.rank - minR) / range) * h;
				return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
			})
			.join(' ');
	}
</script>

<button
	type="button"
	class="ministory text-left w-full bg-base-100 border border-base-300 rounded-box p-4 hover:border-primary/50 transition"
	on:click={() => dispatch('open', { entry_id: story.subject_entry_id, compare_id: story.compare_entry_id })}
>
	<div class="text-[11px] font-bold tracking-wide uppercase {COLORS[story.kind]}">
		{EYEBROWS[story.kind]}
	</div>
	<p class="font-bold mt-1 mb-0.5">{story.title}</p>
	<p class="text-sm text-base-content/55 m-0">{story.caption}</p>
	<svg viewBox="0 0 280 50" class="mt-2 w-full">
		<path d={pathFor(story.sparkline)} stroke="currentColor" stroke-width="2.5" fill="none" class={COLORS[story.kind]} />
		{#if story.compare_sparkline}
			<path d={pathFor(story.compare_sparkline)} stroke="currentColor" stroke-width="2.5" fill="none" class="text-warning-text" />
		{/if}
	</svg>
</button>
