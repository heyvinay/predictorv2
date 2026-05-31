<script lang="ts">
	import type { Fixture, MatchPrediction } from '$types';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { displayTeamName } from '$lib/utils/teamName';
	import { calculateGroupStandings } from '$lib/utils/standings';

	export let group: string;
	export let fixtures: Fixture[];
	export let predictions: Map<string, MatchPrediction>;
	/** Optional in-table heading. Defaults to "Group {X} — Standings". */
	export let title: string | null = null;

	$: standings = calculateGroupStandings(fixtures, predictions, group);
	$: resolvedTitle = title ?? `Group ${group} — Standings`;

	// Position indicator styling
	function getPositionClass(index: number): string {
		if (index < 2) return 'qualifies';
		if (index === 2) return 'third-place';
		return 'eliminated';
	}
</script>

<div class="group-standings">
	<div class="overflow-x-auto -mx-2 sm:mx-0">
		<table class="standings-table">
			<thead>
				<tr>
					<th
						colspan="10"
						class="text-left text-xs font-medium text-base-content/60 uppercase tracking-wider py-2 px-2"
					>
						{resolvedTitle}
					</th>
				</tr>
				<tr>
					<th class="w-8 text-center">#</th>
					<th class="text-left">Team</th>
					<th class="text-center w-8">P</th>
					<th class="text-center w-8">W</th>
					<th class="text-center w-8">D</th>
					<th class="text-center w-8">L</th>
					<th class="text-center w-10 hidden sm:table-cell">GF</th>
					<th class="text-center w-10 hidden sm:table-cell">GA</th>
					<th class="text-center w-10">GD</th>
					<th class="text-center w-10">Pts</th>
				</tr>
			</thead>
			<tbody>
				{#each standings as standing, i}
					{@const posClass = getPositionClass(i)}
					<tr class="standing-row {posClass} animate-fade-in" style="animation-delay: {i * 50}ms; animation-fill-mode: both;">
						<td class="text-center">
							<span class="position-indicator {posClass}">
								{i + 1}
							</span>
						</td>
						<td class="team-cell">
							<div class="flex items-center gap-2">
								{#if hasFlag(standing.team)}
									<img
										src={getFlagUrl(standing.team, 'sm')}
										alt="{standing.team} flag"
										class="w-5 h-auto rounded-sm shadow-sm flex-shrink-0"
										loading="lazy"
									/>
								{:else}
									<div class="w-5 h-3.5 bg-base-300 rounded-sm flex-shrink-0"></div>
								{/if}
								<span class="team-name-table">{displayTeamName(standing.team)}</span>
							</div>
						</td>
						<td class="text-center text-base-content/70">{standing.played}</td>
						<td class="text-center text-success font-medium">{standing.won}</td>
						<td class="text-center text-base-content/50">{standing.drawn}</td>
						<td class="text-center text-error/80">{standing.lost}</td>
						<td class="text-center text-base-content/70 hidden sm:table-cell">{standing.goalsFor}</td>
						<td class="text-center text-base-content/70 hidden sm:table-cell">{standing.goalsAgainst}</td>
						<td class="text-center gd-cell {standing.goalDifference > 0 ? 'positive' : standing.goalDifference < 0 ? 'negative' : ''}">
							{standing.goalDifference > 0 ? '+' : ''}{standing.goalDifference}
						</td>
						<td class="text-center">
							<span class="points-badge">{standing.points}</span>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

</div>

<style>
	/* Qualification indicators - context-specific colors (shared base styles in app.css) */
	.standing-row.qualifies {
		@apply border-l-2 border-l-success;
	}

	.standing-row.third-place {
		@apply border-l-2 border-l-warning;
	}

	.standing-row.eliminated {
		@apply border-l-2 border-l-error;
	}

	.position-indicator.qualifies {
		@apply bg-success/20 text-success;
	}

	.position-indicator.third-place {
		@apply bg-warning/20 text-warning-text;
	}

	.position-indicator.eliminated {
		@apply bg-error/20 text-error;
	}
</style>
