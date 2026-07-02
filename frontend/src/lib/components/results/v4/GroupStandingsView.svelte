<script lang="ts">
	/** Reusable group-standings view (v2.181.2, reality-check overlay v2.19x).
	 *
	 *  Renders the 12 group cards (A–L) + best-eight third-place qualifying
	 *  table. Used by the standalone /standings page AND by the "Group
	 *  Standings" tab on /results (between R3 and R32). The component itself
	 *  is stateless — fetch + gate logic lives in the host page.
	 *
	 *  Reality-check overlay (optional, off by default when `overlayOn` is
	 *  false or predictions aren't supplied): layers the active entry's
	 *  group + best-3rd + R32 + bonus picks on top of the live standings.
	 *  When `overlayOn` is false the component renders byte-identical to
	 *  the pre-overlay version — no new chrome, no behaviour change.
	 */
	import type {
		ActualStandingsResponse,
		TeamStanding as ApiTeamStanding,
		Fixture,
		MatchPrediction,
		BracketPrediction
	} from '$types';
	import type { BonusQuestion } from '$api/bonus';
	import type { BonusPredictionRead } from '$lib/types/leaderboard';
	import type { TeamStanding } from '$lib/utils/standings';
	import type { GroupStandingsMap } from '$lib/utils/bracketResolver';
	import GroupTable from '$lib/components/GroupTable.svelte';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { displayTeamName } from '$lib/utils/teamName';
	import {
		predictedStandingsMap,
		groupVerdict,
		qtrackFromEntry,
		groupStatusFromStandings,
		predictedBestThirdRankMap,
		bestThirdOverlayState,
		bestThirdShiftSummary,
		projectedR32Pairings,
		r32DifferencesVsPrediction,
		groupPhaseBonusState,
		anyGroupIncomplete as computeAnyGroupIncomplete,
		type GroupVerdict,
		type QDotState,
		type GroupFilter
	} from '$lib/utils/groupTracker';
	import OverlayBanner from './group-tracker/OverlayBanner.svelte';
	import KpiBand from './group-tracker/KpiBand.svelte';
	import FilterChips from './group-tracker/FilterChips.svelte';
	import QTracker from './group-tracker/QTracker.svelte';
	import GroupVerdictBadge from './group-tracker/GroupVerdictBadge.svelte';
	import R32ImpactPreview from './group-tracker/R32ImpactPreview.svelte';
	import BonusStripGroupPhase from './group-tracker/BonusStripGroupPhase.svelte';

	export let payload: ActualStandingsResponse | null;
	export let loading = false;
	export let error: string | null = null;
	export let lastUpdatedAt: Date | null = null;

	// ── Reality-check overlay inputs (all optional; overlay is a no-op
	//    when overlayOn is false or entryFixtures/entryMatchPredictions
	//    haven't loaded yet). ──
	export let overlayOn = false;
	export let onToggleOverlay: () => void = () => {};
	export let entryFixtures: Fixture[] = [];
	export let entryMatchPredictions: MatchPrediction[] = [];
	export let entryBracketPrediction: BracketPrediction | null = null;
	export let bonusQuestions: BonusQuestion[] = [];
	export let bonusAnswers: BonusPredictionRead[] = [];

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

	$: anyGroupIncomplete = payload ? computeAnyGroupIncomplete(payload.standings) : false;

	function formatTimestamp(d: Date | null): string {
		if (!d) return '';
		return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
	}

	// ---------------------------------------------------------------------
	// Reality-check derivations (only computed while overlayOn — cheap to
	// skip entirely when the toggle is off).
	// ---------------------------------------------------------------------

	$: actualStandingsByGroup = payload
		? (Object.fromEntries(groupKeys.map((g) => [g, payload.standings[g].map(toClientShape)])) as GroupStandingsMap)
		: {};

	$: canOverlay = overlayOn && entryFixtures.length > 0 && payload !== null;

	$: predictionsByFixtureId = new Map(entryMatchPredictions.map((p) => [p.fixture_id, p]));
	$: predictedMap = canOverlay ? predictedStandingsMap(entryFixtures, predictionsByFixtureId) : {};

	function predictedTop2For(group: string): [string | undefined, string | undefined] {
		const s = predictedMap[group] ?? [];
		return [s[0]?.team, s[1]?.team];
	}

	$: verdictByGroup = canOverlay
		? (Object.fromEntries(
				groupKeys.map((g) => [
					g,
					groupVerdict(predictedTop2For(g), actualStandingsByGroup[g] ?? [], g, entryFixtures)
				])
		  ) as Record<string, GroupVerdict>)
		: {};

	$: qtrackByGroup = canOverlay
		? (Object.fromEntries(
				groupKeys.map((g) => [g, qtrackFromEntry(predictedTop2For(g), actualStandingsByGroup[g] ?? [])])
		  ) as Record<string, [QDotState, QDotState]>)
		: {};

	$: statusByGroup = Object.fromEntries(
		groupKeys.map((g) => [g, groupStatusFromStandings(actualStandingsByGroup[g] ?? [])])
	);

	$: kpiStats = canOverlay
		? (() => {
				let topTwoOnTrack = 0;
				let locked = 0;
				let atRisk = 0;
				let orderSwaps = 0;
				for (const g of groupKeys) {
					const qt = qtrackByGroup[g];
					const v = verdictByGroup[g];
					if (qt) {
						if (qt[0] === 'hit') topTwoOnTrack++;
						if (qt[1] === 'hit') topTwoOnTrack++;
					}
					if (v?.tone === 'good' && statusByGroup[g] === 'final') locked++;
					if (v?.tone === 'warn' || v?.tone === 'miss') atRisk++;
					if (v?.label === 'Right teams, wrong order') orderSwaps++;
				}
				return { topTwoOnTrack, topTwoTotal: groupKeys.length * 2, locked, atRisk, orderSwaps };
		  })()
		: null;

	// ── Filter chips ──
	let activeFilter: GroupFilter = 'all';
	$: filterCounts = canOverlay
		? {
				all: groupKeys.length,
				locked: groupKeys.filter((g) => verdictByGroup[g]?.tone === 'good' && statusByGroup[g] === 'final').length,
				atRisk: groupKeys.filter((g) => verdictByGroup[g]?.tone === 'warn' || verdictByGroup[g]?.tone === 'miss').length,
				orderSwap: groupKeys.filter((g) => verdictByGroup[g]?.label === 'Right teams, wrong order').length,
				upcoming: groupKeys.filter((g) => statusByGroup[g] === 'upcoming').length
		  }
		: ({ all: groupKeys.length, locked: 0, atRisk: 0, orderSwap: 0, upcoming: 0 } as Record<GroupFilter, number>);

	function passesFilter(group: string): boolean {
		if (!canOverlay || activeFilter === 'all') return true;
		const v = verdictByGroup[group];
		if (activeFilter === 'locked') return v?.tone === 'good' && statusByGroup[group] === 'final';
		if (activeFilter === 'atRisk') return v?.tone === 'warn' || v?.tone === 'miss';
		if (activeFilter === 'orderSwap') return v?.label === 'Right teams, wrong order';
		if (activeFilter === 'upcoming') return statusByGroup[group] === 'upcoming';
		return true;
	}

	// ── Best-3rd table overlay ──
	$: userBestThirdRankMap = canOverlay ? predictedBestThirdRankMap(predictedMap) : new Map();
	$: bestThirdSummary =
		canOverlay && payload
			? bestThirdShiftSummary(userBestThirdRankMap, payload.qualifying_third_place.map(toClientShape), actualStandingsByGroup)
			: null;

	// ── R32 impact preview ──
	$: projectedR32 = payload ? projectedR32Pairings(actualStandingsByGroup) : [];
	$: r32Diffs =
		canOverlay && entryBracketPrediction ? r32DifferencesVsPrediction(projectedR32, entryBracketPrediction) : [];

	// ── Group-phase bonus mirror (Q1/Q2) ──
	$: groupBonus = canOverlay ? groupPhaseBonusState(entryFixtures, bonusQuestions, bonusAnswers) : { mostScored: null, mostConceded: null };
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
	{#if anyGroupIncomplete && lastUpdatedAt}
		<p class="mb-3 text-xs text-base-content/40">
			Updated {formatTimestamp(lastUpdatedAt)} · refreshes every minute
		</p>
	{:else if !anyGroupIncomplete}
		<p class="mb-3 text-xs text-base-content/40">Final · group stage complete, standings settled</p>
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

	<OverlayBanner {overlayOn} onToggle={onToggleOverlay} />

	{#if canOverlay && kpiStats}
		<KpiBand
			topTwoOnTrack={kpiStats.topTwoOnTrack}
			topTwoTotal={kpiStats.topTwoTotal}
			locked={kpiStats.locked}
			groupsTotal={groupKeys.length}
			atRisk={kpiStats.atRisk}
			orderSwaps={kpiStats.orderSwaps}
		/>
		<FilterChips active={activeFilter} counts={filterCounts} onSelect={(f) => (activeFilter = f)} />
	{/if}

	<section class="grid gap-4 lg:grid-cols-2">
		{#each groupKeys as group}
			{#if passesFilter(group)}
				<div class="stadium-card no-glow p-4 sm:p-5">
					<GroupTable
						{group}
						standings={payload.standings[group].map(toClientShape)}
						entryPredictedTop2={canOverlay ? predictedTop2For(group) : null}
						overlayOn={canOverlay}
					>
						<svelte:fragment slot="header-extras">
							{#if canOverlay && qtrackByGroup[group]}
								<QTracker dots={qtrackByGroup[group]} />
							{/if}
						</svelte:fragment>
						<svelte:fragment slot="footer">
							{#if canOverlay && verdictByGroup[group]}
								<GroupVerdictBadge verdict={verdictByGroup[group]} />
							{/if}
						</svelte:fragment>
					</GroupTable>
				</div>
			{/if}
		{/each}
	</section>

	<section class="stadium-card no-glow mt-6 p-4 sm:p-5">
		<header class="mb-3">
			<h2 class="font-display text-xl tracking-wide">
				Best third-placed teams
				{#if canOverlay}
					· <span class="text-primary">vs your predicted cohort</span>
				{/if}
			</h2>
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
			{#if canOverlay && bestThirdSummary}
				<div class="mb-3 flex flex-wrap items-center gap-4 rounded-lg bg-primary/10 px-3 py-2 text-xs">
					<span><strong class="text-success">{bestThirdSummary.perfect}</strong> perfect</span>
					<span><strong class="text-warning-text">{bestThirdSummary.rankSwap}</strong> rank-swap</span>
					<span><strong class="text-error">{bestThirdSummary.missedCut}</strong> missed cut</span>
					<span><strong class="text-primary">{bestThirdSummary.surpriseIn}</strong> surprise 3rds</span>
					{#if bestThirdSummary.droppedEntirely > 0}
						<span class="text-base-content/55">
							{bestThirdSummary.droppedEntirely} pick{bestThirdSummary.droppedEntirely === 1 ? '' : 's'} dropped entirely
						</span>
					{/if}
				</div>
			{/if}
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
							{#if canOverlay}
								<th class="text-center w-14">Pick</th>
							{/if}
						</tr>
					</thead>
					<tbody>
						{#each payload.qualifying_third_place as t, i}
							{@const overlayState = canOverlay ? bestThirdOverlayState(t.team, i + 1, userBestThirdRankMap) : null}
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
								{#if canOverlay}
									<td class="text-center whitespace-nowrap">
										{#if overlayState?.marker}
											<span class="inline-flex items-center gap-1" title={overlayState.tooltip}>
												<span class="pick-marker pick-marker-{overlayState.marker}">
													{overlayState.marker === 'hit'
														? '✓'
														: overlayState.marker === 'swap'
															? '↔'
															: overlayState.marker === 'miss'
																? '✕'
																: '↑'}
												</span>
												{#if overlayState.userRank !== null && overlayState.marker !== 'hit'}
													<span class="text-[9px] font-semibold text-base-content/55"
														>#{overlayState.userRank}</span
													>
												{/if}
											</span>
										{/if}
									</td>
								{/if}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</section>

	{#if canOverlay}
		<R32ImpactPreview
			differences={r32Diffs}
			totalMatches={projectedR32.length}
			statusLabel={entryBracketPrediction ? 'Live · updates each match' : 'Bracket prediction not loaded'}
		/>
		<BonusStripGroupPhase mostScored={groupBonus.mostScored} mostConceded={groupBonus.mostConceded} />
	{/if}

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
	.pick-marker-miss {
		@apply bg-error/20 text-error;
	}
	.pick-marker-up {
		@apply text-primary border border-dashed border-primary/40;
	}
</style>
