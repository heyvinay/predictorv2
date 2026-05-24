<!--
	ChampionStrip — gold sticker strip showing the user's predicted
	tournament winner. Used in two places:
	  1. Desktop: directly under the Final column inside the wallchart
	  2. Mobile: persistent footer above the prev/next nav

	Purely display. Falls back to a "not selected" italic when no winner
	has been chosen yet.
-->
<script lang="ts">
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { teamCode } from '$lib/utils/teamCodes';

	export let champion: string | null = null;
	/** Number of match winners picked so far (out of `total`). */
	export let picked: number = 0;
	export let total: number = 31;
	/** Compact variant for tight spaces (smaller padding, smaller name). */
	export let compact: boolean = false;
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
				class="rounded-sm shadow-sm {compact ? 'w-5 h-3.5' : 'w-6 h-4'}"
			/>
		{/if}
		<span
			class="font-display tracking-wide truncate {compact ? 'text-base' : 'text-lg'}"
		>
			{champion.toUpperCase()}
		</span>
		<span
			class="text-[10px] font-mono uppercase tracking-widest opacity-60 ml-auto flex-shrink-0"
		>
			{picked}/{total}
		</span>
	{:else}
		<span class="italic opacity-60 text-sm">Not selected</span>
		<span
			class="text-[10px] font-mono uppercase tracking-widest opacity-60 ml-auto flex-shrink-0"
		>
			{picked}/{total}
		</span>
	{/if}
</div>
