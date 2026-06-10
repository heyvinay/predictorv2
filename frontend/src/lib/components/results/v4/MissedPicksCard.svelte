<script lang="ts">
	/** R32 bracket picks that bombed out in the group stage. Pills carry
	 *  flag + name only (spec F.1 — no reason chip). The unrealised value
	 *  templates from stage points (C.1). */
	import { displayTeamName } from '$lib/utils/teamName';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';

	export let roundLabel: string;
	export let teams: string[];
	export let stagePoints: number;
</script>

<div class="mt-4 rounded-box border border-dashed border-error/50 bg-error/5 p-4">
	<div class="flex items-start gap-3">
		<div
			class="grid h-7 w-7 flex-none place-items-center rounded-full bg-error/20 text-[13px] font-bold text-error"
		>
			✗
		</div>
		<div>
			<div class="text-[13px] font-bold">{roundLabel} picks that didn't make it</div>
			<div class="text-[11.5px] text-base-content/55">
				{teams.length} of your bracket picks were knocked out in the group stage
				<span class="ml-1.5 text-error">· –{teams.length * stagePoints} unrealised</span>
			</div>
		</div>
	</div>
	<div class="mt-3 flex flex-wrap gap-2">
		{#each teams as team (team)}
			<span
				class="inline-flex items-center gap-1.5 rounded-full border border-error/30 bg-base-200 px-2.5 py-1 text-[12px] font-semibold"
			>
				{#if hasFlag(team)}
					<img src={getFlagUrl(team, 'sm')} alt="" class="h-auto w-4 rounded-sm" />
				{/if}
				<span>{displayTeamName(team)}</span>
			</span>
		{/each}
	</div>
</div>
