<script lang="ts">
	/** Click-target pill that surfaces the "these standings include a live
	 *  KO projection" state with a small popover. Mirrors ProvisionalPill's
	 *  popover mechanics (open state, click-outside, Escape-to-close). Badge
	 *  uses the same bg-success/text-white treatment as this codebase's other
	 *  live-score chips (MatchHero, FixtureRowKo); the dot alone stays on the
	 *  error/red token reserved for live/in-progress indicators (RoundTabs'
	 *  pulsing dot, EntryDrawer's live-minute chip). */
	let open = false;
	let buttonEl: HTMLButtonElement;

	function toggle() {
		open = !open;
	}

	function onWindowClick(e: MouseEvent) {
		if (!open) return;
		const tgt = e.target as Node | null;
		if (tgt && buttonEl && !buttonEl.parentElement?.contains(tgt)) open = false;
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape' && open) {
			open = false;
			buttonEl?.focus();
		}
	}
</script>

<svelte:window on:click={onWindowClick} on:keydown={onKey} />

<span class="relative inline-flex">
	<button
		bind:this={buttonEl}
		type="button"
		class="inline-flex items-center gap-0.5 rounded-badge bg-success px-1 py-px text-[10px] font-extrabold uppercase text-white transition-colors hover:bg-success/90"
		aria-expanded={open}
		aria-haspopup="dialog"
		on:click={toggle}
	>
		<span
			class="inline-block h-1.5 w-1.5 rounded-full bg-error animate-pulse-soft"
			aria-hidden="true"
		></span>
		LIVE
	</button>

	{#if open}
		<div
			role="dialog"
			aria-label="About live standings"
			class="absolute right-0 top-[calc(100%+6px)] z-30 w-[280px] rounded-box border border-base-300/60 bg-base-200 p-3 text-left text-[12px] font-normal normal-case leading-relaxed tracking-normal text-base-content/85 shadow-card"
		>
			<div class="mb-1.5 font-display text-[13px] font-bold tracking-tight">Live standings</div>
			<p>
				These standings include knockout matches currently in progress. If a match ended
				right now, the team currently ahead would advance — so points and ranks shown here
				are <b>provisional</b> and can change as the match plays out.
			</p>
			<p class="mt-1.5 text-base-content/60">
				Penalty shootouts don't count until full time. Banked points never move mid-match.
			</p>
		</div>
	{/if}
</span>
