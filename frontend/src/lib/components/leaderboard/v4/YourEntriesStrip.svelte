<script lang="ts">
	/** Gold-tinted toolbar under the header: search box left (grows to
	 *  max-w-sm on desktop, full row on phones), best-rank summary when
	 *  the user has entries on the board, pool filter pills
	 *  (All / Atlas / JMFA / Guests) right. Pool selection persists;
	 *  filtering keeps global ranks (spec §2). */
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

	// Arrow-key cycling within the radiogroup (review P2). Tab still
	// moves out of the group; Home/End jump to ends. Left/Right wrap.
	function onPoolKey(e: KeyboardEvent) {
		const i = POOLS.indexOf(pool);
		if (i < 0) return;
		let next = i;
		if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (i + 1) % POOLS.length;
		else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp')
			next = (i - 1 + POOLS.length) % POOLS.length;
		else if (e.key === 'Home') next = 0;
		else if (e.key === 'End') next = POOLS.length - 1;
		else return;
		e.preventDefault();
		onPool(POOLS[next]);
		// Move keyboard focus to the newly-checked option so screen readers
		// announce the change (standard roving-tabindex pattern).
		const btn = (e.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>(
			'button[role="radio"]'
		)[next];
		btn?.focus();
	}
</script>

<div
	class="mb-4 flex flex-wrap items-center justify-between gap-x-3 gap-y-2 rounded-box border-[1.5px] border-primary/30 bg-primary/[0.06] px-3 py-2.5 sm:gap-x-4 sm:px-4 sm:py-3"
>
	<label class="relative min-w-[180px] flex-1 sm:max-w-sm">
		<span
			class="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-[11px] text-base-content/40 sm:left-2.5 sm:text-xs"
			aria-hidden="true">⌕</span
		>
		<input
			type="search"
			bind:value={search}
			placeholder="Search name…"
			aria-label="Search entries by person or entry name"
			class="h-[30px] w-full rounded-full border-[1.5px] border-base-300/80 bg-base-200 pl-6 pr-2 text-[11px] font-semibold text-base-content placeholder:text-base-content/40 transition-colors focus:border-primary focus:outline-none sm:h-[34px] sm:pl-7 sm:pr-2.5 sm:text-xs"
		/>
	</label>

	{#if best}
		<span class="text-xs text-base-content/70">
			best is <b class="font-display font-extrabold text-primary">#{best.bestRank}</b>
			{#if best.ptsOffLead > 0}
				· {best.ptsOffLead} pts off the lead
			{:else}
				· leading the pool
			{/if}
		</span>
	{/if}

	<div
		class="flex flex-wrap gap-1 sm:gap-1.5"
		role="radiogroup"
		aria-label="Pool filter"
		on:keydown={onPoolKey}
	>
			{#each POOLS as p}
				<button
					role="radio"
					aria-checked={pool === p}
					tabindex={pool === p ? 0 : -1}
					class="inline-flex items-center gap-1 rounded-full border-[1.5px] px-2 py-0.5 font-display text-[11px] font-extrabold tracking-[0.03em] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary sm:gap-1.5 sm:px-3.5 sm:py-1.5 sm:text-xs {pool ===
					p
						? 'border-primary bg-primary/10 text-primary'
						: 'border-base-300/80 bg-base-200 text-base-content/70 hover:border-base-300 hover:text-base-content'}"
					on:click={() => onPool(p)}
				>
					{p}
					<span
						class="rounded-full px-1 py-px text-[9px] sm:px-1.5 sm:text-[10px] {pool === p
							? 'bg-primary/20 text-primary'
							: 'bg-base-content/10 text-base-content/55'}">{counts[p]}</span
					>
				</button>
			{/each}
	</div>
</div>
