<script lang="ts">
	/** Pool advancement vote for a knockout fixture.
	 *
	 *  Two-team split (instead of the group-stage home/draw/away three-way)
	 *  plus an Atlas / JMFA / Guests cohort row that mirrors the leaderboard's
	 *  pool filter — a viewer can see how their tribe leans. */
	import type { Fixture } from '$types';
	import type { KoMatchDetailResponse } from '$lib/types/results';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import TeamName from '$lib/components/TeamName.svelte';

	export let fixture: Fixture;
	export let bundle: KoMatchDetailResponse;

	$: split = bundle.pool_split;

	function pctOf(part: number, total: number): number {
		if (total <= 0) return 0;
		return Math.round((100 * part) / total);
	}
</script>

<div class="rounded-box border border-base-300/60 bg-base-200 p-4">
	<div class="mb-3 flex items-center justify-between">
		<span class="font-display text-[15px]">The pool's bet</span>
		<span class="text-[11px] text-base-content/55"
			>{split.total}
			{split.total === 1 ? 'entry' : 'entries'} · advancement</span
		>
	</div>

	<!-- Home side -->
	<div class="mb-2">
		<div class="mb-1 flex items-center justify-between text-[12.5px]">
			<span class="inline-flex items-center gap-1.5 font-semibold">
				{#if hasFlag(split.home.team)}
					<img src={getFlagUrl(split.home.team, 'sm')} alt="" class="h-3 w-[18px] rounded-sm" style="aspect-ratio: 4 / 3" />
				{/if}
				<TeamName name={split.home.team} />
			</span>
			<span class="font-mono text-[11.5px] text-base-content/65"
				>{split.home.count} ({split.home.pct}%)</span
			>
		</div>
		<div class="h-3 overflow-hidden rounded-full bg-base-300/30">
			<div
				class="h-full rounded-full bg-amber-400"
				style="width: {Math.max(split.home.pct, 1.5)}%;"
			></div>
		</div>
	</div>

	<!-- Away side -->
	<div class="mb-3">
		<div class="mb-1 flex items-center justify-between text-[12.5px]">
			<span class="inline-flex items-center gap-1.5 font-semibold">
				{#if hasFlag(split.away.team)}
					<img src={getFlagUrl(split.away.team, 'sm')} alt="" class="h-3 w-[18px] rounded-sm" style="aspect-ratio: 4 / 3" />
				{/if}
				<TeamName name={split.away.team} />
			</span>
			<span class="font-mono text-[11.5px] text-base-content/65"
				>{split.away.count} ({split.away.pct}%)</span
			>
		</div>
		<div class="h-3 overflow-hidden rounded-full bg-base-300/30">
			<div
				class="h-full rounded-full bg-emerald-400"
				style="width: {Math.max(split.away.pct, 1.5)}%;"
			></div>
		</div>
	</div>

	<!-- Cohort breakdown -->
	{#if split.total > 0}
		<div class="mt-3 grid grid-cols-3 gap-2 border-t border-base-300/40 pt-3 text-[11px]">
			{#each [{ name: 'Atlas', h: split.home.cohorts.atlas, a: split.away.cohorts.atlas }, { name: 'JMFA', h: split.home.cohorts.jmfa, a: split.away.cohorts.jmfa }, { name: 'Guests', h: split.home.cohorts.guests, a: split.away.cohorts.guests }] as cohort}
				{@const cohortTotal = cohort.h + cohort.a}
				<div class="rounded-btn bg-base-300/20 px-2 py-1.5">
					<div class="mb-0.5 text-[9.5px] font-bold uppercase tracking-[0.1em] text-base-content/55">
						{cohort.name}
					</div>
					<div class="font-mono text-[10.5px] text-base-content/80">
						<span class="font-bold text-amber-400">{pctOf(cohort.h, cohortTotal)}%</span>
						<span class="text-base-content/40">/</span>
						<span class="font-bold text-emerald-400">{pctOf(cohort.a, cohortTotal)}%</span>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>
