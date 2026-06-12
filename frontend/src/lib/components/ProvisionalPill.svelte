<script lang="ts">
	/** Click-target pill that surfaces the "standings are provisional"
	 *  policy with a small popover and a link to /rules#finalization.
	 *  Used on the leaderboard freshness strip, the standings card header,
	 *  and the dashboard's mini-leaderboard. Variant just shifts the
	 *  visual weight (compact for chrome rows, regular elsewhere). */
	import { onDestroy } from 'svelte';

	export let variant: 'compact' | 'regular' = 'compact';

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

	$: padCls = variant === 'compact' ? 'px-1.5 py-px text-[10px]' : 'px-2 py-0.5 text-[11px]';
</script>

<svelte:window on:click={onWindowClick} on:keydown={onKey} />

<span class="relative inline-flex">
	<button
		bind:this={buttonEl}
		type="button"
		class="inline-flex items-center gap-1 rounded-badge border border-warning/40 bg-warning/10 font-extrabold uppercase tracking-[0.06em] text-warning-text transition-colors hover:bg-warning/20 {padCls}"
		aria-expanded={open}
		aria-haspopup="dialog"
		on:click={toggle}
	>
		<span aria-hidden="true">ⓘ</span>
		Provisional
	</button>

	{#if open}
		<div
			role="dialog"
			aria-label="About provisional standings"
			class="absolute right-0 top-[calc(100%+6px)] z-30 w-[280px] rounded-box border border-base-300/60 bg-base-200 p-3 text-left text-[12px] font-normal normal-case leading-relaxed tracking-normal text-base-content/85 shadow-card"
		>
			<div class="mb-1.5 font-display text-[13px] font-bold tracking-tight">
				Provisional standings
			</div>
			<p>
				Points are scored automatically from match results. Errors are possible — in the
				algorithm, in the upstream data feed, or in an edge case we haven't seen yet.
			</p>
			<p class="mt-1.5">
				Final standings — and any payouts — are confirmed by manual review after all games
				conclude.
				<a
					href="/rules#finalization"
					class="link text-primary"
					on:click={() => (open = false)}>Read more →</a
				>
			</p>
		</div>
	{/if}
</span>
