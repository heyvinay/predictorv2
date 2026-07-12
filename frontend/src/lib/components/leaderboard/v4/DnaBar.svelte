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

	$: bracketTotal =
		split.roundOf32 +
		split.roundOf16 +
		split.quarterFinal +
		split.semiFinal +
		split.final +
		split.winner;
	$: total = split.exact + split.result + split.rarity + bracketTotal + split.bonus;
	$: pct = (v: number) => (total > 0 ? (v / total) * 100 : 0);
</script>

<span class="flex h-2.5 w-full overflow-hidden rounded-full bg-base-300/40">
	{#if total > 0}
		<span class="block bg-success" style="width:{pct(split.exact)}%"></span>
		<span class="block bg-amber-400" style="width:{pct(split.result)}%"></span>
		<span
			class="block bg-[repeating-linear-gradient(135deg,#D4AF37_0_3px,#7C5E1D_3px_6px)]"
			style="width:{pct(split.rarity)}%"
		></span>
		<span class="block bg-[#93C5FD]" style="width:{pct(split.roundOf32)}%"></span>
		<span class="block bg-[#60A5FA]" style="width:{pct(split.roundOf16)}%"></span>
		<span class="block bg-[#3B82F6]" style="width:{pct(split.quarterFinal)}%"></span>
		<span class="block bg-[#2563EB]" style="width:{pct(split.semiFinal)}%"></span>
		<span class="block bg-[#1D4ED8]" style="width:{pct(split.final)}%"></span>
		<span class="block bg-[#1E3A8A]" style="width:{pct(split.winner)}%"></span>
		<span class="block bg-[#8B5CF6]" style="width:{pct(split.bonus)}%"></span>
	{/if}
</span>
