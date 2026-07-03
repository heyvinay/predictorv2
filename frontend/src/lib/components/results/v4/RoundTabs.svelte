<script lang="ts">
	/** Horizontal-scroll round tabs. Active = faint gold outline (NO glow).
	 *  A pulsing red dot marks rounds with a LIVE fixture; the same
	 *  roundsWithLive set drives the Summary rows (spec D.1b). On mount the
	 *  page pre-selects the live/default round and this component scrolls
	 *  it into view.
	 *
	 *  Compact labels (v2.194.x): after the Bracket tab landed there are 11
	 *  pills to fit horizontally, and "Round of 32"/"Quarter-Finals"/etc.
	 *  overflowed the strip on desktops that don't wrap; the standard
	 *  football shorthand ("R32", "QF") is what everything else in the app
	 *  already uses (round subtotals, KO card headers) and fits without
	 *  overflow. Kept local so other consumers of ROUND_LABELS in prose
	 *  contexts (panels, banners) still see the readable form. */
	import type { RoundDef, RoundId } from '$lib/types/results';

	export let rounds: RoundDef[];
	export let selected: RoundId;
	export let liveRounds: Set<RoundId>;
	export let onSelect: (id: RoundId) => void;

	const SHORT_LABEL: Record<RoundId, string> = {
		summary: 'Summary',
		r1: 'R1',
		r2: 'R2',
		r3: 'R3',
		groups: 'Groups',
		bracket: 'Bracket',
		r32: 'R32',
		r16: 'R16',
		qf: 'QF',
		sf: 'SF',
		f: 'Final',
		winner: 'Winner'
	};

	function labelOf(r: RoundDef): string {
		return SHORT_LABEL[r.id] ?? r.label;
	}

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
			class="relative flex min-w-fit flex-none flex-col items-center gap-0.5 whitespace-nowrap rounded-full px-2.5 py-1 transition-colors border-[1.5px] {active
				? 'border-primary/55 bg-primary/10'
				: 'border-transparent hover:bg-base-300/30'}"
			on:click={() => onSelect(r.id)}
		>
			<span
				class="flex items-center gap-1.5 font-display text-[12px] leading-tight {active
					? 'text-base-content'
					: 'text-base-content/70'}"
			>
				{#if liveRounds.has(r.id)}
					<span
						class="h-[6px] w-[6px] rounded-full bg-error animate-pulse-soft"
						role="img"
						aria-label="Round has a match in progress"
						title="Match in progress"
					></span>
				{/if}
				{labelOf(r)}
			</span>
			<span
				class="text-[9.5px] font-bold tracking-[0.04em] {active
					? 'text-primary'
					: 'text-base-content/55'}">{r.dates}</span
			>
		</button>
	{/each}
</div>
