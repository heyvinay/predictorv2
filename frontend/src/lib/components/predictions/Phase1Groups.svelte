<script lang="ts">
	import MatchCard from '$components/MatchCard.svelte';
	import GroupTable from '$components/GroupTable.svelte';
	import ThirdPlaceTable from '$components/ThirdPlaceTable.svelte';
	import type { FixturesByGroup, MatchPrediction } from '$types';
	import type { TeamStanding } from '$lib/utils/standings';

	export let groupFixtures: FixturesByGroup[];
	export let loading: boolean;
	export let predictionMap: Map<string, MatchPrediction>;
	export let livePredictionMap: Map<string, MatchPrediction>;
	export let thirdPlaceStandings: TeamStanding[];
</script>

{#if loading && groupFixtures.length === 0}
	<div class="flex justify-center py-16">
		<span class="loading loading-spinner loading-lg text-primary"></span>
	</div>
{:else if groupFixtures.length === 0}
	<div class="stadium-card p-8 text-center">
		<div class="text-6xl mb-4 opacity-30">
			<svg class="w-16 h-16 mx-auto text-base-content/20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
			</svg>
		</div>
		<p class="text-base-content/50">No group stage fixtures available yet.</p>
	</div>
{:else}
	<div class="space-y-8">
		{#each groupFixtures as group, groupIndex}
			<div class="stadium-card no-glow p-4 sm:p-6 animate-slide-up" style="animation-delay: {groupIndex * 50}ms; animation-fill-mode: both;">
				<!-- Group Header -->
				<div class="flex items-center gap-3 mb-5">
					<div class="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
						<span class="text-lg font-display text-primary">{group.group}</span>
					</div>
					<div>
						<h2 class="text-lg font-display tracking-wide">Group {group.group}</h2>
						<p class="text-xs text-base-content/50">{group.fixtures.length} matches</p>
					</div>
				</div>

				<!-- Predicted Standings Table — title is rendered inside the
				     table's thead, so no external heading is needed. -->
				<div class="mb-6">
					<GroupTable
						group={group.group}
						fixtures={group.fixtures}
						predictions={livePredictionMap}
					/>
				</div>

				<!-- Match Predictions -->
				<div>
					<div class="flex items-center gap-2 mb-3">
						<svg class="w-4 h-4 text-base-content/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
						</svg>
						<h3 class="text-xs font-medium text-base-content/50 uppercase tracking-wider">Match Predictions</h3>
					</div>
					<div class="match-grid">
						{#each group.fixtures as fixture}
							<MatchCard
								{fixture}
								prediction={predictionMap.get(fixture.id)}
							/>
						{/each}
					</div>
				</div>
			</div>
		{/each}

		<!-- Third Place Table -->
		<div class="stadium-card no-glow p-4 sm:p-6 animate-slide-up" style="animation-delay: 600ms; animation-fill-mode: both;">
			<div class="flex items-center gap-3 mb-5">
				<div class="w-10 h-10 rounded-xl bg-warning/10 flex items-center justify-center">
					<span class="text-lg font-display text-warning-text">3rd</span>
				</div>
				<div>
					<h2 class="text-lg font-display tracking-wide">Ranking of 3rd Place Teams</h2>
					<p class="text-xs text-base-content/50">Top 8 advance to Round of 32</p>
				</div>
			</div>
			<ThirdPlaceTable standings={thirdPlaceStandings} />
		</div>
	</div>
{/if}
