<!--
	ChampionStrip — gold sticker strip showing the user's predicted
	tournament winner. Used in two places:
	  1. Desktop: directly under the Final column inside the wallchart
	     (set showPicks={false} — the count is already in the header)
	  2. Mobile: persistent footer above the prev/next nav
	     (set showPicks={true})

	Uses DaisyUI theme tokens (bg-primary gold sticker, border-error
	red frame, text-primary-content for body text) so the strip swaps
	colours with the active theme.
-->
<script lang="ts">
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';

	export let champion: string | null = null;
	/** Number of match winners picked so far (out of `total`). */
	export let picked: number = 0;
	export let total: number = 31;
	/** Compact variant for tight spaces (smaller padding, smaller name). */
	export let compact: boolean = false;
	/** Show the "picked/total" counter. Hide on desktop where the header carries it. */
	export let showPicks: boolean = true;
</script>

<div
	class="flex items-center gap-3 rounded-lg border-2 border-error
		bg-primary text-primary-content
		{compact ? 'px-3 py-1.5' : 'px-4 py-2.5'}"
>
	<span
		class="text-[10px] font-mono uppercase tracking-widest opacity-70 flex-shrink-0"
		aria-hidden="true">★ My Champion</span
	>

	{#if champion}
		{#if hasFlag(champion)}
			<img
				src={getFlagUrl(champion, 'sm')}
				alt=""
				class="rounded-sm shadow-sm flex-shrink-0 {compact ? 'w-5 h-3.5' : 'w-6 h-4'}"
			/>
		{/if}
		<span class="font-display tracking-wide {compact ? 'text-base' : 'text-lg'}">
			{champion.toUpperCase()}
		</span>
		{#if showPicks}
			<span
				class="text-[10px] font-mono uppercase tracking-widest opacity-60 ml-auto flex-shrink-0"
			>
				{picked}/{total}
			</span>
		{/if}
	{:else}
		<span class="italic opacity-60 text-sm">Not selected</span>
		{#if showPicks}
			<span
				class="text-[10px] font-mono uppercase tracking-widest opacity-60 ml-auto flex-shrink-0"
			>
				{picked}/{total}
			</span>
		{/if}
	{/if}
</div>
