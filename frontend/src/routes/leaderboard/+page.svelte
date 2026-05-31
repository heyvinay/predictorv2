<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import {
		startPolling,
		stopPolling,
		leaderboard,
		leaderboardLoading,
		lastCalculated,
		totalParticipants,
		activeEntryPosition,
		leaderboardPhase,
		type LeaderboardPhase
	} from '$stores/leaderboard';
	import { getGroupTotal, type PhaseBreakdown, type PointBreakdown } from '$types';
	import Sparkline from '$components/Sparkline.svelte';
	import { stubRankTrajectory } from '$lib/utils/widgetFallbacks';
	import { loadEntries, entrySettings } from '$stores/entries';
	import { phase1Deadline } from '$stores/phase';
	import { isYouRow, shouldShowReference } from '$lib/utils/leaderboard';
	import { pageTitle } from '$stores/pageTitle';

	// Flag-gated: when true, restore the full standings table below.
	const SHOW_CONTENT = false;

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	onMount(() => {
		pageTitle.set('Standings');
		if ($isAuthenticated && SHOW_CONTENT) {
			startPolling(60000);
		}
	});

	// Pull entry settings as soon as $user.id resolves. The conditional
	// reference column on each row needs $entrySettings to be populated.
	let entriesLoadStarted = false;
	$: if ($isAuthenticated && $user?.id && !entriesLoadStarted) {
		entriesLoadStarted = true;
		void loadEntries($user.id);
	}

	onDestroy(() => {
		stopPolling();
	});

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

	/** Tournament-start date for the pre-kickoff "Standings open at…" copy.
	 *  Short, weekday-anchored format (e.g. "Thu, 11 Jun") — readable on
	 *  mobile without taking the hero off the fold. */
	function formatKickoff(iso: string | null): string {
		if (!iso) return '';
		try {
			return new Date(iso).toLocaleDateString(undefined, {
				weekday: 'short',
				day: 'numeric',
				month: 'short'
			});
		} catch {
			return '';
		}
	}

	// Match-cell value for the current phase filter
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

	// Per-row breakdown buckets. Single-phase production model means
	// `phase2` is dormant (always zero) — the array shape stays intact so
	// Phase 2 data still flows through if admin ever activates it, but the
	// user-facing labels are neutral (no "Phase I/II" language anywhere).
	const DETAIL_PHASES: Array<{ k: 'phase1' | 'phase2'; name: string }> = [
		{ k: 'phase1', name: 'Pre-tournament' },
		{ k: 'phase2', name: 'Knockout' }
	];

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

	function posBadgeClass(position: number): string {
		if (position === 1) return 'position-badge gold';
		if (position === 2) return 'position-badge silver';
		if (position === 3) return 'position-badge bronze';
		return 'position-badge';
	}
</script>

<svelte:head>
	<title>Standings — Predictor v2</title>
</svelte:head>

{#if $isAuthenticated && !SHOW_CONTENT}
	<div class="hero min-h-[60vh]">
		<div class="hero-content text-center">
			<div class="max-w-md">
				<h2 class="font-display text-3xl tracking-wide">Standings open at kickoff</h2>
				<p class="mt-3 text-base-content/60">
					{#if $phase1Deadline}
						We start scoring once the first match begins —
						<span class="text-warning-text font-semibold">{formatKickoff($phase1Deadline)}</span>.
					{:else}
						We start scoring once the first match of the tournament begins.
					{/if}
				</p>
				<a href="/entries" class="btn btn-primary btn-lg mt-6 shadow-glow-gold">
					Lock in your predictions
				</a>
			</div>
		</div>
	</div>
{/if}

{#if $isAuthenticated && SHOW_CONTENT}
	<div class="container mx-auto mobile-padding py-6">
		<!-- Header (phase tabs removed — single-phase production model) -->
		<div class="flex items-center justify-between flex-wrap gap-3 mb-6">
			<div>
				<h1 class="text-3xl sm:text-4xl font-display tracking-wide">Standings</h1>
				<p class="text-sm text-base-content/50 mt-1">
					{$totalParticipants || $leaderboard.length} players
					{#if $leaderboardLoading}· updating…{:else if $lastCalculated}· updated {formatLastUpdated($lastCalculated)}{/if}
				</p>
			</div>
		</div>

		<!-- Your position -->
		{#if $activeEntryPosition}
			<div class="stadium-card p-5 mb-6">
				<div class="flex items-center gap-4 flex-wrap">
					<div class="text-center">
						<div class="font-display text-5xl tracking-wide leading-none text-primary">
							{yourRank}<span class="text-xl text-base-content/50 align-top">{ordinal(yourRank)}</span>
						</div>
					</div>
					<div class="flex-1 min-w-[160px]">
						<div class="font-semibold flex items-center gap-2">
							{$activeEntryPosition.entry_name}
							<span class="badge badge-error badge-sm">YOU</span>
						</div>
						<div class="text-xs text-base-content/50 mt-0.5">
							{$activeEntryPosition.user_name} · {yourExact} exact · {yourOutcomes} outcomes
							{#if yourMovement !== 0}
								· <span class={yourMovement > 0 ? 'text-success' : 'text-error'}>{yourMovement > 0 ? '▲' : '▼'}{Math.abs(yourMovement)}</span>
							{/if}
						</div>
					</div>
					<div class="flex gap-6">
						<div class="text-center">
							<div class="stat-title">Total</div>
							<div class="font-display text-2xl tracking-wide">{yourPoints}</div>
						</div>
						<div class="text-center">
							<div class="stat-title">To #1</div>
							<div class="font-display text-2xl tracking-wide">{toFirst < 0 ? toFirst : toFirst === 0 ? '—' : `+${toFirst}`}</div>
						</div>
					</div>
				</div>
			</div>
		{/if}

		<!-- Standings table -->
		<div class="stadium-card no-glow overflow-hidden">
			<div class="overflow-x-auto">
				<table class="table table-sm">
					<thead>
						<tr class="text-xs uppercase tracking-wider text-base-content/40">
							<th>#</th>
							<th>Player</th>
							<th class="text-center hidden md:table-cell">Exact</th>
							<th class="text-center hidden md:table-cell">Outcome</th>
							<th class="text-center hidden md:table-cell">Bonus</th>
							<th class="text-center hidden md:table-cell">Bracket</th>
							<th class="text-center hidden lg:table-cell">Trend · 7d</th>
							<th class="text-right">Total</th>
							<th class="text-right">Move</th>
							<th></th>
						</tr>
					</thead>
					<tbody>
						{#each $leaderboard as r (r.entry_id)}
							{@const isYou = isYouRow(r, $user?.id)}
							{@const showRef = shouldShowReference(r, $entrySettings, $user?.id, $user?.is_admin ?? false)}
							{@const traj = stubRankTrajectory(r.entry_id, r.position, $totalParticipants || $leaderboard.length || 32)}
							{@const isOpen = expanded.has(r.entry_id)}
							<tr
								class="cursor-pointer hover:bg-base-200/40 {isYou ? 'bg-primary/10' : ''}"
								on:click={() => toggle(r.entry_id)}
							>
								<td>
									<span class="{posBadgeClass(r.position)} !w-8 !h-8 !text-sm">{r.position}</span>
								</td>
								<td>
									<a href="/profile/{r.user_id}" class="hover:text-primary" on:click|stopPropagation>
										<div class="font-semibold flex items-center gap-1.5">
											{r.entry_name}
											{#if isYou}<span class="badge badge-error badge-xs">YOU</span>{/if}
											{#if showRef}<span class="text-[10px] font-mono text-base-content/40">{r.entry_reference}</span>{/if}
										</div>
										<div class="text-xs text-base-content/40">{r.user_name}</div>
									</a>
								</td>
								<td class="text-center hidden md:table-cell text-primary">{exactPts(r.breakdown, $leaderboardPhase)}</td>
								<td class="text-center hidden md:table-cell">{outcomePts(r.breakdown, $leaderboardPhase)}</td>
								<td class="text-center hidden md:table-cell text-accent">{bonusPts(r.breakdown, $leaderboardPhase)}</td>
								<td class="text-center hidden md:table-cell text-info">{bracketPts(r.breakdown, $leaderboardPhase)}</td>
								<td class="hidden lg:table-cell {isYou ? 'text-error' : 'text-base-content/60'}" style="width: 90px;">
									<Sparkline ranks={traj.ranks} maxRank={traj.maxRank} width={80} height={22} />
								</td>
								<td class="text-right font-display text-lg tracking-wide">{r.total_points}</td>
								<td class="text-right">
									{#if r.movement > 0}<span class="text-success">▲{r.movement}</span>
									{:else if r.movement < 0}<span class="text-error">▼{Math.abs(r.movement)}</span>
									{:else}<span class="text-base-content/30">—</span>{/if}
								</td>
								<td class="text-base-content/30">{isOpen ? '▴' : '▾'}</td>
							</tr>
							{#if isOpen}
								<tr class="bg-base-200/30">
									<td colspan="10">
										<div class="grid grid-cols-1 sm:grid-cols-2 gap-4 p-2">
											{#each DETAIL_PHASES as ph (ph.k)}
												{@const p = r.breakdown[ph.k]}
												<div class="rounded-lg bg-base-300/30 p-3">
													<div class="flex items-center justify-between mb-2">
														<span class="text-xs uppercase tracking-wider text-base-content/50">{ph.name}</span>
														<b class="font-display tracking-wide">{phaseTotal(p)} pts</b>
													</div>
													<div class="grid grid-cols-4 gap-2 text-center">
														<div><div class="stat-title">Outcome</div><div class="font-semibold">{p.match_outcome_points}</div></div>
														<div><div class="stat-title">Exact</div><div class="font-semibold text-primary">{p.exact_score_points}</div></div>
														<div><div class="stat-title">Bonus</div><div class="font-semibold text-accent">{p.hybrid_bonus_points}</div></div>
														<div><div class="stat-title">Bracket</div><div class="font-semibold text-info">{phaseBracketSum(p)}</div></div>
													</div>
												</div>
											{/each}
										</div>
									</td>
								</tr>
							{/if}
						{:else}
							<tr><td colspan="10" class="text-center py-8 text-base-content/40">No standings yet</td></tr>
						{/each}
					</tbody>
				</table>
			</div>
		</div>
	</div>
{/if}
