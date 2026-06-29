<script lang="ts">
	/** Winners of this round's finished fixtures, split by membership in
	 *  the entry's NEXT-round bracket. Locked-in value templates from the
	 *  NEXT stage's points (C.1). Tightened to match RoundPicksCard's
	 *  compact treatment (v2.184.x): same paddings, type scale, pill
	 *  geometry, and compactCodes convention so the two cards bracket
	 *  the KO tab with consistent density. */
	import { teamCode } from '$lib/utils/teamCodes';
	import { displayTeamName } from '$lib/utils/teamName';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';

	export let nextLabel: string;
	export let inNext: string[];
	export let notInNext: string[];
	export let nextStagePoints: number;
	/** True for R32/R16 → use 3-letter FIFA codes; false for QF/SF/F →
	 *  simplified names. Matches RoundPicksCard's pill convention. */
	export let compactCodes: boolean = false;

	$: banked = inNext.length * nextStagePoints;
	$: totalWinners = inNext.length + notInNext.length;

	function pillLabel(team: string): string {
		return compactCodes ? teamCode(team) : displayTeamName(team);
	}
</script>

<div class="mt-3 rounded-box border border-success/40 bg-success/5 p-3">
	<!-- Header: progression title + summary stats (compact, no icon) -->
	<div class="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
		<div class="text-[12.5px] font-bold">
			Progressing to <span class="text-success">{nextLabel}</span>
		</div>
		<div class="font-mono text-[10.5px] tabular-nums text-base-content/55">
			<strong class="text-base-content">{inNext.length}</strong>/{totalWinners} winners in your
			bracket
			{#if banked > 0}
				<span class="ml-1 font-bold text-success">· locks +{banked}</span>
			{/if}
		</div>
	</div>

	<!-- Pills row -->
	<div class="flex flex-wrap gap-1.5">
		{#each inNext as team (team)}
			<span
				class="inline-flex items-center gap-1 rounded-full border border-success/40 bg-base-300/20 px-2 py-0.5 text-[11px] font-semibold"
			>
				{#if hasFlag(team)}
					<img
						src={getFlagUrl(team, 'sm')}
						alt=""
						class="h-auto w-3.5 rounded-sm"
						style="aspect-ratio: 4 / 3"
					/>
				{/if}
				<span>{pillLabel(team)}</span>
				<span
					class="rounded-badge bg-success/15 px-1 text-[9px] font-bold text-success"
					aria-label="locks in points">+{nextStagePoints}</span
				>
			</span>
		{/each}
		{#each notInNext as team (team)}
			<span
				class="inline-flex items-center gap-1 rounded-full border border-base-300/60 bg-base-300/20 px-2 py-0.5 text-[11px] font-semibold opacity-65"
			>
				{#if hasFlag(team)}
					<img
						src={getFlagUrl(team, 'sm')}
						alt=""
						class="h-auto w-3.5 rounded-sm"
						style="aspect-ratio: 4 / 3"
					/>
				{/if}
				<span>{pillLabel(team)}</span>
				<span
					class="rounded-badge bg-base-300/30 px-1 text-[9px] font-bold text-base-content/45"
					aria-label="not in your bracket">—</span
				>
			</span>
		{/each}
	</div>
</div>
