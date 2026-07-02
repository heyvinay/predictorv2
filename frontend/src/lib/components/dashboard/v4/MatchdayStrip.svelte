<script lang="ts">
	/** ESPN-style Matchday scoreboard (v2.181.0, compacted + flanked
	 *  v2.191.4). Replaces the original FixturesTable for the dashboard's
	 *  Matchday section — vertical-row table → horizontal pill scoreboard.
	 *
	 *  `items` carries today's fixtures ('today' variant, full emphasis)
	 *  optionally flanked by the most recent finished game from before
	 *  today and up to 2 of tomorrow's fixtures (both 'context', dimmed) —
	 *  see bucketDashboardFixtures' `strip` field for the derivation.
	 *
	 *  Layout:
	 *    - desktop (md+): flex-wrap row — pills keep their compact width
	 *      regardless of count, so 3 vs 8 fixtures never looks lopsided
	 *      (a fixed-column grid would stretch/compress pills unevenly)
	 *    - mobile (< md): flex row with horizontal scroll + snap so the
	 *      user swipes through fixtures while keeping chronological order
	 *
	 *  No section heading — the pills speak for themselves; "All fixtures →"
	 *  is the only chrome, right-aligned above the row.
	 *
	 *  Empty state: collapses entirely (parent's `{#if buckets.strip.length > 0}`
	 *  guard means this only renders when there's something to show).
	 */
	import type { MatchdayStripItem } from '$lib/types/dashboard';
	import MatchdayPill from './MatchdayPill.svelte';

	export let items: MatchdayStripItem[];
</script>

<section>
	<div class="mb-1.5 flex justify-end">
		<a
			href="/results"
			class="whitespace-nowrap font-display text-[12px] font-extrabold text-primary transition-opacity hover:opacity-75"
		>
			All fixtures →
		</a>
	</div>

	<!-- Mobile: flex with overflow-x-auto + snap. Desktop: flex-wrap.
	     The negative-mx/px trick on mobile lets pills bleed into the
	     container's padding so users can see partial pills at the edges
	     (hinting "swipe for more"); desktop neutralises that. -->
	<div
		class="flex gap-1.5 overflow-x-auto pb-2 snap-x snap-mandatory -mx-3 px-3
			   md:flex-wrap md:overflow-x-visible md:pb-0 md:snap-none md:mx-0 md:px-0"
	>
		{#each items as item (item.fixture.id)}
			<MatchdayPill fixture={item.fixture} variant={item.variant} />
		{/each}
	</div>
</section>
