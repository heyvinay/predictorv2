<script lang="ts">
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { displayTeamName } from '$lib/utils/teamName';
	import { getPredictionResult } from '$lib/utils/predictionResult';
	import { getCommunityPredictions } from '$api/predictions';
	import ScatterPlot from './ScatterPlot.svelte';
	import type { Fixture, MatchPrediction, CommunityPredictionsResponse } from '$types';

	export let fixture: Fixture;
	export let prediction: MatchPrediction | undefined = undefined;

	$: result = getPredictionResult(fixture, prediction);

	// Accordion state
	let expanded = false;
	let communityData: CommunityPredictionsResponse | null = null;
	let loading = false;
	let error: string | null = null;

	async function toggle() {
		expanded = !expanded;
		// Lazy-load community data on first expand
		if (expanded && !communityData && !loading) {
			loading = true;
			error = null;
			try {
				communityData = await getCommunityPredictions(fixture.id);
			} catch (e) {
				error = e instanceof Error ? e.message : 'Failed to load predictions';
			} finally {
				loading = false;
			}
		}
	}

	function formatDate(kickoff: string): string {
		return new Date(kickoff).toLocaleDateString('en-GB', {
			day: 'numeric',
			month: 'short',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function getResultLabel(): string {
		if (result === 'exact') return 'Exact Score';
		if (result === 'outcome') return 'Correct Result';
		if (result === 'wrong') return 'Wrong';
		return '';
	}
</script>

<div
	class="stadium-card no-glow overflow-hidden {result === 'exact' ? 'ring-1 ring-success/50' : ''} {result === 'outcome' ? 'ring-1 ring-warning/50' : ''} {result === 'wrong' ? 'ring-1 ring-error/50' : ''}"
>
	<!-- Main row (clickable) -->
	<button class="w-full p-4 text-left" on:click={toggle}>
		<div class="flex items-center gap-3">
			<!-- Date -->
			<div class="text-xs text-base-content/40 w-20 shrink-0">
				{formatDate(fixture.kickoff)}
			</div>

			<!-- Teams + Score -->
			<div class="flex-1 min-w-0">
				<div class="flex items-center gap-2">
					{#if hasFlag(fixture.home_team)}
						<img src={getFlagUrl(fixture.home_team, 'sm')} alt="" class="w-5 h-auto rounded-sm" style="aspect-ratio: 4 / 3" />
					{/if}
					<span class="font-semibold text-sm truncate">{displayTeamName(fixture.home_team)}</span>
					{#if fixture.score}
						<span class="font-display text-lg tracking-wide mx-1">
							{fixture.score.home_score} - {fixture.score.away_score}
						</span>
					{/if}
					<span class="font-semibold text-sm truncate">{displayTeamName(fixture.away_team)}</span>
					{#if hasFlag(fixture.away_team)}
						<img src={getFlagUrl(fixture.away_team, 'sm')} alt="" class="w-5 h-auto rounded-sm" style="aspect-ratio: 4 / 3" />
					{/if}
				</div>
				{#if prediction}
					<div class="text-xs text-base-content/50 mt-1">
						Your prediction: {prediction.home_score} - {prediction.away_score}
					</div>
				{:else}
					<div class="text-xs text-base-content/30 mt-1">No prediction</div>
				{/if}
			</div>

			<!-- Result badge -->
			{#if result !== 'pending'}
				<span class="result-badge {result} shrink-0">
					{getResultLabel()}
				</span>
			{/if}

			<!-- Expand arrow -->
			<svg
				class="w-4 h-4 text-base-content/30 transition-transform shrink-0 {expanded ? 'rotate-180' : ''}"
				fill="none"
				viewBox="0 0 24 24"
				stroke="currentColor"
			>
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
			</svg>
		</div>
	</button>

	<!-- Expanded: Scatter Plot -->
	{#if expanded}
		<div class="border-t border-base-300/30 p-4 bg-base-300/10">
			{#if loading}
				<div class="flex justify-center py-8">
					<span class="loading loading-spinner loading-md text-primary"></span>
				</div>
			{:else if error}
				<div class="text-center py-4 text-error text-sm">{error}</div>
			{:else if communityData}
				<div class="mb-3 text-center">
					<span class="text-xs text-base-content/50">
						{communityData.predictions.length} predictions
					</span>
				</div>
				<ScatterPlot
					predictions={communityData.predictions}
					actual={communityData.actual}
					homeTeam={fixture.home_team}
					awayTeam={fixture.away_team}
					userPrediction={prediction ? { home_score: prediction.home_score, away_score: prediction.away_score } : null}
				/>
				<!-- Legend -->
				<div class="flex items-center justify-center gap-4 mt-3 text-[10px] text-base-content/40">
					{#if communityData.actual}
						<div class="flex items-center gap-1">
							<span class="w-2.5 h-2.5 bg-success" style="clip-path: polygon(50% 0%, 61% 35%, 98% 35%, 68% 57%, 79% 91%, 50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%);"></span>
							Exact
						</div>
						<div class="flex items-center gap-1">
							<span class="w-2.5 h-2.5 rounded-full bg-warning"></span>
							Correct
						</div>
						<div class="flex items-center gap-1">
							<span class="w-2.5 h-2.5 rounded-full bg-error/70"></span>
							Wrong
						</div>
					{:else}
						<div class="flex items-center gap-1">
							<span class="w-2.5 h-2.5 rounded-full bg-base-content/40"></span>
							Predictions
						</div>
					{/if}
				</div>
				<div class="text-center mt-1.5 text-[9px] text-base-content/30">
					Numbers show how many players predicted each score
				</div>
			{/if}
		</div>
	{/if}
</div>
