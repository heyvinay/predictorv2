<script lang="ts">
	/** Horizontal-scroll round tabs. Active = faint gold outline (NO glow).
	 *  A pulsing red dot marks rounds with a LIVE fixture; the same
	 *  roundsWithLive set drives the Summary rows (spec D.1b). On mount the
	 *  page pre-selects the live/default round and this component scrolls
	 *  it into view. */
	import type { RoundDef, RoundId } from '$lib/types/results';

	export let rounds: RoundDef[];
	export let selected: RoundId;
	export let liveRounds: Set<RoundId>;
	export let onSelect: (id: RoundId) => void;

	function scrollActive(node: HTMLElement, active: boolean) {
		function maybe(isActive: boolean) {
			if (isActive)
				node.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
		}
		maybe(active);
		return { update: maybe };
	}
</script>

<div
	role="tablist"
	aria-label="Rounds"
	class="sticky top-0 z-10 mt-4 flex items-stretch gap-1 overflow-x-auto rounded-full border border-base-300/55 bg-base-100/95 p-1 backdrop-blur [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
>
	{#each rounds as r (r.id)}
		{@const active = r.id === selected}
		<button
			role="tab"
			aria-selected={active}
			use:scrollActive={active}
			class="relative flex min-w-fit flex-none flex-col items-center gap-0.5 whitespace-nowrap rounded-full px-[13px] py-1.5 transition-colors border-[1.5px] {active
				? 'border-primary/55 bg-primary/10'
				: 'border-transparent hover:bg-base-300/30'}"
			on:click={() => onSelect(r.id)}
		>
			<span
				class="flex items-center gap-1.5 font-display text-[13px] leading-tight {active
					? 'text-base-content'
					: 'text-base-content/70'}"
			>
				{#if liveRounds.has(r.id)}
					<span
						class="h-[7px] w-[7px] rounded-full bg-error animate-pulse-soft"
						title="Match in progress"
					></span>
				{/if}
				{r.label}
			</span>
			<span
				class="text-[10px] font-bold tracking-[0.04em] {active
					? 'text-primary'
					: 'text-base-content/55'}">{r.dates}</span
			>
		</button>
	{/each}
</div>
