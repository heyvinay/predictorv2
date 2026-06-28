<script lang="ts">
	/** Reusable group-standings view (v2.181.2).
	 *
	 *  Renders the 12 group cards (A–L) + best-eight third-place qualifying
	 *  table. Used by the standalone /standings page AND by the new "Group
	 *  Standings" tab on /results (between R3 and R32). The component itself
	 *  is stateless — fetch + gate logic lives in the host page.
	 */
	import type {
		ActualStandingsResponse,
		TeamStanding as ApiTeamStanding
	} from '$types';
	import type { TeamStanding } from '$lib/utils/standings';
	import GroupTable from '$lib/components/GroupTable.svelte';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { displayTeamName } from '$lib/utils/teamName';

	export let payload: ActualStandingsResponse | null;
	export let loading = false;
	export let error: string | null = null;
	export let lastUpdatedAt: Date | null = null;

	function toClientShape(row: ApiTeamStanding): TeamStanding {
		return {
			team: row.team,
			group: row.group,
			played: row.played,
			won: row.won,
			drawn: row.drawn,
			lost: row.lost,
			goalsFor: row.goals_for,
			goalsAgainst: row.goals_against,
			goalDifference: row.goal_difference,
			points: row.points
		};
	}

	$: groupKeys = payload ? Object.keys(payload.standings).sort() : [];

	$: anyGroupIncomplete = payload
		? Object.values(payload.standings).some((g) =>
				g.some((t) => t.played < 3)
		  )
		: false;

	function formatTimestamp(d: Date | null): string {
		if (!d) return '';
		return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
	}
</script>

{#if loading}
	<div class="flex justify-center py-16">
		<span class="loading loading-spinner loading-lg text-primary"></span>
	</div>
{:else if error}
	<div class="alert alert-error">
		<span>Couldn't load standings: {error}</span>
	</div>
{:else if payload}
	{#if lastUpdatedAt}
		<p class="mb-3 text-xs text-base-content/40">
			Updated {formatTimestamp(lastUpdatedAt)} · refreshes every minute
		</p>
	{/if}

	{#if anyGroupIncomplete}
		<div
			class="mb-4 rounded-xl border border-warning/40 bg-warning/10 px-4 py-2 text-sm text-warning-text"
			role="status"
		>
			Some groups haven't finished all three matchdays yet — standings will
			settle once Round 3 wraps.
		</div>
	{/if}

	<section class="grid gap-4 lg:grid-cols-2">
		{#each groupKeys as group}
			<div class="stadium-card p-4 sm:p-5">
				<GroupTable
					{group}
					standings={payload.standings[group].map(toClientShape)}
				/>
			</div>
		{/each}
	</section>

	<section class="stadium-card mt-6 p-4 sm:p-5">
		<header class="mb-3">
			<h2 class="font-display text-xl tracking-wide">Best third-placed teams</h2>
			<p class="mt-1 text-xs text-base-content/55 max-w-prose">
				FIFA picks the top eight third-placed teams across the twelve groups
				to join the Round of 32. Head-to-head doesn't apply across groups —
				ties resolve by overall GD, then goals, then alphabetical.
			</p>
		</header>

		{#if payload.qualifying_third_place.length === 0}
			<p class="text-sm text-base-content/55">
				Third-place candidates appear here once every group has played at
				least one match.
			</p>
		{:else}
			<div class="overflow-x-auto -mx-2 sm:mx-0">
				<table class="standings-table">
					<thead>
						<tr>
							<th class="w-8 text-center">#</th>
							<th class="text-left">Team</th>
							<th class="text-center w-10">Grp</th>
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
						{#each payload.qualifying_third_place as t, i}
							<tr class="standing-row {i < 8 ? 'qualifies' : 'eliminated'}">
								<td class="text-center">
									<span class="position-indicator {i < 8 ? 'qualifies' : 'eliminated'}">
										{i + 1}
									</span>
								</td>
								<td class="team-cell">
									<div class="flex items-center gap-2">
										{#if hasFlag(t.team)}
											<img
												src={getFlagUrl(t.team, 'sm')}
												alt="{t.team} flag"
												class="w-5 h-auto rounded-sm shadow-sm flex-shrink-0"
												loading="lazy"
												style="aspect-ratio: 4 / 3"
											/>
										{:else}
											<div class="w-5 h-3.5 bg-base-300 rounded-sm flex-shrink-0"></div>
										{/if}
										<span class="team-name-table">
											{displayTeamName(t.team)}
										</span>
									</div>
								</td>
								<td class="text-center text-base-content/70">{t.group}</td>
								<td class="text-center text-base-content/70">{t.played}</td>
								<td class="text-center text-success font-medium">{t.won}</td>
								<td class="text-center text-base-content/50">{t.drawn}</td>
								<td class="text-center text-error/80">{t.lost}</td>
								<td class="text-center text-base-content/70 hidden sm:table-cell">
									{t.goals_for}
								</td>
								<td class="text-center text-base-content/70 hidden sm:table-cell">
									{t.goals_against}
								</td>
								<td
									class="text-center gd-cell {t.goal_difference > 0
										? 'positive'
										: t.goal_difference < 0
											? 'negative'
											: ''}"
								>
									{t.goal_difference > 0 ? '+' : ''}{t.goal_difference}
								</td>
								<td class="text-center">
									<span class="points-badge">{t.points}</span>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</section>

	<p class="mt-4 text-xs text-base-content/40 max-w-prose">
		Standings derive from finished match results with FIFA Article 13
		tiebreakers applied: points → head-to-head points → head-to-head GD →
		head-to-head goals → overall GD → overall goals → alphabetical
		(deterministic fallback when fair-play and FIFA-ranking criteria can't
		be computed here).
	</p>
{/if}

<style>
	.standing-row.qualifies {
		@apply border-l-2 border-l-success;
	}
	.standing-row.eliminated {
		@apply border-l-2 border-l-error;
	}
	.position-indicator.qualifies {
		@apply bg-success/20 text-success;
	}
	.position-indicator.eliminated {
		@apply bg-error/20 text-error;
	}
</style>
