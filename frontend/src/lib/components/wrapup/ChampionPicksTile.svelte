<script lang="ts">
	import FlagCode from '$lib/components/leaderboard/v4/FlagCode.svelte';
	import type { ChampionPickOut } from '$lib/types/wrapup';

	export let picks: ChampionPickOut[];
	/** Whole-pool entry count — percentages are of the full pool, not just
	 *  the picks shown here (this list is capped to the top 5). */
	export let poolSize: number;

	$: max = Math.max(1, ...picks.map((p) => p.count));
	$: actualCount = picks.find((p) => p.is_actual)?.count ?? 0;
	$: pct = (count: number) => (poolSize > 0 ? Math.round((count / poolSize) * 100) : 0);
</script>

<div class="stadium-card no-glow h-full p-4">
	<h2 class="font-display text-[15px] font-extrabold">Who picked whom — champion</h2>
	<p class="mb-2 text-xs text-base-content/50">Where the pool placed its title faith before a ball was kicked.</p>
	{#each picks as p (p.team)}
		<div class="mt-1.5 grid grid-cols-[92px_1fr_64px] items-center gap-2 text-[13px]">
			<span class="flex min-w-0 items-center gap-1 truncate {p.is_actual ? 'font-bold text-primary' : ''}">
				<FlagCode team={p.team} size="sm" />
				{p.is_actual ? '✓' : ''}
			</span>
			<div class="h-2.5 overflow-hidden rounded-full bg-base-300/60">
				<div class="h-full rounded-full {p.is_actual ? 'bg-primary' : 'bg-base-content/25'}" style={`width:${(p.count / max) * 100}%`}></div>
			</div>
			<span class="text-right text-xs tabular-nums text-base-content/55"
				>{p.count} <span class="text-base-content/40">({pct(p.count)}%)</span></span
			>
		</div>
	{/each}
	<p class="mt-2 text-[11px] text-base-content/40">{actualCount} entries backed the actual champion.</p>
</div>
