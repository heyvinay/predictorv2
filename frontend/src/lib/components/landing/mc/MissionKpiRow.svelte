<!--
  MissionKpiRow — 6 KPI cards in two rows of three.

  Row 1: Rank · Total · Trajectory (sparkline)
  Row 2: Outcomes · Exact · Rarity bonus

  Each card carries an arrow-delta chip (↑N / ↓N / ±0) where data permits.
  Delta sources:
    - Rank: $activeMovement (LeaderboardEntry.movement field, already wired)
    - Total: difference between current and oldest snapshot in trajectory
    - Outcomes/Exact: not deltable today — LeaderboardSnapshot only stores
      position + total_points. Cards show count + hit-rate sub instead.

  Reads from $missionDerived stores — re-contextualises with the active
  entry. Ported from upstream's DwKpiRow with token swap to our
  premium-night palette + single-phase simplifications.
-->
<script lang="ts">
	import {
		activeRank,
		activePoints,
		activeMovement,
		activeBreakdown,
		activeCorrectOutcomes,
		activeExactScores
	} from '$stores/missionDerived';
	import { totalParticipants } from '$stores/leaderboard';
	import type { RankSnapshotPoint } from '$api/leaderboard';
	import MissionSparkline from './MissionSparkline.svelte';

	/** Last N daily rank+points snapshots, newest LAST in the array. */
	export let trajectory: RankSnapshotPoint[] = [];
	/** ghostSeries: optional sibling-entry trajectories drawn as dashed lines
	 *  behind the active line. Each element is `{ entry_id, points: RankSnapshotPoint[] }`. */
	export let ghostSeries: { entry_id: string; points: RankSnapshotPoint[] }[] = [];

	$: rankOf = $totalParticipants || 0;
	$: rank = $activeRank;
	$: total = $activePoints;
	$: rankDelta = $activeMovement;
	$: bd = $activeBreakdown;
	$: rarity = bd?.hybrid_bonus_points ?? 0;
	$: outcomes = $activeCorrectOutcomes;
	$: exact = $activeExactScores;
	$: totalPredictions = bd?.total_predictions ?? 0;

	// Total delta: current points minus oldest snapshot in window
	$: totalDelta =
		trajectory.length >= 2 ? trajectory[trajectory.length - 1].total_points - trajectory[0].total_points : 0;

	$: outcomeRate = totalPredictions > 0 ? Math.round((outcomes / totalPredictions) * 100) : 0;
	$: exactRate = totalPredictions > 0 ? Math.round((exact / totalPredictions) * 100) : 0;
	$: rarityShare = total > 0 ? Math.round((rarity / total) * 100) : 0;

	// Sparkline expects raw rank numbers (ranks[0] = oldest, ranks[end] = newest).
	$: trajectoryRanks = trajectory.map((p) => p.position);
	$: trajectoryMaxRank = Math.max(rankOf, ...trajectoryRanks, 1);

	$: trajPlaces = trajectoryRanks.length >= 2 ? trajectoryRanks[0] - trajectoryRanks[trajectoryRanks.length - 1] : 0;
	$: trajectoryNowDelta = totalDelta;

	function delta(d: number): { tone: 'up' | 'dn' | 'zero'; label: string } {
		if (!d) return { tone: 'zero', label: '±0' };
		const up = d > 0;
		return { tone: up ? 'up' : 'dn', label: `${up ? '↑' : '↓'}${Math.abs(d)}` };
	}

	$: rd = delta(rankDelta * -1); // movement chip: +N means climbed = good = arrow-up
	$: td = delta(totalDelta);
</script>

<section class="grid grid-cols-2 lg:grid-cols-3 gap-3 mb-4">
	<!-- Rank -->
	<div class="stadium-card no-glow p-4">
		<div class="text-[10.5px] font-bold uppercase tracking-[0.12em] text-base-content/55 mb-1.5">
			Rank
		</div>
		<div class="flex items-baseline justify-between">
			<div class="font-display font-extrabold text-3xl leading-none">
				<span class="text-primary">{rank ?? '—'}</span>
				<span class="text-sm text-base-content/55">/{rankOf || '—'}</span>
			</div>
			<span class="text-xs font-bold {rd.tone === 'up' ? 'text-success' : rd.tone === 'dn' ? 'text-error' : 'text-base-content/55'}">
				{rd.label}
			</span>
		</div>
	</div>

	<!-- Total points -->
	<div class="stadium-card no-glow p-4">
		<div class="text-[10.5px] font-bold uppercase tracking-[0.12em] text-base-content/55 mb-1.5">
			Total
		</div>
		<div class="flex items-baseline justify-between">
			<div class="font-display font-extrabold text-3xl leading-none">
				{total}<span class="text-sm text-base-content/55"> pts</span>
			</div>
			<span class="text-xs font-bold {td.tone === 'up' ? 'text-success' : td.tone === 'dn' ? 'text-error' : 'text-base-content/55'}">
				{td.label}
			</span>
		</div>
	</div>

	<!-- Trajectory -->
	<div
		class="stadium-card no-glow p-4 min-w-0"
		style="background: linear-gradient(135deg, rgba(212,175,55,0.08), var(--b2, #1C2541));"
	>
		<div class="text-[10.5px] font-bold uppercase tracking-[0.12em] text-base-content/55 mb-1.5">
			Trajectory · {trajectory.length}d
		</div>
		<div class="h-[46px] min-w-0">
			{#if trajectoryRanks.length >= 2}
				<!-- Ghost lines first (drawn behind) -->
				<div class="relative">
					{#each ghostSeries as g (g.entry_id)}
						<div class="absolute inset-0">
							<MissionSparkline
								ranks={g.points.map((p) => p.position)}
								maxRank={trajectoryMaxRank}
								width={240}
								height={46}
								ghost={true}
							/>
						</div>
					{/each}
					<MissionSparkline ranks={trajectoryRanks} maxRank={trajectoryMaxRank} width={240} height={46} />
				</div>
			{:else}
				<div class="h-full grid place-items-center font-mono text-[10px] text-base-content/55">
					awaiting history
				</div>
			{/if}
		</div>
		<div class="text-[11px] text-base-content/55 mt-1.5">
			{#if trajPlaces > 0}<span class="text-success font-bold">▲{trajPlaces} pl</span>
			{:else if trajPlaces < 0}<span class="text-error font-bold">▼{Math.abs(trajPlaces)} pl</span>
			{:else}<span>— pl</span>{/if}
			· last {trajectory.length}d
			· <em class="text-base-content not-italic font-bold">{trajectoryNowDelta >= 0 ? '+' : ''}{trajectoryNowDelta}</em>
		</div>
	</div>

	<!-- Outcomes -->
	<div class="stadium-card no-glow p-4">
		<div class="text-[10.5px] font-bold uppercase tracking-[0.12em] text-base-content/55 mb-1.5">
			Outcomes
		</div>
		<div class="font-display font-extrabold text-3xl leading-none">
			{outcomes}<span class="text-sm text-base-content/55">/{totalPredictions || '—'}</span>
		</div>
		<div class="text-[11px] text-base-content/55 mt-1.5">
			<b class="text-base-content">{outcomeRate}%</b> hit rate
		</div>
	</div>

	<!-- Exact -->
	<div class="stadium-card no-glow p-4">
		<div class="text-[10.5px] font-bold uppercase tracking-[0.12em] text-base-content/55 mb-1.5">
			Exact
		</div>
		<div class="font-display font-extrabold text-3xl leading-none">
			<span class="text-success">{exact}</span><span class="text-sm text-base-content/55">/{totalPredictions || '—'}</span>
		</div>
		<div class="text-[11px] text-base-content/55 mt-1.5">
			<b class="text-base-content">{exactRate}%</b> hit rate
		</div>
	</div>

	<!-- Rarity bonus -->
	<div class="stadium-card no-glow p-4">
		<div class="text-[10.5px] font-bold uppercase tracking-[0.12em] text-base-content/55 mb-1.5">
			Rarity bonus
		</div>
		<div class="font-display font-extrabold text-3xl leading-none">
			{rarity}<span class="text-sm text-base-content/55"> pts</span>
		</div>
		{#if total > 0}
			<div class="text-[11px] text-base-content/55 mt-1.5">
				<b class="text-base-content">{rarityShare}%</b> of total
			</div>
		{/if}
	</div>
</section>
