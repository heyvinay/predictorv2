<script lang="ts">
	/** Stacked points-DNA bar: Exact / Result / Rarity / Bracket(+bonus).
	 *  Token mapping: success / amber-400 / primary / info.
	 *  Result uses Tailwind amber-400 directly — the `warning` theme token is
	 *  a surface fill (#221703 deep brown), invisible as a chart bar. */
	import type { DnaSplit } from '$lib/types/leaderboard';

	export let split: DnaSplit;

	$: bracketAndBonus = split.bracket + split.bonus;
	$: total = split.exact + split.result + split.rarity + bracketAndBonus;
	$: pct = (v: number) => (total > 0 ? (v / total) * 100 : 0);
</script>

<span class="flex h-2.5 w-full overflow-hidden rounded-full bg-base-300/40">
	{#if total > 0}
		<span class="block bg-success" style="width:{pct(split.exact)}%"></span>
		<span class="block bg-amber-400" style="width:{pct(split.result)}%"></span>
		<span class="block bg-primary" style="width:{pct(split.rarity)}%"></span>
		<span class="block bg-info" style="width:{pct(bracketAndBonus)}%"></span>
	{/if}
</span>
