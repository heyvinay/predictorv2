<script lang="ts">
	import type { Fixture, MatchPrediction } from '$types';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { displayTeamName } from '$lib/utils/teamName';
	import { calculateGroupStandings, type TeamStanding } from '$lib/utils/standings';
	import { entryPickSlotState, type PickSlotState } from '$lib/utils/groupTracker';

	export let group: string;
	/** Default empty so callers passing pre-computed standings (v2.181.1)
	 *  don't have to thread fixture/prediction inputs they won't use. */
	export let fixtures: Fixture[] = [];
	export let predictions: Map<string, MatchPrediction> = new Map();
	/** Optional in-table heading. Defaults to "Group {X} — Standings". */
	export let title: string | null = null;
	/** Pre-computed standings (v2.181.1). When provided, skips the
	 *  client-side calculation — used by the /standings page where the
	 *  backend has already applied FIFA tiebreakers from real match
	 *  data. Leave null in the prediction wizard to keep the predicted
	 *  standings recomputing reactively as the user edits scores. */
	export let standings: TeamStanding[] | null = null;

	/** Reality-check overlay (v2.19x) — the active entry's predicted
	 *  top-2 for this group. Null (default) renders the table exactly
	 *  as before; every existing caller is unaffected. */
	export let entryPredictedTop2: [string | undefined, string | undefined] | null = null;
	export let overlayOn = false;

	$: resolvedStandings = standings ?? calculateGroupStandings(fixtures, predictions, group);
	$: resolvedTitle = title ?? `Group ${group} — Standings`;
	$: showPickColumn = overlayOn && entryPredictedTop2 !== null;
	$: titleColspan = showPickColumn ? 11 : 10;

	// Position indicator styling
	function getPositionClass(index: number): string {
		if (index < 2) return 'qualifies';
		if (index === 2) return 'third-place';
		return 'eliminated';
	}

	const MARKER_LABEL: Record<Exclude<PickSlotState, null>, string> = {
		hit: '✓',
		swap: '↔',
		warn: '⚠',
		miss: '✕',
		up: '↑'
	};
	const MARKER_TITLE: Record<Exclude<PickSlotState, null>, string> = {
		hit: 'Your pick, right slot',
		swap: 'Your pick, wrong slot',
		warn: 'Your pick, on the best-3rd bubble',
		miss: 'Your pick, slipped out',
		up: "Surprise qualifier you didn't pick"
	};

	/** Template expressions aren't TypeScript even in a `lang="ts"` block —
	 *  the `as` cast has to happen here, not inline in a {@const}. */
	function markerFor(
		team: string,
		rank: number,
		top2: [string | undefined, string | undefined]
	): PickSlotState {
		return entryPickSlotState(team, rank as 1 | 2 | 3 | 4, top2);
	}
</script>

<div class="group-standings">
	{#if $$slots['header-extras']}
		<div class="flex items-center gap-2 mb-1">
			<slot name="header-extras" />
		</div>
	{/if}
	<div class="overflow-x-auto -mx-2 sm:mx-0">
		<table class="standings-table">
			<thead>
				<tr>
					<th
						colspan={titleColspan}
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
					{#if showPickColumn}
						<th class="text-center w-10">Pick</th>
					{/if}
				</tr>
			</thead>
			<tbody>
				{#each resolvedStandings as standing, i}
					{@const posClass = getPositionClass(i)}
					{@const marker = showPickColumn && entryPredictedTop2
						? markerFor(standing.team, i + 1, entryPredictedTop2)
						: null}
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
										loading="lazy" style="aspect-ratio: 4 / 3" />
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
						{#if showPickColumn}
							<td class="text-center">
								{#if marker}
									<span class="pick-marker pick-marker-{marker}" title={MARKER_TITLE[marker]}>
										{MARKER_LABEL[marker]}
									</span>
								{/if}
							</td>
						{/if}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	{#if $$slots.footer}
		<div class="mt-2">
			<slot name="footer" />
		</div>
	{/if}
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

	.pick-marker {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.4rem;
		height: 1.4rem;
		border-radius: 0.4rem;
		font-size: 0.65rem;
		font-weight: 700;
	}
	.pick-marker-hit {
		@apply bg-success/20 text-success;
	}
	.pick-marker-swap {
		@apply bg-warning/20 text-warning-text;
	}
	.pick-marker-warn {
		@apply bg-warning/20 text-warning-text;
	}
	.pick-marker-miss {
		@apply bg-error/20 text-error;
	}
	.pick-marker-up {
		@apply text-primary border border-dashed border-primary/40;
	}
</style>
