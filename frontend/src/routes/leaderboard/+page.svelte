<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import {
		fetchLeaderboard,
		setPhase,
		startPolling,
		stopPolling,
		leaderboard,
		leaderboardLoading,
		lastCalculated,
		totalParticipants,
		activeEntryPosition,
		myLeaderboardRows,
		leaderboardPhase,
		type LeaderboardPhase
	} from '$stores/leaderboard';
	import { getGroupTotal, type PhaseBreakdown, type PointBreakdown } from '$types';
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import PnSparkline from '$components/panini/PnSparkline.svelte';
	import { stubRankTrajectory } from '$lib/stubs/panini';
	import { loadEntries, entrySettings } from '$stores/entries';
	import { isYouRow, shouldShowReference } from '$lib/utils/leaderboard';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	onMount(() => {
		if ($isAuthenticated) {
			startPolling(60000);
		}
	});

	// Pull entry settings as soon as $user.id resolves. The conditional
	// reference column on each row needs $entrySettings to be populated.
	// Using $: so initAuth() resolving after onMount doesn't strand us
	// without settings.
	let entriesLoadStarted = false;
	$: if ($isAuthenticated && $user?.id && !entriesLoadStarted) {
		entriesLoadStarted = true;
		void loadEntries($user.id);
	}

	onDestroy(() => {
		stopPolling();
	});

	async function handlePhaseChange(phase: LeaderboardPhase) {
		await setPhase(phase);
	}

	function ordinal(n: number): string {
		if (n % 100 >= 11 && n % 100 <= 13) return 'th';
		switch (n % 10) {
			case 1: return 'st';
			case 2: return 'nd';
			case 3: return 'rd';
			default: return 'th';
		}
	}

	function formatLastUpdated(date: string | null): string {
		if (!date) return '';
		return new Date(date).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
	}

	// Match-cell value for the current phase filter
	function matchPts(b: PointBreakdown, phase: LeaderboardPhase): number {
		if (phase === 'phase_1') return b.phase1.match_outcome_points + b.phase1.exact_score_points + b.phase1.hybrid_bonus_points;
		if (phase === 'phase_2') return b.phase2.match_outcome_points + b.phase2.exact_score_points + b.phase2.hybrid_bonus_points;
		return b.match_total;
	}
	function exactPts(b: PointBreakdown, phase: LeaderboardPhase): number {
		if (phase === 'phase_1') return b.phase1.exact_score_points;
		if (phase === 'phase_2') return b.phase2.exact_score_points;
		return b.exact_score_points;
	}
	function outcomePts(b: PointBreakdown, phase: LeaderboardPhase): number {
		if (phase === 'phase_1') return b.phase1.match_outcome_points;
		if (phase === 'phase_2') return b.phase2.match_outcome_points;
		return b.match_outcome_points;
	}
	function bonusPts(b: PointBreakdown, phase: LeaderboardPhase): number {
		if (phase === 'phase_1') return b.phase1.hybrid_bonus_points;
		if (phase === 'phase_2') return b.phase2.hybrid_bonus_points;
		return b.hybrid_bonus_points;
	}
	function bracketPts(b: PointBreakdown, phase: LeaderboardPhase): number {
		if (phase === 'phase_1') return getGroupTotal(b.phase1) + b.phase1.round_of_32_points + b.phase1.round_of_16_points + b.phase1.quarter_final_points + b.phase1.semi_final_points + b.phase1.final_points + b.phase1.winner_points;
		if (phase === 'phase_2') return getGroupTotal(b.phase2) + b.phase2.round_of_32_points + b.phase2.round_of_16_points + b.phase2.quarter_final_points + b.phase2.semi_final_points + b.phase2.final_points + b.phase2.winner_points;
		return b.bracket_total;
	}

	// Row expansion state — keyed by entry_id (a user can hold multiple
	// entries, each with its own row).
	let expanded = new Set<string>();
	function toggle(entryId: string) {
		if (expanded.has(entryId)) expanded.delete(entryId);
		else expanded.add(entryId);
		expanded = expanded; // trigger reactivity
	}

	// Phases listed in the per-row expander, in order
	const DETAIL_PHASES: Array<{ k: 'phase1' | 'phase2'; name: string }> = [
		{ k: 'phase1', name: 'Phase I' },
		{ k: 'phase2', name: 'Phase II' }
	];

	// Per-phase breakdown helpers
	function phaseTotal(p: PhaseBreakdown): number {
		return (
			p.match_outcome_points +
			p.exact_score_points +
			p.hybrid_bonus_points +
			getGroupTotal(p) +
			p.round_of_32_points +
			p.round_of_16_points +
			p.quarter_final_points +
			p.semi_final_points +
			p.final_points +
			p.winner_points
		);
	}
	function phaseBracketSum(p: PhaseBreakdown): number {
		return (
			getGroupTotal(p) +
			p.round_of_32_points +
			p.round_of_16_points +
			p.quarter_final_points +
			p.semi_final_points +
			p.final_points +
			p.winner_points
		);
	}

	$: yourRank = $activeEntryPosition?.position ?? 0;
	$: yourPoints = $activeEntryPosition?.total_points ?? 0;
	$: leaderPoints = $leaderboard[0]?.total_points ?? 0;
	$: toFirst = yourRank > 1 ? yourPoints - leaderPoints : 0;
	$: yourMovement = $activeEntryPosition?.movement ?? 0;
	$: yourExact = $activeEntryPosition?.exact_scores ?? 0;
	$: yourOutcomes = $activeEntryPosition?.correct_outcomes ?? 0;

	// Roughly how many points are still in play — sum of remaining bracket
	// stages + estimated unfinished match exact/outcome ceiling. For now
	// use a fixed-ish number; this slot exists in the design.
	$: availablePts = 288;
</script>

<svelte:head>
	<title>Standings — Predictor</title>
</svelte:head>

{#if $isAuthenticated}
	<PnPageShell>
		<!-- ===== DESKTOP ===== -->
		<div class="pn-desk">
			<div class="pn-lb-h">
				<div class="ttl">THE <em>STANDINGS</em></div>
				<div class="pn-lb-tabs">
					<button class:on={$leaderboardPhase === 'overall'} on:click={() => handlePhaseChange('overall')}>Overall</button>
					<button class:on={$leaderboardPhase === 'phase_1'} on:click={() => handlePhaseChange('phase_1')}>Phase I</button>
					<button class:on={$leaderboardPhase === 'phase_2'} on:click={() => handlePhaseChange('phase_2')}>Phase II</button>
				</div>
			</div>

			{#if $activeEntryPosition}
				<div class="pn-lb-self">
					<div class="num">
						{yourRank}<span style="font-size: 24px; color: rgba(255,255,255,0.65); vertical-align: top;">{ordinal(yourRank)}</span>
					</div>
					<div>
						<div class="nm">
							{$activeEntryPosition.entry_name}
							<span style="background: var(--paper); color: var(--red); padding: 2px 6px; font-size: 11px; margin-left: 8px;">YOU</span>
						</div>
						<div class="sub">
							{$activeEntryPosition.user_name} · {yourExact} exact · {yourOutcomes} outcomes
							{#if yourMovement !== 0}
								· {yourMovement > 0 ? '▲' : '▼'}{Math.abs(yourMovement)} last update
							{/if}
						</div>
					</div>
					<div class="stat"><div class="l">Total</div><div class="v">{yourPoints}</div></div>
					<div class="stat"><div class="l">To #1</div><div class="v">{toFirst < 0 ? toFirst : toFirst === 0 ? '—' : `+${toFirst}`}</div></div>
					<div class="stat"><div class="l">Available</div><div class="v">{availablePts}</div></div>
				</div>
			{/if}

			<div class="pn-card pn-lb-card">
				<div class="pn-card-h">
					<span>★ STANDINGS · {$totalParticipants || $leaderboard.length} PLAYERS</span>
					<span class="right">
						{#if $leaderboardLoading}LOADING…{:else if $lastCalculated}Updated {formatLastUpdated($lastCalculated)}{/if}
					</span>
				</div>
				<div class="pn-card-body">
					<table class="pn-lb-table">
						<thead>
							<tr>
								<th>#</th>
								<th>Player</th>
								<th class="c">Exact</th>
								<th class="c">Outcome</th>
								<th class="c">Bonus</th>
								<th class="c">Bracket</th>
								<th class="c">Trend · 7d</th>
								<th class="r">Total</th>
								<th class="r">Move</th>
								<th></th>
							</tr>
						</thead>
						<tbody>
							{#each $leaderboard as r (r.entry_id)}
								{@const isYou = isYouRow(r, $user?.id)}
								{@const showRef = shouldShowReference(r, $entrySettings, $user?.id, $user?.is_admin ?? false)}
								{@const traj = stubRankTrajectory(r.entry_id, r.position, $totalParticipants || $leaderboard.length || 32)}
								{@const isOpen = expanded.has(r.entry_id)}
								<tr class:you={isYou} class:open={isOpen} on:click={() => toggle(r.entry_id)} style="cursor: pointer;">
									<td class="pos" class:gold={r.position <= 3}>{r.position}</td>
									<td class="nm-cell">
										<a href="/profile/{r.user_id}" style="color: inherit; text-decoration: none;" on:click|stopPropagation>
											<span class="nm-line">
												{r.entry_name}
												{#if isYou}<span class="pn-lb-you">YOU</span>{/if}
												{#if showRef}<span class="pn-lb-ref">{r.entry_reference}</span>{/if}
											</span>
											<span class="h">{r.user_name}</span>
										</a>
									</td>
									<td class="c exact">{exactPts(r.breakdown, $leaderboardPhase)}</td>
									<td class="c">{outcomePts(r.breakdown, $leaderboardPhase)}</td>
									<td class="c bonus">{bonusPts(r.breakdown, $leaderboardPhase)}</td>
									<td class="c bracket">{bracketPts(r.breakdown, $leaderboardPhase)}</td>
									<td class="c">
										<PnSparkline
											ranks={traj.ranks}
											maxRank={traj.maxRank}
											width={80}
											height={22}
											strokeColor={isYou ? 'var(--red)' : 'var(--ink)'}
											fillColor="transparent"
											markerColor={isYou ? 'var(--red)' : 'var(--ink)'}
										/>
									</td>
									<td class="r total">{#if isYou}<em>{r.total_points}</em>{:else}{r.total_points}{/if}</td>
									<td class="r mv">
										{#if r.movement > 0}<span class="up">▲{r.movement}</span>
										{:else if r.movement < 0}<span class="dn">▼{Math.abs(r.movement)}</span>
										{:else}<span class="eq">—</span>{/if}
									</td>
									<td class="expand"><span class="chev">▾</span></td>
								</tr>
								{#if isOpen}
									<tr class="detail">
										<td colspan="10">
											<div class="pn-lb-detail">
												{#each DETAIL_PHASES as ph (ph.k)}
													{@const p = r.breakdown[ph.k]}
													<div class="phase">
														<div class="ph-h">
															<span>{ph.name}</span>
															<b>{phaseTotal(p)} pts</b>
														</div>
														<div class="grid">
															<div class="cell"><div class="l">Outcome</div><div class="v">{p.match_outcome_points}</div></div>
															<div class="cell"><div class="l">Exact</div><div class="v exact">{p.exact_score_points}</div></div>
															<div class="cell"><div class="l">Bonus</div><div class="v bonus">{p.hybrid_bonus_points}</div></div>
															<div class="cell"><div class="l">Bracket</div><div class="v bracket">{phaseBracketSum(p)}</div></div>
														</div>
													</div>
												{/each}
											</div>
										</td>
									</tr>
								{/if}
							{:else}
								<tr><td colspan="10" style="padding: 24px; text-align: center; font-family: var(--mono); color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">No standings yet</td></tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		</div>

		<!-- ===== MOBILE ===== -->
		<div class="pn-mob">
			<div class="pn-m-lb-h">
				<div class="ttl">THE <em>STANDINGS</em></div>
				<div class="meta">{$totalParticipants || $leaderboard.length} PLAYERS<br />{#if $lastCalculated}UPD {formatLastUpdated($lastCalculated)}{/if}</div>
			</div>

			<div class="pn-m-lb-tabs">
				<button class:on={$leaderboardPhase === 'overall'} on:click={() => handlePhaseChange('overall')}>Overall</button>
				<button class:on={$leaderboardPhase === 'phase_1'} on:click={() => handlePhaseChange('phase_1')}>Phase I</button>
				<button class:on={$leaderboardPhase === 'phase_2'} on:click={() => handlePhaseChange('phase_2')}>Phase II</button>
			</div>

			{#if $activeEntryPosition}
				<div class="pn-m-lb-self">
					<div class="num">
						{yourRank}<span style="font-size: 16px; color: rgba(255,255,255,0.7); vertical-align: top;">{ordinal(yourRank)}</span>
					</div>
					<div>
						<div class="nm">{$activeEntryPosition.entry_name}</div>
						<div class="sub">{$activeEntryPosition.user_name} · {yourExact} ex · {yourOutcomes} outc {#if yourMovement !== 0}· {yourMovement > 0 ? '▲' : '▼'}{Math.abs(yourMovement)}{/if}</div>
					</div>
					<div class="pts">
						<div class="v">{yourPoints}</div>
						<div class="l">{toFirst === 0 ? 'LEADER' : `${toFirst} to #1`}</div>
					</div>
				</div>
			{/if}

			<div class="pn-m-lb-rows">
				{#each $leaderboard as r (r.entry_id)}
					{@const isYou = isYouRow(r, $user?.id)}
					{@const showRef = shouldShowReference(r, $entrySettings, $user?.id, $user?.is_admin ?? false)}
					{@const isOpen = expanded.has(r.entry_id)}
					<div
						class="pn-m-lb-row"
						class:gold={r.position <= 3}
						class:you={isYou}
						class:open={isOpen}
						role="button"
						tabindex="0"
						on:click={() => toggle(r.entry_id)}
						on:keydown={(e) => (e.key === 'Enter' || e.key === ' ') && toggle(r.entry_id)}
					>
						<div class="pos">{r.position}</div>
						<div>
							<div class="nm">
								{r.entry_name}
								{#if isYou}<span class="pn-lb-you">YOU</span>{/if}
								{#if showRef}<span class="pn-lb-ref">{r.entry_reference}</span>{/if}
							</div>
							<div class="h">{r.user_name} · {r.exact_scores} ex · {r.correct_outcomes} outc · <span class="chev">▾</span></div>
						</div>
						<div class="pts">{r.total_points}</div>
						<div class="mv">
							{#if r.movement > 0}<span class="up">▲{r.movement}</span>
							{:else if r.movement < 0}<span class="dn">▼{Math.abs(r.movement)}</span>
							{:else}<span class="eq">—</span>{/if}
						</div>
					</div>
					{#if isOpen}
						<div class="pn-m-lb-detail">
							{#each DETAIL_PHASES as ph (ph.k)}
								{@const p = r.breakdown[ph.k]}
								<div class="phase">
									<div class="ph-h">
										<span>{ph.name}</span>
										<b>{phaseTotal(p)} pts</b>
									</div>
									<div class="grid">
										<div class="cell"><div class="l">Out</div><div class="v">{p.match_outcome_points}</div></div>
										<div class="cell"><div class="l">Exact</div><div class="v exact">{p.exact_score_points}</div></div>
										<div class="cell"><div class="l">Bonus</div><div class="v bonus">{p.hybrid_bonus_points}</div></div>
										<div class="cell"><div class="l">Brkt</div><div class="v bracket">{phaseBracketSum(p)}</div></div>
									</div>
								</div>
							{/each}
						</div>
					{/if}
				{:else}
					<div style="padding: 24px; text-align: center; font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">
						No standings yet
					</div>
				{/each}
			</div>
		</div>
	</PnPageShell>
{/if}
