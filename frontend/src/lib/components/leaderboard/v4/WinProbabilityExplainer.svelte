<script lang="ts">
	/** "For the nerds" ℹ popover on the Win Probability tab — plain-English
	 *  background on how Win% / T3 / ER / Odds% are actually computed.
	 *  Same popover pattern as ScoringExplainer.svelte (Standings) and
	 *  results/v4/PointsHelpButton.svelte. */
	export let hasOdds: boolean;

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
		class="inline-flex items-center gap-1 text-[11px] font-semibold text-base-content/55 transition-colors hover:text-primary"
		aria-expanded={open}
		on:click|stopPropagation={() => (open = !open)}
	>
		<span
			class="grid h-3.5 w-3.5 place-items-center rounded-full bg-base-300/60 text-[10px] leading-none"
			aria-hidden="true">ⓘ</span
		>
		For the nerds
	</button>

	{#if open}
		<div
			class="absolute left-0 top-[calc(100%+6px)] z-30 w-[300px] rounded-box border border-primary/30 bg-base-200 p-3 text-left text-[12px] font-normal normal-case leading-relaxed text-base-content/85 shadow-card"
			role="dialog"
		>
			<div class="mb-1.5 font-display text-[13px] font-bold tracking-tight">
				How Win% &amp; Odds% are worked out
			</div>
			<p>
				We simulate every possible way the remaining knockout matches could go — each unplayed
				match a <b>coin-flip</b>, thousands of times over. <b>Win%</b> is how often an entry
				finishes 1st across all those simulations; <b>T3</b> is top-3, and <b>ER</b> ("expected
				rank") is the average finishing position.
			</p>
			{#if hasOdds}
				<p class="mt-1.5">
					<b>Odds%</b> re-runs the same simulation, but swaps the coin-flip for real betting-market
					odds (Polymarket, live sportsbooks) on whichever upcoming matches are already priced —
					so a strong favourite gets a realistic edge instead of a flat 50/50.
				</p>
			{:else}
				<p class="mt-1.5">
					An <b>Odds%</b> column will appear once a real betting market prices one of the next
					matches — it re-runs the same simulation swapping the coin-flip for that market's odds.
				</p>
			{/if}
			<p class="mt-1.5 text-base-content/55">
				Nothing here is fixed — every simulation reruns from the current bracket state, so these
				numbers shift as matches finish.
			</p>
		</div>
	{/if}
</span>
