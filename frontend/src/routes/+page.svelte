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
		myLeaderboardRows,
		leaderboard,
		totalParticipants
	} from '$stores/leaderboard';
	import { phase1Countdown, phase1Deadline } from '$stores/phase';
	import { loadEntries, activeEntryId, activeEntry } from '$stores/entries';
	import { get } from 'svelte/store';

	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import PnFlag from '$components/panini/PnFlag.svelte';
	import PnSparkline from '$components/panini/PnSparkline.svelte';
	import { teamCode } from '$lib/utils/teamCodes';
	import {
		stubRankTrajectory,
		stubBracketExposure,
		stubBonusHaul,
		stubHotPick,
		stubSteepestClimb
	} from '$lib/stubs/panini';
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
	import type { Fixture, LeaderboardEntry } from '$types';

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

	// Real backend-driven widget data (replaces stubRankTrajectory +
	// stubSteepestClimb + stubSocialSignal + stubHotPick). All start null
	// and the stubs cover for them while the API call is in flight or if
	// the endpoint is unavailable. Each value gates its widget independently.
	let realTrajectory: RankTrajectoryResponse | null = null;
	let realClimbers: SteepestClimbersResponse | null = null;
	let realAgreements: FixtureAgreement[] | null = null;
	let realExposure: BracketExposureResponse | null = null;

	onMount(async () => {
		if ($isAuthenticated) {
			// Non-entry fetches run unconditionally. Entry-scoped fetches
			// (trajectory, agreements, bracket exposure, match predictions)
			// run in the reactive block below once $activeEntryId resolves.
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

	// Rivals: ±1 around the user's active entry. Falls back gracefully near
	// edges. Keyed by entry_id — when a user holds several entries, the
	// rivals widget anchors to the one currently in focus.
	$: rivals = (() => {
		const idx = $leaderboard.findIndex((e) => e.entry_id === $activeEntryId);
		if (idx === -1) return [];
		const start = Math.max(0, idx - 1);
		const end = Math.min($leaderboard.length, idx + 2);
		return $leaderboard.slice(start, end);
	})();

	// ---- Stubbed widgets ---------------------------------------------------
	// Rank trajectory: real backend data once we have >= 2 days of snapshots;
	// stub fallback while history accumulates (newly-installed deployment).
	$: trajectory = (() => {
		if (realTrajectory && realTrajectory.points.length >= 2) {
			return {
				ranks: realTrajectory.points.map((p) => p.position),
				maxRank: realTrajectory.total_participants
			};
		}
		return stubRankTrajectory(userId, rank || 1, totalPlayers);
	})();
	// Bracket exposure: real backend computation when available; stub otherwise.
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
	// Bonus haul: real breakdown of points earned BEYOND the base 5-per-correct-
	// outcome. `fromExact` is the exact-score-bonus column, `fromUnderdogs`
	// maps to the hybrid_bonus_points column (the rarity bonus — "underdog"
	// in product language). Both are real values from the cached
	// PointBreakdown that ships with the user's leaderboard row, so no
	// extra fetch is needed.
	$: bonusHaul = (() => {
		const b = $activeEntryPosition?.breakdown;
		if (b) {
			return {
				fromExact: b.exact_score_points,
				fromUnderdogs: b.hybrid_bonus_points,
				total: b.exact_score_points + b.hybrid_bonus_points
			};
		}
		// Fallback while the leaderboard is loading — keep the stub so the
		// KPI strip doesn't flash zeros.
		return stubBonusHaul(userId, exactCount);
	})();
	// Steepest climb: real climbers if available, stub fallback otherwise.
	// Climbers are keyed by entry_id, so a user with two climbing entries
	// can legitimately appear twice. Anchor to the active entry's row.
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
	// lowest exact-agreement count. Lowest = rarest = highest expected value
	// if it lands. Uses real agreement counts + the user's real picks; falls
	// back to the stub when either is unavailable.
	$: hotPick = (() => {
		if (realAgreements && realAgreements.length > 0) {
			// Intersect agreements with upcoming-open fixtures + the user's actual picks.
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
		// Stub fallback while predictions / agreements load or for users
		// who haven't predicted any open fixtures yet.
		const stubCandidates = $upcomingFixtures.slice(0, 5).map((f) => ({
			fixtureId: f.id,
			homeCode: teamCode(f.home_team),
			awayCode: teamCode(f.away_team),
			yourScore: [2, 1] as [number, number]
		}));
		return stubHotPick(stubCandidates);
	})();

	// ---- Countdown digits --------------------------------------------------
	// Use the closest upcoming fixture as the "next lock"; fall back to
	// phase 1 deadline if no fixtures are loaded yet.
	$: nextFixture = $upcomingFixtures[0] ?? null;
	$: countdownText = nextFixture
		? getTimeUntilKickoff(nextFixture.kickoff)
		: $phase1Countdown ?? '—';

	function parseCountdown(s: string): { d: number; h: number; m: number; sec: number } {
		const out = { d: 0, h: 0, m: 0, sec: 0 };
		if (!s) return out;
		const dm = s.match(/(\d+)d/);
		const hm = s.match(/(\d+)h/);
		const mm = s.match(/(\d+)m/);
		const sm = s.match(/(\d+)s/);
		if (dm) out.d = +dm[1];
		if (hm) out.h = +hm[1];
		if (mm) out.m = +mm[1];
		if (sm) out.sec = +sm[1];
		return out;
	}
	$: cd = parseCountdown(countdownText);

	function pad(n: number): string {
		return String(n).padStart(2, '0');
	}

	// ---- Strip labels ------------------------------------------------------
	$: stripLive = (() => {
		const f = $liveFixtures[0];
		if (!f) return null;
		const score = liveOf(f);
		return `<b>LIVE</b> · ${teamCode(f.home_team)} ${score.homeScore}–${score.awayScore} ${teamCode(f.away_team)} · ${score.minute}′`;
	})();
	$: stripLock = nextFixture
		? `<b>Next lock</b> ${teamCode(nextFixture.home_team)}–${teamCode(nextFixture.away_team)} in ${countdownText}`
		: null;
	$: stripYou = totalPlayers
		? `<b>You</b> · ${rank}${ordinal(rank)} of ${totalPlayers} · ${totalPoints} pts${movement !== 0 ? ` · ${movement > 0 ? '▲' : '▼'}${Math.abs(movement)}` : ''}`
		: null;

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

	function shortKickoff(iso: string): { day: string; time: string } {
		const d = new Date(iso);
		const day = d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
		const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
		return { day, time };
	}

	function gapVariant(theirPts: number, yourPts: number): { label: string; cls: string } {
		const diff = yourPts - theirPts;
		if (diff > 0) return { label: `+${diff}`, cls: 'up' };
		if (diff < 0) return { label: `${diff}`, cls: 'dn' };
		return { label: '—', cls: 'eq' };
	}
</script>

<svelte:head>
	<title>Dashboard — Predictor</title>
</svelte:head>

{#if $isAuthenticated}
	<PnPageShell liveLabel={stripLive} lockLabel={stripLock} youLabel={stripYou}>
		<!-- ============================================================
		     DESKTOP
		     ============================================================ -->
		<div class="pn-desk">
			<!-- KPI ROW -->
			<section class="pn-kpi-row">
				<div class="pn-kpi">
					<div>
						<div class="l"><span class="pip red"></span>Rank</div>
						<div class="v">
							<span class="red">{rank || '—'}</span><span class="sm">/{totalPlayers}</span>
						</div>
					</div>
					<div class="sub">
						{#if movement > 0}<span class="up">▲ {movement}</span>
						{:else if movement < 0}<span class="dn">▼ {Math.abs(movement)}</span>
						{:else}—{/if}
						· last update
					</div>
				</div>
				<div class="pn-kpi">
					<div>
						<div class="l"><span class="pip"></span>Total</div>
						<div class="v">{totalPoints}</div>
					</div>
					<div class="sub"><b>{exactCount}</b> exact + <b>{correctOutcomes}</b> outcomes</div>
				</div>
				<div class="pn-kpi">
					<div>
						<div class="l"><span class="pip green"></span>Exact</div>
						<div class="v">
							<span class="green">{exactCount}</span><span class="sm">/{totalScored || '—'}</span>
						</div>
					</div>
					<div class="sub"><b>+{exactCount * 10}</b> pts from exact scores</div>
				</div>
				<div class="pn-kpi">
					<div>
						<div class="l"><span class="pip"></span>Outcomes</div>
						<div class="v">
							{correctOutcomes}<span class="sm">/{totalScored || '—'}</span>
						</div>
					</div>
					<div class="sub"><b>{outcomeRate}%</b> hit rate</div>
				</div>
				<div class="pn-kpi">
					<div>
						<div class="l"><span class="pip"></span>Bonus haul</div>
						<div class="v">
							<span class="gold">{bonusHaul.total}</span>
						</div>
					</div>
					<div class="sub">
						<b>{bonusHaul.fromExact}</b> exact + <b>{bonusHaul.fromUnderdogs}</b> underdog
					</div>
				</div>
			</section>

			<!-- LIVE matches + countdown/trend -->
			<section class="pn-main2">
				<div class="pn-card">
					<div class="pn-card-h">
						<span><span class="live-dot"></span>LIVE NOW · {$liveFixtures.length} IN PROGRESS</span>
						<span class="right">MATCH DAY</span>
					</div>
					<div class="pn-card-body" style="padding: 14px 18px;">
						{#if $liveFixtures.length === 0}
							<div style="padding: 24px 0; text-align: center; font-family: var(--mono); font-size: 12px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">
								No live matches right now
							</div>
						{:else}
							{#each $liveFixtures as f (f.id)}
								{@const live = liveOf(f)}
								<div class="pn-bcast">
									<PnFlag code={teamCode(f.home_team)} w={56} h={36} />
									<div class="team">
										<span class="nm">{f.home_team}</span>
										<span class="sub">{f.group ? `Group ${f.group}` : f.stage}</span>
									</div>
									<div class="sb">{live.homeScore}–{live.awayScore}<span class="min">{live.minute}′ · {live.half === 1 ? '1H' : '2H'}</span></div>
									<div class="team r">
										<span class="nm r">{f.away_team}</span>
										<span class="sub">{f.group ? `Group ${f.group}` : f.stage}</span>
									</div>
									<PnFlag code={teamCode(f.away_team)} w={56} h={36} />
									<div class="pick">
										<span><b>YOUR PICK</b> · —</span>
										<span>Scores update live</span>
										<span>● IN PROGRESS</span>
									</div>
								</div>
							{/each}
						{/if}
					</div>
				</div>

				<div class="pn-stack">
					<div class="pn-card pn-count">
						<div class="pn-card-h">
							<span>NEXT LOCK</span>
							<span class="right">{nextFixture?.stage ?? '—'}</span>
						</div>
						<div class="pn-card-body">
							{#if nextFixture}
								<div class="who">{teamCode(nextFixture.home_team)} · {teamCode(nextFixture.away_team)}</div>
								<div class="when">{formatKickoff(nextFixture.kickoff)}</div>
							{:else}
								<div class="who">—</div>
								<div class="when">No upcoming matches</div>
							{/if}
							<div class="digits">
								<div class="digit">{pad(cd.d).slice(0, 1)}</div>
								<div class="digit">{pad(cd.d).slice(-1)}</div>
								<div class="sep">:</div>
								<div class="digit">{pad(cd.h).slice(0, 1)}</div>
								<div class="digit">{pad(cd.h).slice(-1)}</div>
								<div class="sep">:</div>
								<div class="digit">{pad(cd.m).slice(0, 1)}</div>
								<div class="digit">{pad(cd.m).slice(-1)}</div>
							</div>
							<div class="digit-label">
								<span>D</span><span>D</span><span class="ph"></span>
								<span>H</span><span>H</span><span class="ph"></span>
								<span>M</span><span>M</span>
							</div>
							<div class="quick-pick">
								<span>YOUR PICK</span>
								<span style="color: var(--paper-3);">— · —</span>
								<a class="pn-tag red" href="/predictions" style="padding: 2px 8px; text-decoration: none;">Submit →</a>
							</div>
						</div>
					</div>

					<div class="pn-trend">
						<div class="trend-h">
							<span class="l"><span class="pip"></span>Rank trajectory · 7 days</span>
							<span class="now">
								<span class="from">{trajectory.ranks[0]} →</span><em>{rank || trajectory.ranks[6]}</em>
							</span>
						</div>
						<PnSparkline ranks={trajectory.ranks} maxRank={trajectory.maxRank} width={240} height={96} />
						<div class="trend-foot">
							<span>{movement >= 0 ? 'Climber' : 'Slipped'} · pool of {totalPlayers}</span>
							<b>{movement > 0 ? '▲' : movement < 0 ? '▼' : '—'} {Math.abs(movement)} places</b>
						</div>
					</div>
				</div>
			</section>

			<!-- Insights row -->
			<section class="pn-insights">
				<!-- Closest rivals -->
				<div class="pn-insight pn-rival" style="padding: 0;">
					<div style="padding: 14px 16px 8px;">
						<div class="l"><span class="pip"></span>Closest rivals</div>
					</div>
					<div class="pn-card-body" style="padding: 0 16px 14px;">
						{#each rivals as r (r.entry_id)}
							{@const g = gapVariant(r.total_points, totalPoints)}
							{@const isYou = r.entry_id === $activeEntryId}
							<div class="row" class:you={isYou}>
								<div class="pos">{r.position}</div>
								<div>
									<div class="nm">
										{r.entry_name}
										<div class="h">
											{r.user_name}{isYou ? ' · YOU' : ''}
											{#if r.exact_scores}· {r.exact_scores} exact{/if}
										</div>
									</div>
								</div>
								<div class="gap {g.cls}">{isYou ? '—' : g.label}</div>
								<div class="pts">{r.total_points}</div>
							</div>
						{:else}
							<div style="padding: 16px 0; font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">
								No leaderboard data yet
							</div>
						{/each}
					</div>
				</div>

				<!-- Hot pick -->
				<div class="pn-insight">
					<div class="l"><span class="pip"></span>Your hottest open pick</div>
					{#if hotPick}
						<div class="matchup" style="margin-top: 4px; margin-bottom: 12px;">
							<PnFlag code={hotPick.homeCode} w={28} h={20} />
							<span>{hotPick.homeCode}</span>
							<span style="color: var(--ink-3); font-size: 12px; font-family: var(--mono);">vs</span>
							<PnFlag code={hotPick.awayCode} w={28} h={20} />
							<span>{hotPick.awayCode}</span>
						</div>
						<div class="pn-insight-row" style="align-items: baseline; gap: 16px;">
							<span class="num red">{hotPick.yourScore[0]}–{hotPick.yourScore[1]}</span>
							<div class="meta">
								Stub pick · <b>{hotPick.agreesExact} of {hotPick.total}</b> agree exact<br />
								Potential yield <b>+{hotPick.potentialPoints} pts</b> · <b>{hotPick.multiplier}×</b> avg
							</div>
						</div>
						<div class="corner-tag">High EV</div>
					{:else}
						<div class="meta" style="margin-top: 8px;">No open fixtures available.</div>
					{/if}
				</div>

				<!-- Bracket exposure -->
				<div class="pn-insight">
					<div class="l"><span class="pip"></span>Bracket exposure</div>
					<div class="pn-insight-row" style="align-items: baseline; gap: 14px;">
						<span class="num gold">{bracketExposure.pointsAvailable}</span>
						<div class="meta">
							Pts available · <b>{bracketExposure.picksLocked} of {bracketExposure.picksTotal}</b> picks<br />
							{#if bracketExposure.finalPick}
								Final pick · <b>{bracketExposure.finalPick.winnerCode}</b> over <b>{bracketExposure.finalPick.opponentCode}</b>
							{/if}
						</div>
					</div>
					<div class="corner-tag red">Locked</div>
				</div>
			</section>

			<!-- Bottom: Top 5 + Upcoming -->
			<section class="pn-bottom">
				<div>
					<div class="pn-banner">
						<span class="n">04</span>
						<h2>Top <em>5</em></h2>
						<span class="end">of {totalPlayers}</span>
					</div>
					<div class="pn-pod">
						{#each topFive as e, i (e.entry_id)}
							<div class="row" class:gold={i === 0} class:you={e.entry_id === $activeEntryId}>
								<div class="pos">{e.position}</div>
								<div>
									<div class="nm">{e.entry_name}</div>
									<div class="h">{e.user_name} · {e.exact_scores} exact · {e.correct_outcomes} outcomes</div>
								</div>
								<div class="pts">{e.total_points}</div>
							</div>
						{:else}
							<div style="padding: 16px; font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">
								Leaderboard not loaded yet
							</div>
						{/each}
					</div>
				</div>

				<div>
					<div class="pn-banner">
						<span class="n">05</span>
						<h2>Up <em>next</em></h2>
						<span class="end">{$upcomingFixtures.length} matches</span>
					</div>
					<div class="pn-card" style="padding: 0;">
						<div class="pn-card-body" style="padding: 0;">
							<table class="pn-fix-table">
								<thead>
									<tr>
										<th>Kickoff</th>
										<th>Match</th>
										<th>Stage</th>
										<th class="r">Your pick</th>
										<th class="r">Status</th>
									</tr>
								</thead>
								<tbody>
									{#each $upcomingFixtures.slice(0, 5) as f (f.id)}
										{@const k = shortKickoff(f.kickoff)}
										{@const state = rowState(f)}
										<tr>
											<td class="kick"><b>{k.day}</b>{k.time}</td>
											<td>
												<div class="match">
													{teamCode(f.home_team)}
													<span class="vs">VS</span>
													{teamCode(f.away_team)}
												</div>
											</td>
											<td class="stage">{f.group ? `Group ${f.group}` : f.stage}</td>
											<td class="pick empty">—</td>
											<td class="state {state}">●
												{state === 'locked' ? 'Locked' : state === 'soon' ? 'Soon' : 'Open'}
											</td>
										</tr>
									{:else}
										<tr><td colspan="5" style="padding: 24px; text-align: center; font-family: var(--mono); color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">No upcoming matches</td></tr>
									{/each}
								</tbody>
							</table>
						</div>
					</div>
				</div>
			</section>
		</div>

		<!-- ============================================================
		     MOBILE
		     ============================================================ -->
		<div class="pn-mob">
			<!-- Rank hero -->
			<div class="pn-m-rank">
				<div class="num">{rank || '—'}<span class="sx">{rank ? ordinal(rank) : ''}</span></div>
				<div class="info">
					<div class="l">RANK · {totalPlayers} PLAYERS</div>
					<div class="nm">{firstName}</div>
					<div class="move">
						{#if movement > 0}▲ {movement} places · last update
						{:else if movement < 0}▼ {Math.abs(movement)} places · last update
						{:else}— · holding steady{/if}
					</div>
				</div>
				<div class="pts">
					<div class="v">{totalPoints}</div>
					<div class="l">PTS</div>
				</div>
			</div>

			<!-- 2x2 KPI -->
			<div class="pn-m-kpis">
				<div class="pn-m-kpi">
					<div class="l">Bonus haul</div>
					<div class="v"><span class="gold">{bonusHaul.total}</span></div>
					<div class="sub">{bonusHaul.fromUnderdogs} from underdogs</div>
				</div>
				<div class="pn-m-kpi">
					<div class="l">Exact</div>
					<div class="v"><span class="green">{exactCount}</span><span class="sm">/{totalScored || '—'}</span></div>
					<div class="sub">+{exactCount * 10} pts</div>
				</div>
				<div class="pn-m-kpi">
					<div class="l">Outcomes</div>
					<div class="v">{correctOutcomes}<span class="sm">/{totalScored || '—'}</span></div>
					<div class="sub">{outcomeRate}% hit rate</div>
				</div>
				<div class="pn-m-kpi">
					<div class="l">Climb · 7d</div>
					<div class="v">
						{#if movement > 0}<span class="green">▲{movement}</span>
						{:else if movement < 0}<span class="red">▼{Math.abs(movement)}</span>
						{:else}<span>—</span>{/if}
					</div>
					<div class="sub">rank {climb.rankAmongClimbers} / climbers</div>
				</div>
			</div>

			<!-- Live match (first one only on mobile) -->
			{#if $liveFixtures.length > 0}
				{@const f = $liveFixtures[0]}
				{@const live = liveOf(f)}
				<div class="pn-m-live">
					<div class="head">
						<span><span class="live">LIVE</span> · {teamCode(f.home_team)} vs {teamCode(f.away_team)}</span>
						<span>{live.minute}′ · {live.half === 1 ? '1H' : '2H'}</span>
					</div>
					<div class="body">
						<div class="team">
							<PnFlag code={teamCode(f.home_team)} w={42} h={28} />
							<div class="nm">{f.home_team}</div>
						</div>
						<div class="sb">{live.homeScore}–{live.awayScore}<span class="min">{live.minute}′</span></div>
						<div class="team">
							<PnFlag code={teamCode(f.away_team)} w={42} h={28} />
							<div class="nm">{f.away_team}</div>
						</div>
						<div class="pick">
							<span>YOUR PICK · <b>—</b></span>
							<span>● IN PROGRESS</span>
						</div>
					</div>
				</div>
			{/if}

			<!-- Countdown -->
			{#if nextFixture}
				<div class="pn-m-count">
					<div class="info">
						<div class="l">NEXT LOCK</div>
						<div class="who">{teamCode(nextFixture.home_team)} vs {teamCode(nextFixture.away_team)}</div>
						<div class="when">{formatKickoff(nextFixture.kickoff)}</div>
					</div>
					<div class="digits">
						<div class="digit">{pad(cd.h).slice(0, 1)}</div>
						<div class="digit">{pad(cd.h).slice(-1)}</div>
						<div class="sep">:</div>
						<div class="digit">{pad(cd.m).slice(0, 1)}</div>
						<div class="digit">{pad(cd.m).slice(-1)}</div>
					</div>
				</div>
			{/if}

			<!-- Top 3 + you -->
			<div class="pn-m-h">
				<span class="n">04</span>
				<h2>Top <em>3</em></h2>
				<span class="end">of {totalPlayers}</span>
			</div>
			<div class="pn-m-pod">
				{#each $leaderboard.slice(0, 3) as e, i (e.entry_id)}
					<div class="pn-m-pod-row" class:gold={i === 0}>
						<div class="pos">{e.position}</div>
						<div>
							<div class="nm">{e.entry_name}</div>
							<div class="h">{e.user_name} · {e.exact_scores} ex · {e.correct_outcomes} outc</div>
						</div>
						<div class="pts">{e.total_points}</div>
					</div>
				{/each}
				{#if $activeEntryPosition && $activeEntryPosition.position > 3}
					<div class="pn-m-pod-row you">
						<div class="pos">{$activeEntryPosition.position}</div>
						<div>
							<div class="nm">{$activeEntryPosition.entry_name} · YOU</div>
							<div class="h">{firstName} · {exactCount} ex · {correctOutcomes} outc</div>
						</div>
						<div class="pts">{totalPoints}</div>
					</div>
				{/if}
			</div>

			<!-- Upcoming -->
			<div class="pn-m-h">
				<span class="n">05</span>
				<h2>Up <em>next</em></h2>
				<span class="end">{$upcomingFixtures.length} open</span>
			</div>
			<div class="pn-m-fix">
				{#each $upcomingFixtures.slice(0, 5) as f (f.id)}
					{@const k = shortKickoff(f.kickoff)}
					{@const state = rowState(f)}
					<div class="pn-m-fix-row">
						<div class="time"><b>{k.day.split(' ')[0]}</b>{k.time}</div>
						<div class="match">
							<PnFlag code={teamCode(f.home_team)} w={16} h={11} />
							{teamCode(f.home_team)} ·
							<PnFlag code={teamCode(f.away_team)} w={16} h={11} />
							{teamCode(f.away_team)}
							<span class="stage">{f.group ? `Group ${f.group}` : f.stage}</span>
						</div>
						<div class="pick empty">
							—
							<span class="state {state}">{state === 'locked' ? 'Locked' : state === 'soon' ? 'Soon' : 'Open'}</span>
						</div>
					</div>
				{:else}
					<div style="padding: 14px; text-align: center; font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">
						No upcoming matches
					</div>
				{/each}
			</div>

			<div style="height: 14px;"></div>
		</div>
	</PnPageShell>
{/if}
