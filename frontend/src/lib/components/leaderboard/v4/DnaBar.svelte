<script lang="ts">
	/** Stacked points-DNA bar: Exact / Result / Rarity / Bracket (split by
	 *  knockout round) / Bonus.
	 *  Token mapping: success / amber-400 / primary-striped / blue ramp /
	 *  violet. Result uses Tailwind amber-400 directly — the `warning` theme
	 *  token is a surface fill (#221703 deep brown), invisible as a chart bar.
	 *  Rarity uses a diagonal stripe of champagne gold over deep bronze to
	 *  (a) differentiate from the adjacent solid amber Result band and (b)
	 *  carry the "bonus / special" semantic.
	 *  The bracket is one blue segment per round, light → dark as the rounds
	 *  advance (R32 → winner) — the ramp itself encodes how deep into the
	 *  bracket the points were earned. Bonus is a distinct violet so it never
	 *  reads as part of the bracket ramp. */
	import type { DnaSplit } from '$lib/types/leaderboard';

	export let split: DnaSplit;
	/** When true (wrap-up Points DNA tile), render each segment's own raw
	 *  point value centered inside it, and grow the bar so the labels have
	 *  room to sit legibly. Segments too narrow for a legible label are left
	 *  blank rather than clipped/overflowing. Defaults to false — every
	 *  existing caller (InsightsGrid) omits this prop and renders the
	 *  original label-less bar unchanged. */
	export let labels = false;

	$: bracketTotal =
		split.roundOf32 +
		split.roundOf16 +
		split.quarterFinal +
		split.semiFinal +
		split.final +
		split.winner;
	$: total = split.exact + split.result + split.rarity + bracketTotal + split.bonus;
	$: pct = (v: number) => (total > 0 ? (v / total) * 100 : 0);

	// Segments narrower than this can't legibly fit a centered number at this
	// font size — hide the label rather than clip or overflow it.
	const MIN_LABEL_PCT = 8;
	function fmt(v: number): string {
		return v > 0 ? String(Math.round(v * 10) / 10) : '';
	}
</script>

<span class="flex w-full overflow-hidden rounded-full bg-base-300/40 {labels ? 'h-4' : 'h-2.5'}">
	{#if total > 0}
		<span class="block {labels ? 'relative flex items-center justify-center' : ''} bg-success" style="width:{pct(split.exact)}%">
			{#if labels && pct(split.exact) >= MIN_LABEL_PCT}<span class="font-display text-[10px] font-extrabold text-base-100">{fmt(split.exact)}</span>{/if}
		</span>
		<span class="block {labels ? 'relative flex items-center justify-center' : ''} bg-amber-400" style="width:{pct(split.result)}%">
			{#if labels && pct(split.result) >= MIN_LABEL_PCT}<span class="font-display text-[10px] font-extrabold text-base-100">{fmt(split.result)}</span>{/if}
		</span>
		<span
			class="block {labels ? 'relative flex items-center justify-center' : ''} bg-[repeating-linear-gradient(135deg,#D4AF37_0_3px,#7C5E1D_3px_6px)]"
			style="width:{pct(split.rarity)}%"
		>
			{#if labels && pct(split.rarity) >= MIN_LABEL_PCT}<span class="font-display text-[10px] font-extrabold text-base-100">{fmt(split.rarity)}</span>{/if}
		</span>
		<span class="block {labels ? 'relative flex items-center justify-center' : ''} bg-[#93C5FD]" style="width:{pct(split.roundOf32)}%">
			{#if labels && pct(split.roundOf32) >= MIN_LABEL_PCT}<span class="font-display text-[10px] font-extrabold text-base-100">{fmt(split.roundOf32)}</span>{/if}
		</span>
		<span class="block {labels ? 'relative flex items-center justify-center' : ''} bg-[#60A5FA]" style="width:{pct(split.roundOf16)}%">
			{#if labels && pct(split.roundOf16) >= MIN_LABEL_PCT}<span class="font-display text-[10px] font-extrabold text-base-100">{fmt(split.roundOf16)}</span>{/if}
		</span>
		<span class="block {labels ? 'relative flex items-center justify-center' : ''} bg-[#3B82F6]" style="width:{pct(split.quarterFinal)}%">
			{#if labels && pct(split.quarterFinal) >= MIN_LABEL_PCT}<span class="font-display text-[10px] font-extrabold text-base-100">{fmt(split.quarterFinal)}</span>{/if}
		</span>
		<span class="block {labels ? 'relative flex items-center justify-center' : ''} bg-[#2563EB]" style="width:{pct(split.semiFinal)}%">
			{#if labels && pct(split.semiFinal) >= MIN_LABEL_PCT}<span class="font-display text-[10px] font-extrabold text-base-100">{fmt(split.semiFinal)}</span>{/if}
		</span>
		<span class="block {labels ? 'relative flex items-center justify-center' : ''} bg-[#1D4ED8]" style="width:{pct(split.final)}%">
			{#if labels && pct(split.final) >= MIN_LABEL_PCT}<span class="font-display text-[10px] font-extrabold text-base-100">{fmt(split.final)}</span>{/if}
		</span>
		<span class="block {labels ? 'relative flex items-center justify-center' : ''} bg-[#1E3A8A]" style="width:{pct(split.winner)}%">
			{#if labels && pct(split.winner) >= MIN_LABEL_PCT}<span class="font-display text-[10px] font-extrabold text-base-100">{fmt(split.winner)}</span>{/if}
		</span>
		<span class="block {labels ? 'relative flex items-center justify-center' : ''} bg-[#8B5CF6]" style="width:{pct(split.bonus)}%">
			{#if labels && pct(split.bonus) >= MIN_LABEL_PCT}<span class="font-display text-[10px] font-extrabold text-base-100">{fmt(split.bonus)}</span>{/if}
		</span>
	{/if}
</span>
