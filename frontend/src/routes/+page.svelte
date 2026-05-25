<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import {
		fetchAllFixtures,
		liveFixtures,
		upcomingFixtures,
		formatKickoff,
		getTimeUntilKickoff
	} from '$stores/fixtures';
	import {
		fetchLeaderboard,
		activeEntryPosition,
		leaderboard,
		totalParticipants
	} from '$stores/leaderboard';
	import { phase1Countdown } from '$stores/phase';
	import { loadEntries, activeEntryId } from '$stores/entries';

	import Sparkline from '$components/Sparkline.svelte';
	import { teamCode } from '$lib/utils/teamCodes';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import {
		stubRankTrajectory,
		stubBracketExposure,
		stubBonusHaul,
		stubHotPick,
		stubSteepestClimb
	} from '$lib/utils/widgetFallbacks';
	import {
		getMyRankTrajectory,
		getSteepestClimbers,
		type RankTrajectoryResponse,
		type SteepestClimbersResponse
	} from '$api/leaderboard';
	import {
		getAgreements,
		getBracketExposure,
		type BracketExposureResponse,
		type FixtureAgreement
	} from '$api/predictions';
	import { fetchMatchPredictions, predictionsByFixture } from '$stores/predictions';
	import type { Fixture } from '$types';

	// Live-ticker projection over a Fixture row. The score_scheduler writes
	// real numbers into f.score for IN_PLAY / HALFTIME matches via the
	// Football-Data.org provider. Before the first sync of a live match,
	// f.score may briefly be null — render as 0–0 (correct by definition).
	function liveOf(f: Fixture): { homeScore: number; awayScore: number; minute: number; half: 1 | 2 } {
		const minute = f.minute ?? 0;
		return {
			homeScore: f.score?.home_score ?? 0,
			awayScore: f.score?.away_score ?? 0,
			minute,
			half: minute > 45 ? 2 : 1
		};
	}

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	// Real backend-driven widget data. All start null and the fallbacks cover
	// for them while the API call is in flight or if the endpoint is
	// unavailable. Each value gates its widget independently.
	let realTrajectory: RankTrajectoryResponse | null = null;
	let realClimbers: SteepestClimbersResponse | null = null;
	let realAgreements: FixtureAgreement[] | null = null;
	let realExposure: BracketExposureResponse | null = null;

	onMount(async () => {
		if ($isAuthenticated) {
			await Promise.all([fetchAllFixtures(), fetchLeaderboard()]);
		}
	});

	// Load entries as soon as $user.id resolves.
	let entriesLoadStarted = false;
	$: if ($isAuthenticated && $user?.id && !entriesLoadStarted) {
		entriesLoadStarted = true;
		void loadEntries($user.id);
	}

	// Fire entry-scoped fetches once the active entry id resolves.
	let entryDepsLoadStarted = false;
	$: if ($activeEntryId && !entryDepsLoadStarted) {
		entryDepsLoadStarted = true;
		const entryId = $activeEntryId;
		void (async () => {
			fetchMatchPredictions();
			try {
				[realTrajectory, realClimbers, realAgreements, realExposure] = await Promise.all([
					getMyRankTrajectory(7, entryId),
					getSteepestClimbers(7, 32),
					getAgreements(entryId),
					getBracketExposure(entryId, 'phase_1')
				]);
			} catch (_e) {
				realTrajectory = null;
				realClimbers = null;
				realAgreements = null;
				realExposure = null;
			}
		})();
	}

	// ---- Derived values from existing stores -------------------------------
	$: rank = $activeEntryPosition?.position ?? 0;
	$: totalPlayers = $totalParticipants || $leaderboard.length || 32;
	$: totalPoints = $activeEntryPosition?.total_points ?? 0;
	$: exactCount = $activeEntryPosition?.exact_scores ?? 0;
	$: correctOutcomes = $activeEntryPosition?.correct_outcomes ?? 0;
	$: totalScored = $activeEntryPosition?.breakdown?.total_predictions ?? 0;
	$: movement = $activeEntryPosition?.movement ?? 0;
	$: userId = $user?.id ?? 'anonymous';
	$: userName = $user?.name ?? 'Player';
	$: firstName = userName.split(' ')[0];

	// Outcome hit rate (correct / total scored)
	$: outcomeRate = totalScored > 0 ? Math.round((correctOutcomes / totalScored) * 100) : 0;

	// Top 5 of leaderboard
	$: topFive = $leaderboard.slice(0, 5);

	// Rivals: ±1 around the user's active entry.
	$: rivals = (() => {
		const idx = $leaderboard.findIndex((e) => e.entry_id === $activeEntryId);
		if (idx === -1) return [];
		const start = Math.max(0, idx - 1);
		const end = Math.min($leaderboard.length, idx + 2);
		return $leaderboard.slice(start, end);
	})();

	// ---- Widgets (real backend data, fallback while loading) ---------------
	$: trajectory = (() => {
		if (realTrajectory && realTrajectory.points.length >= 2) {
			return {
				ranks: realTrajectory.points.map((p) => p.position),
				maxRank: realTrajectory.total_participants
			};
		}
		return stubRankTrajectory(userId, rank || 1, totalPlayers);
	})();
	$: bracketExposure = (() => {
		if (realExposure) {
			return {
				pointsAvailable: realExposure.points_available,
				picksLocked: realExposure.picks_locked,
				picksTotal: realExposure.picks_total,
				finalPick:
					realExposure.final_winner && realExposure.final_opponent
						? {
							winnerCode: teamCode(realExposure.final_winner),
							opponentCode: teamCode(realExposure.final_opponent)
						}
						: null
			};
		}
		return stubBracketExposure(userId);
	})();
	$: bonusHaul = (() => {
		const b = $activeEntryPosition?.breakdown;
		if (b) {
			return {
				fromExact: b.exact_score_points,
				fromUnderdogs: b.hybrid_bonus_points,
				total: b.exact_score_points + b.hybrid_bonus_points
			};
		}
		return stubBonusHaul(userId, exactCount);
	})();
	$: climb = (() => {
		if (realClimbers && realClimbers.entries.length > 0) {
			const me = realClimbers.entries.find((e) => e.entry_id === $activeEntryId);
			const myRank = me
				? realClimbers.entries.findIndex((e) => e.entry_id === $activeEntryId) + 1
				: realClimbers.entries.length + 1;
			return {
				yourPlaces: me?.places ?? movement,
				rankAmongClimbers: myRank,
				totalPlayers
			};
		}
		return stubSteepestClimb(userId, movement, totalPlayers);
	})();

	// Hot pick: the user's predicted-but-not-yet-locked fixture with the
	// lowest exact-agreement count (rarest = highest expected value).
	$: hotPick = (() => {
		if (realAgreements && realAgreements.length > 0) {
			const openIds = new Set($upcomingFixtures.map((f) => f.id));
			const openAgreements = realAgreements.filter((a) => openIds.has(a.fixture_id));
			if (openAgreements.length > 0) {
				const rarest = openAgreements.reduce(
					(best, a) => (a.agrees_exact < best.agrees_exact ? a : best),
					openAgreements[0]
				);
				const fixture = $upcomingFixtures.find((f) => f.id === rarest.fixture_id);
				const pred = $predictionsByFixture.get(rarest.fixture_id);
				if (fixture && pred) {
					const rarity = rarest.total > 0 ? 1 - rarest.agrees_exact / rarest.total : 0;
					return {
						fixtureId: rarest.fixture_id,
						homeCode: teamCode(fixture.home_team),
						awayCode: teamCode(fixture.away_team),
						yourScore: [pred.home_score, pred.away_score] as [number, number],
						agreesExact: rarest.agrees_exact,
						total: rarest.total,
						potentialPoints: 15,
						multiplier: +(1 + rarity * 1.5).toFixed(1)
					};
				}
			}
		}
		const stubCandidates = $upcomingFixtures.slice(0, 5).map((f) => ({
			fixtureId: f.id,
			homeCode: teamCode(f.home_team),
			awayCode: teamCode(f.away_team),
			yourScore: [2, 1] as [number, number]
		}));
		return stubHotPick(stubCandidates);
	})();

	// ---- Countdown ---------------------------------------------------------
	$: nextFixture = $upcomingFixtures[0] ?? null;
	$: countdownText = nextFixture
		? getTimeUntilKickoff(nextFixture.kickoff)
		: $phase1Countdown ?? '—';

	function ordinal(n: number): string {
		if (n % 100 >= 11 && n % 100 <= 13) return 'th';
		switch (n % 10) {
			case 1: return 'st';
			case 2: return 'nd';
			case 3: return 'rd';
			default: return 'th';
		}
	}

	function rowState(f: Fixture): 'open' | 'soon' | 'locked' {
		if (f.is_locked) return 'locked';
		if (f.time_until_lock !== null && f.time_until_lock < 60 * 60 * 1000) return 'soon';
		return 'open';
	}

	function stateBadge(state: 'open' | 'soon' | 'locked'): string {
		if (state === 'locked') return 'badge-ghost';
		if (state === 'soon') return 'badge-warning';
		return 'badge-success';
	}

	function shortKickoff(iso: string): { day: string; time: string } {
		const d = new Date(iso);
		const day = d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
		const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
		return { day, time };
	}

	function gapLabel(theirPts: number, yourPts: number): string {
		const diff = yourPts - theirPts;
		if (diff > 0) return `+${diff}`;
		if (diff < 0) return `${diff}`;
		return '—';
	}
</script>

<svelte:head>
	<title>Dashboard - Predictor v2</title>
</svelte:head>

{#if $isAuthenticated}
	<div class="container mx-auto mobile-padding py-6 space-y-6">
		<!-- Welcome -->
		<div class="flex items-end justify-between flex-wrap gap-2">
			<div>
				<h1 class="text-3xl sm:text-4xl font-display tracking-wide">Welcome back, {firstName}</h1>
				<p class="text-sm text-base-content/50 mt-1">
					{#if rank}You're {rank}{ordinal(rank)} of {totalPlayers}{:else}World Cup 2026 Predictions{/if}
				</p>
			</div>
			<a href={$activeEntryId ? `/entries/${$activeEntryId}` : '/entries'} class="btn btn-primary btn-sm">Make predictions</a>
		</div>

		<!-- KPI row -->
		<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
			<div class="stat-card">
				<p class="stat-title">Rank</p>
				<p class="stat-value text-primary">{rank || '—'}<span class="text-base text-base-content/40">/{totalPlayers}</span></p>
				<p class="text-xs mt-1">
					{#if movement > 0}<span class="text-success">▲ {movement}</span>
					{:else if movement < 0}<span class="text-error">▼ {Math.abs(movement)}</span>
					{:else}<span class="text-base-content/40">—</span>{/if} since last update
				</p>
			</div>
			<div class="stat-card">
				<p class="stat-title">Total Points</p>
				<p class="stat-value">{totalPoints}</p>
				<p class="text-xs text-base-content/40 mt-1">{exactCount} exact · {correctOutcomes} outcomes</p>
			</div>
			<div class="stat-card">
				<p class="stat-title">Exact</p>
				<p class="stat-value text-success">{exactCount}<span class="text-base text-base-content/40">/{totalScored || '—'}</span></p>
				<p class="text-xs text-base-content/40 mt-1">+{exactCount * 10} pts</p>
			</div>
			<div class="stat-card">
				<p class="stat-title">Outcomes</p>
				<p class="stat-value">{correctOutcomes}<span class="text-base text-base-content/40">/{totalScored || '—'}</span></p>
				<p class="text-xs text-base-content/40 mt-1">{outcomeRate}% hit rate</p>
			</div>
			<div class="stat-card col-span-2 sm:col-span-1">
				<p class="stat-title">Bonus Haul</p>
				<p class="stat-value text-accent">{bonusHaul.total}</p>
				<p class="text-xs text-base-content/40 mt-1">{bonusHaul.fromExact} exact + {bonusHaul.fromUnderdogs} underdog</p>
			</div>
		</div>

		<!-- Live + countdown/trend -->
		<div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
			<!-- Live matches -->
			<div class="stadium-card no-glow p-5 lg:col-span-2">
				<div class="flex items-center justify-between mb-4">
					<h2 class="text-lg font-display tracking-wide flex items-center gap-2">
						<span class="inline-block w-2 h-2 rounded-full bg-error animate-pulse-soft"></span>
						Live Now
					</h2>
					<span class="text-xs text-base-content/40">{$liveFixtures.length} in progress</span>
				</div>
				{#if $liveFixtures.length === 0}
					<p class="text-center py-8 text-sm text-base-content/40">No live matches right now</p>
				{:else}
					<div class="space-y-3">
						{#each $liveFixtures as f (f.id)}
							{@const live = liveOf(f)}
							<div class="flex items-center gap-3 p-3 rounded-xl bg-base-300/30">
								<div class="flex items-center gap-2 flex-1 min-w-0">
									{#if hasFlag(f.home_team)}<img src={getFlagUrl(f.home_team, 'sm')} alt="" class="w-6 h-auto rounded-sm" />{/if}
									<span class="font-semibold truncate">{f.home_team}</span>
								</div>
								<div class="text-center px-3">
									<div class="font-display text-2xl tracking-wide">{live.homeScore}–{live.awayScore}</div>
									<div class="text-[10px] text-error font-mono">{live.minute}′ · {live.half === 1 ? '1H' : '2H'}</div>
								</div>
								<div class="flex items-center gap-2 flex-1 min-w-0 justify-end">
									<span class="font-semibold truncate text-right">{f.away_team}</span>
									{#if hasFlag(f.away_team)}<img src={getFlagUrl(f.away_team, 'sm')} alt="" class="w-6 h-auto rounded-sm" />{/if}
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>

			<!-- Next lock + trajectory -->
			<div class="space-y-4">
				<div class="stadium-card no-glow p-5">
					<p class="stat-title mb-1">Next Lock</p>
					{#if nextFixture}
						<div class="font-display text-xl tracking-wide">{teamCode(nextFixture.home_team)} · {teamCode(nextFixture.away_team)}</div>
						<div class="text-xs text-base-content/50 mb-2">{formatKickoff(nextFixture.kickoff)}</div>
						<div class="countdown-timer inline-block">{countdownText}</div>
					{:else}
						<p class="text-sm text-base-content/40">No upcoming matches</p>
					{/if}
				</div>

				<div class="stadium-card no-glow p-5 {movement >= 0 ? 'text-success' : 'text-error'}">
					<div class="flex items-center justify-between mb-2 text-base-content">
						<p class="stat-title">Rank trajectory · 7d</p>
						<span class="text-xs text-base-content/50">{trajectory.ranks[0]} → <b class="text-base-content">{rank || trajectory.ranks[6]}</b></span>
					</div>
					<Sparkline ranks={trajectory.ranks} maxRank={trajectory.maxRank} width={240} height={80} />
					<div class="flex items-center justify-between mt-2 text-xs text-base-content/50">
						<span>{movement >= 0 ? 'Climber' : 'Slipped'} · pool of {totalPlayers}</span>
						<b class="text-base-content">{movement > 0 ? '▲' : movement < 0 ? '▼' : '—'} {Math.abs(movement)} places</b>
					</div>
				</div>
			</div>
		</div>

		<!-- Insights: rivals, hot pick, exposure -->
		<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
			<!-- Closest rivals -->
			<div class="stadium-card no-glow p-5">
				<h2 class="text-sm font-semibold uppercase tracking-wider text-base-content/60 mb-3">Closest Rivals</h2>
				{#each rivals as r (r.entry_id)}
					{@const isYou = r.entry_id === $activeEntryId}
					<div class="flex items-center gap-3 py-2 {isYou ? 'text-primary' : ''}">
						<span class="font-mono text-sm w-6">{r.position}</span>
						<div class="flex-1 min-w-0">
							<div class="font-medium truncate">{r.entry_name}</div>
							<div class="text-xs text-base-content/40">{r.user_name}{isYou ? ' · YOU' : ''}</div>
						</div>
						<span class="text-xs {gapLabel(r.total_points, totalPoints).startsWith('+') ? 'text-success' : gapLabel(r.total_points, totalPoints) === '—' ? 'text-base-content/40' : 'text-error'}">
							{isYou ? '—' : gapLabel(r.total_points, totalPoints)}
						</span>
						<span class="font-display text-lg tracking-wide">{r.total_points}</span>
					</div>
				{:else}
					<p class="text-sm text-base-content/40 py-2">No leaderboard data yet</p>
				{/each}
			</div>

			<!-- Hot pick -->
			<div class="stadium-card no-glow p-5">
				<h2 class="text-sm font-semibold uppercase tracking-wider text-base-content/60 mb-3">Your Hottest Open Pick</h2>
				{#if hotPick}
					<div class="flex items-center gap-2 mb-3 font-semibold">
						{#if hasFlag(hotPick.homeCode)}<img src={getFlagUrl(hotPick.homeCode, 'sm')} alt="" class="w-6 h-auto rounded-sm" />{/if}
						{hotPick.homeCode}
						<span class="text-xs text-base-content/40 font-mono">vs</span>
						{#if hasFlag(hotPick.awayCode)}<img src={getFlagUrl(hotPick.awayCode, 'sm')} alt="" class="w-6 h-auto rounded-sm" />{/if}
						{hotPick.awayCode}
					</div>
					<div class="flex items-baseline gap-3">
						<span class="font-display text-3xl tracking-wide text-primary">{hotPick.yourScore[0]}–{hotPick.yourScore[1]}</span>
						<div class="text-xs text-base-content/50">
							<b>{hotPick.agreesExact} of {hotPick.total}</b> agree exact<br />
							yield <b>+{hotPick.potentialPoints} pts</b> · <b>{hotPick.multiplier}×</b> avg
						</div>
					</div>
				{:else}
					<p class="text-sm text-base-content/40">No open fixtures available.</p>
				{/if}
			</div>

			<!-- Bracket exposure -->
			<div class="stadium-card no-glow p-5">
				<h2 class="text-sm font-semibold uppercase tracking-wider text-base-content/60 mb-3">Bracket Exposure</h2>
				<div class="flex items-baseline gap-3">
					<span class="font-display text-3xl tracking-wide text-accent">{bracketExposure.pointsAvailable}</span>
					<div class="text-xs text-base-content/50">
						pts available · <b>{bracketExposure.picksLocked} of {bracketExposure.picksTotal}</b> picks<br />
						{#if bracketExposure.finalPick}
							Final · <b>{bracketExposure.finalPick.winnerCode}</b> over <b>{bracketExposure.finalPick.opponentCode}</b>
						{/if}
					</div>
				</div>
			</div>
		</div>

		<!-- Top 5 + Upcoming -->
		<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
			<!-- Top 5 -->
			<div class="stadium-card no-glow p-5">
				<div class="flex items-center justify-between mb-3">
					<h2 class="text-lg font-display tracking-wide">Top 5</h2>
					<a href="/leaderboard" class="text-xs text-primary hover:underline">Full table →</a>
				</div>
				{#each topFive as e, i (e.entry_id)}
					<div class="flex items-center gap-3 py-2 {e.entry_id === $activeEntryId ? 'text-primary' : ''}">
						<span class="{i === 0 ? 'position-badge gold' : 'position-badge'} !w-8 !h-8 !text-sm">{e.position}</span>
						<div class="flex-1 min-w-0">
							<div class="font-medium truncate">{e.entry_name}</div>
							<div class="text-xs text-base-content/40">{e.user_name} · {e.exact_scores} exact</div>
						</div>
						<span class="font-display text-lg tracking-wide">{e.total_points}</span>
					</div>
				{:else}
					<p class="text-sm text-base-content/40 py-2">Leaderboard not loaded yet</p>
				{/each}
			</div>

			<!-- Upcoming -->
			<div class="stadium-card no-glow p-5">
				<div class="flex items-center justify-between mb-3">
					<h2 class="text-lg font-display tracking-wide">Up Next</h2>
					<a href={$activeEntryId ? `/entries/${$activeEntryId}` : '/entries'} class="text-xs text-primary hover:underline">Predict →</a>
				</div>
				<div class="overflow-x-auto">
					<table class="table table-sm">
						<tbody>
							{#each $upcomingFixtures.slice(0, 5) as f (f.id)}
								{@const k = shortKickoff(f.kickoff)}
								{@const state = rowState(f)}
								<tr>
									<td class="text-xs"><b>{k.day}</b><br />{k.time}</td>
									<td class="font-medium">{teamCode(f.home_team)} <span class="text-base-content/30 text-xs">vs</span> {teamCode(f.away_team)}</td>
									<td class="text-xs text-base-content/40">{f.group ? `Group ${f.group}` : f.stage}</td>
									<td class="text-right"><span class="badge badge-sm {stateBadge(state)}">{state === 'locked' ? 'Locked' : state === 'soon' ? 'Soon' : 'Open'}</span></td>
								</tr>
							{:else}
								<tr><td colspan="4" class="text-center py-6 text-base-content/40">No upcoming matches</td></tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		</div>
	</div>
{/if}
