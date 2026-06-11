<script lang="ts">
	/** Gold-tinted band under the header: your best rank + gap to the lead
	 *  on the left, pool filter pills (All / Atlas / JMFA / Guests) right.
	 *  Pool selection persists; filtering keeps global ranks (spec §2). */
	import type { LbEntryV4, LbPool } from '$lib/types/leaderboard';
	import { bestOwnSummary, poolCounts } from '$lib/utils/leaderboardV4';

	export let rows: LbEntryV4[];
	export let userId: string | null | undefined;
	export let pool: LbPool;
	export let onPool: (p: LbPool) => void;
	/** Two-way bound search query (person or entry name). */
	export let search = '';

	const POOLS: LbPool[] = ['All', 'Atlas', 'JMFA', 'Guests'];

	$: counts = poolCounts(rows);
	$: best = bestOwnSummary(rows, userId);
</script>

<div
	class="mb-4 flex flex-wrap items-center justify-between gap-4 rounded-box border-[1.5px] border-primary/30 bg-primary/[0.06] px-4 py-3"
>
	<div class="flex flex-col gap-1">
		<span class="font-display text-[10px] font-extrabold uppercase tracking-[0.12em] text-primary"
			>Your entries</span
		>
		{#if best}
			<span class="text-xs text-base-content/70">
				best is <b class="font-display font-extrabold text-primary">#{best.bestRank}</b>
				{#if best.ptsOffLead > 0}
					· {best.ptsOffLead} pts off the lead
				{:else}
					· leading the pool
				{/if}
			</span>
		{:else}
			<span class="text-xs text-base-content/55">no eligible entry on the board</span>
		{/if}
	</div>

	<div class="flex flex-wrap items-center gap-1.5">
		<label class="relative">
			<span
				class="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-base-content/40"
				aria-hidden="true">⌕</span
			>
			<input
				type="search"
				bind:value={search}
				placeholder="Search name…"
				aria-label="Search entries by person or entry name"
				class="h-[34px] w-36 rounded-full border-[1.5px] border-base-300/80 bg-base-200 pl-7 pr-2.5 text-xs font-semibold text-base-content placeholder:text-base-content/40 focus:border-primary focus:outline-none sm:w-44 sm:focus:w-52 transition-all"
			/>
		</label>
		<div class="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Pool filter">
		{#each POOLS as p}
			<button
				role="radio"
				aria-checked={pool === p}
				class="inline-flex items-center gap-1.5 rounded-full border-[1.5px] px-3.5 py-1.5 font-display text-xs font-extrabold tracking-[0.03em] transition-colors {pool ===
				p
					? 'border-primary bg-primary/10 text-primary'
					: 'border-base-300/80 bg-base-200 text-base-content/70 hover:border-base-300 hover:text-base-content'}"
				on:click={() => onPool(p)}
			>
				{p}
				<span
					class="rounded-full px-1.5 py-px text-[10px] {pool === p
						? 'bg-primary/20 text-primary'
						: 'bg-base-content/10 text-base-content/55'}">{counts[p]}</span
				>
			</button>
		{/each}
		</div>
	</div>
</div>
