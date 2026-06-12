<script lang="ts">
	/** Winners of this round's finished fixtures, split by membership in
	 *  the entry's NEXT-round bracket. Locked-in value templates from the
	 *  NEXT stage's points (C.1). */
	import { displayTeamName } from '$lib/utils/teamName';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';

	export let nextLabel: string;
	export let inNext: string[];
	export let notInNext: string[];
	export let nextStagePoints: number;

	$: banked = inNext.length * nextStagePoints;
	$: totalWinners = inNext.length + notInNext.length;
</script>

<div class="mt-4 rounded-box border border-success/40 bg-success/5 p-4">
	<div class="flex items-start gap-3">
		<div
			class="grid h-7 w-7 flex-none place-items-center rounded-full bg-success/20 text-[13px] font-bold text-success"
		>
			→
		</div>
		<div>
			<div class="text-[13px] font-bold">Progressing to {nextLabel}</div>
			<div class="text-[11.5px] text-base-content/55">
				<b class="text-success">{inNext.length}</b> of {totalWinners} fixture winners are in your
				{nextLabel} bracket
				<span class="ml-1.5 text-success">· locks in +{banked} on the {nextLabel} page</span>
			</div>
		</div>
	</div>
	<div class="mt-3 flex flex-wrap gap-2">
		{#each inNext as team (team)}
			<span
				class="inline-flex items-center gap-1.5 rounded-full border border-success/40 bg-base-200 px-2.5 py-1 text-[12px] font-semibold"
			>
				{#if hasFlag(team)}
					<img src={getFlagUrl(team, 'sm')} alt="" class="h-auto w-4 rounded-sm" style="aspect-ratio: 4 / 3" />
				{/if}
				<span>{displayTeamName(team)}</span>
				<span class="rounded-badge bg-success/20 px-1.5 text-[10px] font-bold text-success"
					>+{nextStagePoints}</span
				>
			</span>
		{/each}
		{#each notInNext as team (team)}
			<span
				class="inline-flex items-center gap-1.5 rounded-full border border-base-300/60 bg-base-200 px-2.5 py-1 text-[12px] font-semibold opacity-70"
			>
				{#if hasFlag(team)}
					<img src={getFlagUrl(team, 'sm')} alt="" class="h-auto w-4 rounded-sm" style="aspect-ratio: 4 / 3" />
				{/if}
				<span>{displayTeamName(team)}</span>
				<span class="rounded-badge bg-base-300/40 px-1.5 text-[10px] font-bold text-base-content/55"
					>not picked</span
				>
			</span>
		{/each}
	</div>
</div>
