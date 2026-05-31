<script lang="ts">
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { displayTeamName } from '$lib/utils/teamName';
	import type { UserMatchPredictionView } from '$types';

	export let predictions: UserMatchPredictionView[];

	function formatDate(kickoff: string): string {
		return new Date(kickoff).toLocaleDateString('en-GB', {
			day: 'numeric',
			month: 'short'
		});
	}

	function getRowClass(pred: UserMatchPredictionView): string {
		if (pred.status !== 'finished' || pred.actual_home === null) return '';
		if (pred.is_exact) return 'bg-success/10';
		if (pred.is_correct_outcome) return 'bg-warning/10';
		return 'bg-error/5';
	}

	function getResultText(pred: UserMatchPredictionView): string {
		if (pred.status !== 'finished' || pred.actual_home === null) return '';
		if (pred.is_exact) return 'Exact';
		if (pred.is_correct_outcome) return 'Correct';
		return 'Wrong';
	}

	function getResultClass(pred: UserMatchPredictionView): string {
		if (pred.is_exact) return 'text-success';
		if (pred.is_correct_outcome) return 'text-warning-text';
		return 'text-error/70';
	}
</script>

<!-- Desktop table (hidden on small screens) -->
<div class="hidden sm:block overflow-x-auto">
	<table class="w-full">
		<thead>
			<tr class="border-b border-base-300/50">
				<th class="text-left py-3 px-3 text-[10px] uppercase tracking-wider text-base-content/40 font-normal">Date</th>
				<th class="text-left py-3 px-3 text-[10px] uppercase tracking-wider text-base-content/40 font-normal">Match</th>
				<th class="text-center py-3 px-3 text-[10px] uppercase tracking-wider text-base-content/40 font-normal">Prediction</th>
				<th class="text-center py-3 px-3 text-[10px] uppercase tracking-wider text-base-content/40 font-normal">Actual</th>
				<th class="text-center py-3 px-3 text-[10px] uppercase tracking-wider text-base-content/40 font-normal">Result</th>
			</tr>
		</thead>
		<tbody>
			{#each predictions as pred}
				<tr class="border-b border-base-300/20 transition-colors {getRowClass(pred)}">
					<td class="py-2.5 px-3 text-xs text-base-content/50">{formatDate(pred.kickoff)}</td>
					<td class="py-2.5 px-3">
						<div class="flex items-center gap-1.5 text-sm">
							{#if hasFlag(pred.home_team)}
								<img src={getFlagUrl(pred.home_team, 'sm')} alt="" class="w-4 h-auto rounded-sm" />
							{/if}
							<span class="font-medium truncate max-w-[80px]">{displayTeamName(pred.home_team)}</span>
							<span class="text-base-content/30">vs</span>
							<span class="font-medium truncate max-w-[80px]">{displayTeamName(pred.away_team)}</span>
							{#if hasFlag(pred.away_team)}
								<img src={getFlagUrl(pred.away_team, 'sm')} alt="" class="w-4 h-auto rounded-sm" />
							{/if}
						</div>
					</td>
					<td class="py-2.5 px-3 text-center font-display text-lg tracking-wide">
						{pred.predicted_home} - {pred.predicted_away}
					</td>
					<td class="py-2.5 px-3 text-center font-display text-lg tracking-wide">
						{#if pred.actual_home !== null}
							{pred.actual_home} - {pred.actual_away}
						{:else}
							<span class="text-base-content/30">-</span>
						{/if}
					</td>
					<td class="py-2.5 px-3 text-center">
						{#if pred.status === 'finished' && pred.actual_home !== null}
							<span class="text-xs font-semibold {getResultClass(pred)}">{getResultText(pred)}</span>
						{:else}
							<span class="text-xs text-base-content/30">Pending</span>
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<!-- Mobile stacked cards (visible on small screens) -->
<div class="sm:hidden space-y-2">
	{#each predictions as pred}
		<div class="rounded-xl p-3 border border-base-300/20 {getRowClass(pred)}">
			<div class="flex items-center justify-between mb-2">
				<span class="text-xs text-base-content/40">{formatDate(pred.kickoff)}</span>
				{#if pred.status === 'finished' && pred.actual_home !== null}
					<span class="text-xs font-semibold {getResultClass(pred)}">{getResultText(pred)}</span>
				{:else}
					<span class="text-xs text-base-content/30">Pending</span>
				{/if}
			</div>
			<div class="flex items-center justify-between">
				<div class="flex items-center gap-1.5 text-sm min-w-0">
					{#if hasFlag(pred.home_team)}
						<img src={getFlagUrl(pred.home_team, 'sm')} alt="" class="w-4 h-auto rounded-sm shrink-0" />
					{/if}
					<span class="font-medium truncate">{displayTeamName(pred.home_team)}</span>
					<span class="text-base-content/30 shrink-0">v</span>
					<span class="font-medium truncate">{displayTeamName(pred.away_team)}</span>
					{#if hasFlag(pred.away_team)}
						<img src={getFlagUrl(pred.away_team, 'sm')} alt="" class="w-4 h-auto rounded-sm shrink-0" />
					{/if}
				</div>
			</div>
			<div class="flex items-center gap-4 mt-2 text-xs">
				<div>
					<span class="text-base-content/40">Pred:</span>
					<span class="font-display text-base tracking-wide ml-1">{pred.predicted_home}-{pred.predicted_away}</span>
				</div>
				{#if pred.actual_home !== null}
					<div>
						<span class="text-base-content/40">Actual:</span>
						<span class="font-display text-base tracking-wide ml-1">{pred.actual_home}-{pred.actual_away}</span>
					</div>
				{/if}
			</div>
		</div>
	{/each}
</div>
