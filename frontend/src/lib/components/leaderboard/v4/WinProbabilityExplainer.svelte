<script lang="ts">
	/** ⓘ popover next to the Prob% column header on the Win Probability
	 *  tab — plain-English background on how Prob% and Proj are actually
	 *  computed. Same compact-icon pattern as the Standings "ⓘ next to
	 *  Total header" (no standalone "For the nerds" text label) and
	 *  results/v4/PointsHelpButton.svelte. */
	export let marketBased: boolean;

	let open = false;
	let containerEl: HTMLSpanElement;

	function onWindowClick(e: MouseEvent) {
		if (!open || !containerEl) return;
		if (!containerEl.contains(e.target as Node)) open = false;
	}
	function onKey(e: KeyboardEvent) {
		if (open && e.key === 'Escape') open = false;
	}
</script>

<svelte:window on:click={onWindowClick} on:keydown={onKey} />

<span bind:this={containerEl} class="relative inline-flex">
	<button
		type="button"
		class="grid h-3.5 w-3.5 flex-none place-items-center rounded-full bg-base-300/60 text-[10px] font-normal leading-none normal-case tracking-normal text-base-content/55 transition-colors hover:text-primary"
		aria-expanded={open}
		aria-label="How Prob% and Proj are worked out"
		on:click|stopPropagation={() => (open = !open)}
	>
		ⓘ
	</button>

	{#if open}
		<div
			class="absolute right-0 top-[calc(100%+6px)] z-30 w-[280px] rounded-box border border-primary/30 bg-base-200 p-3 text-left text-[12px] font-normal normal-case leading-relaxed tracking-normal text-base-content/85 shadow-card"
			role="dialog"
		>
			<div class="mb-1.5 font-display text-[13px] font-bold tracking-tight">
				How Prob% &amp; Proj are worked out
			</div>
			<p>
				We simulate every possible way the remaining knockout matches could go, thousands of times
				over. <b>Prob%</b> is how often an entry finishes 1st across all those simulations, and
				<b>Proj</b> is that entry's probability-weighted final points total.
			</p>
			{#if marketBased}
				<p class="mt-1.5">
					Right now that simulation is weighted by real betting-market odds (Polymarket, live
					sportsbooks) on the next unresolved match, instead of a flat coin-toss — so a strong
					favourite gets a realistic edge.
				</p>
			{:else}
				<p class="mt-1.5">
					No betting market has priced the next match yet, so both figures come from a flat
					50/50 coin-toss simulation instead — they'll switch to market odds automatically the
					moment one prices in.
				</p>
			{/if}
			<p class="mt-1.5 text-base-content/55">
				Nothing here is fixed — every simulation reruns from the current bracket state, so these
				numbers shift as matches finish.
			</p>
		</div>
	{/if}
</span>
