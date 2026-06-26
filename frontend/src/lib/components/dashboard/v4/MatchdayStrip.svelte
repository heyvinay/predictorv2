<script lang="ts">
	/** ESPN-style Matchday scoreboard (v2.181.0). Replaces the original
	 *  FixturesTable for the dashboard's Matchday section — vertical-row
	 *  table → horizontal pill scoreboard.
	 *
	 *  Layout:
	 *    - desktop (md+): 6-column grid, full container width
	 *    - mobile (< md): flex row with horizontal scroll + snap so the
	 *      user swipes through fixtures while keeping chronological order
	 *
	 *  Empty state: collapses entirely (parent's `{#if buckets.matchday.length > 0}`
	 *  guard means this only renders when there's something to show).
	 */
	import type { Fixture } from '$types';
	import MatchdayPill from './MatchdayPill.svelte';

	export let fixtures: Fixture[];
</script>

<section>
	<header class="mb-2 flex items-baseline justify-between gap-3">
		<h2 class="font-display text-lg font-bold tracking-wide text-base-content">Matchday</h2>
		<a
			href="/results"
			class="whitespace-nowrap font-display text-[12px] font-extrabold text-primary transition-opacity hover:opacity-75"
		>
			All fixtures →
		</a>
	</header>

	<!-- Mobile: flex with overflow-x-auto + snap. Desktop: 6-col grid.
	     The negative-mx/px trick on mobile lets pills bleed into the
	     container's padding so users can see partial pills at the edges
	     (hinting "swipe for more"); desktop neutralises that. -->
	<div
		class="flex gap-2 overflow-x-auto pb-2 snap-x snap-mandatory -mx-3 px-3
			   md:grid md:grid-cols-6 md:overflow-x-visible md:pb-0 md:snap-none md:mx-0 md:px-0"
	>
		{#each fixtures as f (f.id)}
			<MatchdayPill fixture={f} />
		{/each}
	</div>
</section>
