<script lang="ts">
	/** Group Standings page (v2.181.1) — 12 group cards (A–L) plus the
	 *  qualifying third-place table, computed server-side from finished
	 *  group-stage match results with the FIFA tiebreaker chain applied
	 *  (Article 13: H2H → overall GD → goals → alphabetical fallback).
	 *
	 *  Gated by the post-deadline release switch (mirrors /results and
	 *  /leaderboard): pre-release shows the "Standings open at kickoff"
	 *  stub; admins see the page immediately so they can verify it.
	 *
	 *  Polls every 60s while the tab is visible so the page stays fresh
	 *  during R3 — same cadence as /leaderboard.
	 */
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import { postDeadlineLive } from '$stores/phase';
	import { getActualStandings } from '$api/fixtures';
	import { startLivePoll } from '$lib/utils/livePoll';
	import type {
		ActualStandingsResponse,
		TeamStanding as ApiTeamStanding
	} from '$types';
	import type { TeamStanding } from '$lib/utils/standings';
	import GroupTable from '$lib/components/GroupTable.svelte';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { displayTeamName } from '$lib/utils/teamName';

	$: if (!$isAuthenticated) goto('/login');

	const STANDINGS_ENABLED = true;
	$: standingsOpen = STANDINGS_ENABLED && ($user?.is_admin === true || $postDeadlineLive);

	let loading = true;
	let payload: ActualStandingsResponse | null = null;
	let loadError: string | null = null;
	let lastUpdatedAt: Date | null = null;

	/** Adapt the backend's snake_case row to the camelCase TeamStanding
	 *  shape that GroupTable expects. The CLAUDE.md "shapes match" note
	 *  was almost-true — field names differ between the wire and the
	 *  client-side calculator's output. */
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

	async function loadStandings() {
		try {
			payload = await getActualStandings();
			lastUpdatedAt = new Date();
			loadError = null;
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Failed to load standings';
		} finally {
			loading = false;
		}
	}

	let dataRequested = false;
	$: if (standingsOpen && !dataRequested) {
		dataRequested = true;
		void loadStandings();
	}

	let stopPoll: (() => void) | null = null;
	onMount(() => {
		stopPoll = startLivePoll(() => {
			if (standingsOpen) void loadStandings();
		});
	});
	onDestroy(() => {
		stopPoll?.();
	});

	/** Sorted group keys (A–L). Backend may return groups in arbitrary order. */
	$: groupKeys = payload ? Object.keys(payload.standings).sort() : [];

	/** Standings staleness banner: any group with played < 3 means R3 hasn't
	 *  fully landed yet (or fixtures sync is lagging). */
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

<svelte:head>
	<title>Group Standings — Predictor v2</title>
</svelte:head>

{#if $isAuthenticated && !standingsOpen}
	<div class="hero min-h-[60vh]">
		<div class="hero-content text-center">
			<div class="max-w-md">
				<h2 class="font-display text-3xl tracking-wide">Standings open at kickoff</h2>
				<p class="mt-3 text-base-content/60">
					Live group tables go live once the tournament begins.
				</p>
				<a href="/entries" class="btn btn-primary btn-lg mt-6 shadow-glow-gold">
					Lock in your predictions
				</a>
			</div>
		</div>
	</div>
{:else if $isAuthenticated}
	<div class="container mx-auto mobile-padding max-w-[1180px] py-4">
		<header class="mb-6">
			<h1 class="font-display text-3xl sm:text-4xl tracking-wide">Group Standings</h1>
			<p class="mt-1 text-sm text-base-content/60">
				Live group tables from finished match results. Top two in each group qualify
				directly; the best eight third-placed teams join them in the Round of 32.
			</p>
			{#if lastUpdatedAt}
				<p class="mt-2 text-xs text-base-content/40">
					Updated {formatTimestamp(lastUpdatedAt)} · refreshes every minute
				</p>
			{/if}
		</header>

		{#if loading}
			<div class="flex justify-center py-16">
				<span class="loading loading-spinner loading-lg text-primary"></span>
			</div>
		{:else if loadError}
			<div class="alert alert-error">
				<span>Couldn't load standings: {loadError}</span>
			</div>
		{:else if payload}
			{#if anyGroupIncomplete}
				<div
					class="mb-4 rounded-xl border border-warning/40 bg-warning/10 px-4 py-2 text-sm text-warning-text"
					role="status"
				>
					Some groups haven't finished all three matchdays yet — standings will
					settle once R3 wraps.
				</div>
			{/if}

			<!-- 12 group cards, A–L, two-column on lg+, single-column on mobile -->
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

			<!-- Third-place qualifying table -->
			<section class="stadium-card mt-6 p-4 sm:p-5">
				<header class="mb-3">
					<h2 class="font-display text-xl tracking-wide">
						Best third-placed teams
					</h2>
					<p class="mt-1 text-xs text-base-content/55 max-w-prose">
						FIFA picks the top eight third-placed teams (across all twelve
						groups) to join the Round of 32. Head-to-head doesn't apply across
						groups — ties resolve by overall GD, then goals, then alphabetical.
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
											<span
												class="position-indicator {i < 8
													? 'qualifies'
													: 'eliminated'}"
											>
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
													<div
														class="w-5 h-3.5 bg-base-300 rounded-sm flex-shrink-0"
													></div>
												{/if}
												<span class="team-name-table">
													{displayTeamName(t.team)}
												</span>
											</div>
										</td>
										<td class="text-center text-base-content/70">{t.group}</td>
										<td class="text-center text-base-content/70">{t.played}</td>
										<td class="text-center text-success font-medium">
											{t.won}
										</td>
										<td class="text-center text-base-content/50">{t.drawn}</td>
										<td class="text-center text-error/80">{t.lost}</td>
										<td
											class="text-center text-base-content/70 hidden sm:table-cell"
										>
											{t.goals_for}
										</td>
										<td
											class="text-center text-base-content/70 hidden sm:table-cell"
										>
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
	</div>
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
