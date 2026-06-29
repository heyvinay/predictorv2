<script lang="ts">
	/** Pool advancement vote for a knockout fixture.
	 *
	 *  Two-team split (home vs away advancement). Pool-wide only — cohort
	 *  breakdown (Atlas / JMFA / Guests) was removed v2.184.x; viewers found
	 *  the tribe-level slicing distracting on a per-fixture page. The bundle
	 *  still carries the cohort counts in case a future surface wants them. */
	import type { Fixture } from '$types';
	import type { KoMatchDetailResponse } from '$lib/types/results';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import TeamName from '$lib/components/TeamName.svelte';

	export let fixture: Fixture;
	export let bundle: KoMatchDetailResponse;

	$: split = bundle.pool_split;
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

</div>
