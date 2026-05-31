<script lang="ts">
	/**
	 * /results/[fixture_id] — Match Detail drill-down (DaisyUI port of 75597e2).
	 *
	 * Single-match view combining:
	 *   - Hero strip with team flags, state badge, actual score
	 *   - Per-user breakdown card (reuses BreakdownCard from Phase B)
	 *   - 5×5 bubble grid: score distribution across all predictors
	 *   - Per-match leaderboard
	 *
	 * State → mode mapping:
	 *   - finished → post  (actual score drives colouring)
	 *   - live     → post  (live score acts as "if FT now" result)
	 *   - locked   → pre   (no score yet; bubbles coloured by W/D/L)
	 *   - open     → blocked  (community endpoint refuses; show placeholder)
	 *
	 * Data sources mirror main's 75597e2 but use sheets's entry-scoped agreements API.
	 * matchDetail.ts utilities are pure ports — buildCells, toGridPlayer, fmtKickoff.
	 */
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import { fetchAllFixtures, fixtureById } from '$stores/fixtures';
	import { fetchMatchPredictions, predictionsByFixture } from '$stores/predictions';
	import {
		getAgreements,
		getCommunityPredictions,
		type FixtureAgreement
	} from '$api/predictions';
	import { getLeaderboard, type PhaseFilter } from '$api/leaderboard';
	import { getScoringConfig, type ScoringConfig } from '$api/competition';
	import { computeBreakdown, stageLabel, stageShort, matchState } from '$lib/utils/matchBreakdown';
	import {
		buildCells,
		toGridPlayer,
		fmtKickoff,
		pickActualScore,
		rarityLabel,
		type GridPlayer,
		type BubbleCell
	} from '$lib/utils/matchDetail';
	import { teamCode } from '$lib/utils/teamCodes';
	import { displayTeamName } from '$lib/utils/teamName';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { entries, loadEntries, submittedEntries } from '$stores/entries';
	import BreakdownCard from '$lib/components/results/BreakdownCard.svelte';
	import type {
		CommunityPredictionsResponse,
		Fixture,
		LeaderboardEntry,
		LeaderboardResponse
	} from '$types';

	$: if (browser && !$isAuthenticated) goto('/login');

	$: fixtureId = $page.params.fixture_id ?? '';
	$: fixture = $fixtureById.get(fixtureId) as Fixture | undefined;

	let loading = true;
	let loadError: string | null = null;
	let community: CommunityPredictionsResponse | null = null;
	let agreement: FixtureAgreement | undefined = undefined;
	let leaderboardEntries: LeaderboardEntry[] = [];
	let scoringConfig: ScoringConfig = {
		mode: 'logarithmic',
		outcome_points: 5,
		exact_points: 10,
		rarity_cap: 10
	};
	let blocked = false;
	let activeEntryId: string | null = null;

	onMount(async () => {
		if (!$isAuthenticated) return;
		try {
			// Fixtures + own predictions first.
			await Promise.all([fetchAllFixtures(), fetchMatchPredictions()]);

			const f = $fixtureById.get(fixtureId);
			if (!f) {
				loadError = 'Fixture not found.';
				loading = false;
				return;
			}

			// Pick an entry for agreements scoping (most-recent submitted → first).
			if ($user?.id) {
				try {
					await loadEntries($user.id);
					activeEntryId = ($submittedEntries[0] ?? $entries[0] ?? null)?.id ?? null;
				} catch {
					activeEntryId = null;
				}
			}

			const state = matchState(f);
			if (state === 'open') {
				blocked = true;
				const [cfg, ags] = await Promise.all([
					getScoringConfig().catch(() => scoringConfig),
					activeEntryId
						? getAgreements(activeEntryId, [fixtureId]).catch(() => [] as FixtureAgreement[])
						: Promise.resolve([] as FixtureAgreement[])
				]);
				scoringConfig = cfg;
				agreement = ags.find((a) => a.fixture_id === fixtureId);
				loading = false;
				return;
			}

			const [comm, cfg, ags, lb] = await Promise.all([
				getCommunityPredictions(fixtureId),
				getScoringConfig().catch(() => scoringConfig),
				activeEntryId
					? getAgreements(activeEntryId, [fixtureId]).catch(() => [] as FixtureAgreement[])
					: Promise.resolve([] as FixtureAgreement[]),
				getLeaderboard(null as unknown as PhaseFilter).catch(
					() => ({ entries: [] }) as Partial<LeaderboardResponse> as LeaderboardResponse
				)
			]);
			community = comm;
			scoringConfig = cfg;
			agreement = ags.find((a) => a.fixture_id === fixtureId);
			leaderboardEntries = lb.entries ?? [];
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Failed to load match.';
		} finally {
			loading = false;
		}
	});

	// Build the GridPlayer[] for the bubble grid + leaderboard.
	$: gridPlayers = (() => {
		if (!community) return [] as GridPlayer[];
		const lbByName = new Map<string, LeaderboardEntry>();
		for (const e of leaderboardEntries) lbByName.set(e.user_name, e);
		const youName = $user?.name ?? null;
		return community.predictions.map((cp) => {
			const lb = lbByName.get(cp.user_name);
			return toGridPlayer(
				cp,
				youName !== null && cp.user_name === youName,
				lb?.position ?? null,
				lb?.total_points ?? null,
				lb?.movement ?? null
			);
		});
	})();

	$: cells = buildCells(gridPlayers);
	$: youPlayer = gridPlayers.find((p) => p.you) ?? null;

	$: state = fixture ? matchState(fixture) : null;
	$: phase = (state === 'finished' || state === 'live' ? 'post' : 'pre') as 'pre' | 'post';
	$: actualScore = pickActualScore(fixture?.score ?? null);

	$: ownPrediction = $predictionsByFixture.get(fixtureId);
	$: breakdown = fixture
		? computeBreakdown(fixture, ownPrediction, agreement, scoringConfig)
		: null;

	$: homeCode = fixture ? teamCode(fixture.home_team) : '';
	$: awayCode = fixture ? teamCode(fixture.away_team) : '';
	$: homeFull = fixture ? displayTeamName(fixture.home_team) : '';
	$: awayFull = fixture ? displayTeamName(fixture.away_team) : '';

	$: homeWon = !!(
		state === 'finished' &&
		actualScore &&
		actualScore.home_score > actualScore.away_score
	);
	$: awayWon = !!(
		state === 'finished' &&
		actualScore &&
		actualScore.away_score > actualScore.home_score
	);

	$: kickoff = fixture ? fmtKickoff(fixture.kickoff) : { dow: '', date: '', time: '' };

	function stateBadgeText(): string {
		if (state === 'finished') return 'FULL TIME';
		if (state === 'live') return fixture?.minute != null ? `LIVE · ${fixture.minute}'` : 'LIVE';
		if (state === 'locked') return 'PRE-MATCH · LOCKED';
		return 'PRE-MATCH';
	}
	function stateBadgeClass(): string {
		if (state === 'finished') return 'badge-neutral';
		if (state === 'live') return 'badge-info animate-pulse';
		if (state === 'locked') return 'badge-warning';
		return 'badge-ghost';
	}

	/** 5×5 bubble grid: home picks on Y (0..4 top→bottom), away on X (0..4 left→right). */
	const GRID_MAX = 4;
	const RANGE = [0, 1, 2, 3, 4];

	function cellAt(h: number, a: number): BubbleCell | undefined {
		return cells[`${h},${a}`];
	}

	/** Outcome class for a cell — by W/D/L of the predicted score. */
	function cellOutcomeClass(h: number, a: number): string {
		if (h > a) return 'home-win';
		if (a > h) return 'away-win';
		return 'draw';
	}

	/** Cell colouring depends on phase:
	 *   - pre:  by predicted-side (home-win / draw / away-win)
	 *   - post: by accuracy vs actual (exact / outcome / miss / empty)
	 */
	function cellBg(h: number, a: number, count: number): string {
		if (count === 0) return 'bg-base-300/15 text-base-content/30';
		if (phase === 'pre') {
			const o = cellOutcomeClass(h, a);
			if (o === 'home-win') return 'bg-info/15 text-info border-info/40';
			if (o === 'draw') return 'bg-base-content/10 text-base-content/70 border-base-content/20';
			return 'bg-warning/15 text-warning-text border-warning/40';
		}
		// post — colour by accuracy
		if (!actualScore) return 'bg-base-300/30 text-base-content/60';
		if (h === actualScore.home_score && a === actualScore.away_score)
			return 'bg-success/30 text-success border-success/60';
		const sameOutcome =
			cellOutcomeClass(h, a) === cellOutcomeClass(actualScore.home_score, actualScore.away_score);
		if (sameOutcome) return 'bg-warning/20 text-warning-text border-warning/40';
		return 'bg-error/10 text-error/70 border-error/30';
	}

	function cellIsActual(h: number, a: number): boolean {
		return !!(actualScore && h === actualScore.home_score && a === actualScore.away_score);
	}

	function cellHasYou(h: number, a: number): boolean {
		return !!(youPlayer && youPlayer.home === Math.min(GRID_MAX, youPlayer.home) &&
			youPlayer.away === Math.min(GRID_MAX, youPlayer.away) &&
			Math.min(GRID_MAX, youPlayer.home) === h && Math.min(GRID_MAX, youPlayer.away) === a);
	}

	/** Per-match leaderboard sort: exact hits first, then outcome hits, then by rank. */
	$: rankedPlayers = (() => {
		if (!gridPlayers.length) return [] as GridPlayer[];
		return [...gridPlayers].sort((p, q) => {
			const pe = actualScore && p.home === actualScore.home_score && p.away === actualScore.away_score ? 0 : 1;
			const qe = actualScore && q.home === actualScore.home_score && q.away === actualScore.away_score ? 0 : 1;
			if (pe !== qe) return pe - qe;
			const po =
				actualScore && cellOutcomeClass(p.home, p.away) === cellOutcomeClass(actualScore.home_score, actualScore.away_score)
					? 0
					: 1;
			const qo =
				actualScore && cellOutcomeClass(q.home, q.away) === cellOutcomeClass(actualScore.home_score, actualScore.away_score)
					? 0
					: 1;
			if (po !== qo) return po - qo;
			return (p.rank ?? 999) - (q.rank ?? 999);
		});
	})();

	function pickPointsForPlayer(p: GridPlayer): { exact: boolean; outcome: boolean; pts: number } {
		if (!actualScore) return { exact: false, outcome: false, pts: 0 };
		const exact = p.home === actualScore.home_score && p.away === actualScore.away_score;
		const sameOutcome =
			cellOutcomeClass(p.home, p.away) ===
			cellOutcomeClass(actualScore.home_score, actualScore.away_score);
		if (exact) return { exact: true, outcome: true, pts: scoringConfig.outcome_points + scoringConfig.exact_points };
		if (sameOutcome) return { exact: false, outcome: true, pts: scoringConfig.outcome_points };
		return { exact: false, outcome: false, pts: 0 };
	}
</script>

<svelte:head>
	<title>
		{fixture ? `${homeCode} vs ${awayCode} — Match Detail` : 'Match Detail'} · Predictor
	</title>
</svelte:head>

{#if $isAuthenticated}
	<div class="container mx-auto mobile-padding py-6 space-y-6">
		<!-- Back link -->
		<div>
			<a class="link link-hover text-xs font-mono text-base-content/60" href="/results">
				← Back to results
			</a>
		</div>

		{#if loading}
			<div class="flex justify-center py-16">
				<span class="loading loading-spinner loading-lg text-primary"></span>
			</div>
		{:else if loadError || !fixture}
			<div class="stadium-card no-glow p-8 text-center">
				<p class="text-base-content/70">{loadError ?? 'Match not found.'}</p>
				<a class="link link-primary text-sm mt-3 inline-block" href="/results">← Back to results</a>
			</div>
		{:else}
			<!-- Hero -->
			<section class="stadium-card no-glow p-5 sm:p-7">
				<div class="grid grid-cols-[1fr_auto_1fr] items-center gap-4 sm:gap-8">
					<!-- Home -->
					<div
						class="flex flex-col items-center text-center gap-2 {awayWon ? 'opacity-60' : ''}"
					>
						{#if hasFlag(fixture.home_team)}
							<img
								src={getFlagUrl(fixture.home_team, 'md')}
								alt=""
								class="w-14 sm:w-20 h-auto rounded-md shadow-md"
							/>
						{/if}
						<div class="text-[10px] uppercase tracking-widest text-base-content/40 font-mono">
							Home · {fixture.group ? `Group ${fixture.group}` : stageLabel(fixture.stage)}
						</div>
						<div class="font-display text-base sm:text-xl tracking-wide">{homeFull}</div>
					</div>

					<!-- Centre -->
					<div class="flex flex-col items-center gap-2 min-w-[7rem]">
						<span class="badge {stateBadgeClass()} badge-sm font-mono uppercase tracking-wider">
							{stateBadgeText()}
						</span>
						{#if phase === 'post' && actualScore}
							<div class="font-display text-4xl sm:text-5xl tracking-wider">
								<span class={awayWon ? 'text-base-content/40' : ''}>{actualScore.home_score}</span>
								<span class="text-base-content/40 mx-1">–</span>
								<span class={homeWon ? 'text-base-content/40' : ''}>{actualScore.away_score}</span>
							</div>
						{:else}
							<div class="font-display text-3xl sm:text-4xl tracking-wider text-base-content/40">
								VS
							</div>
						{/if}
						<div class="text-[10px] font-mono text-base-content/50 flex items-center gap-2">
							<span>KO <b class="text-base-content/70">{kickoff.time}</b></span>
							<span class="opacity-40">·</span>
							<span>{kickoff.dow} <b class="text-base-content/70">{kickoff.date}</b></span>
							{#if fixture.group}
								<span class="opacity-40">·</span>
								<span>GROUP <b class="text-base-content/70">{fixture.group}</b></span>
							{:else}
								<span class="opacity-40">·</span>
								<span><b class="text-base-content/70">{stageShort(fixture.stage)}</b></span>
							{/if}
						</div>
					</div>

					<!-- Away -->
					<div
						class="flex flex-col items-center text-center gap-2 {homeWon ? 'opacity-60' : ''}"
					>
						{#if hasFlag(fixture.away_team)}
							<img
								src={getFlagUrl(fixture.away_team, 'md')}
								alt=""
								class="w-14 sm:w-20 h-auto rounded-md shadow-md"
							/>
						{/if}
						<div class="text-[10px] uppercase tracking-widest text-base-content/40 font-mono">
							Away · {fixture.group ? `Group ${fixture.group}` : stageLabel(fixture.stage)}
						</div>
						<div class="font-display text-base sm:text-xl tracking-wide">{awayFull}</div>
					</div>
				</div>
			</section>

			<!-- Your breakdown card (reuse Phase B component) -->
			{#if breakdown}
				<section>
					<h2 class="text-xs uppercase tracking-widest text-base-content/50 mb-2 font-mono">
						Your prediction · {breakdown.totalLabel.toLowerCase()}
					</h2>
					<BreakdownCard
						{fixture}
						prediction={ownPrediction}
						{breakdown}
						config={scoringConfig}
					/>
				</section>
			{/if}

			{#if blocked}
				<!-- Pre-lock placeholder: community is gated -->
				<section class="stadium-card no-glow p-6 text-center">
					<h3 class="font-display text-lg tracking-wide mb-2">Predictions are blind until lock</h3>
					<p class="text-sm text-base-content/60 max-w-prose mx-auto">
						Community predictions become visible <b>5 minutes before kickoff</b>. Come back when
						the match locks to see the full pool, the score-distribution plot, and the per-match
						leaderboard.
					</p>
				</section>
			{:else}
				<!-- Bubble grid + leaderboard, two-column on lg+ -->
				<div class="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-5">
					<!-- LEFT: bubble plate -->
					<section class="stadium-card no-glow p-4 sm:p-5 overflow-hidden">
						<header class="flex items-center justify-between mb-3 flex-wrap gap-2">
							<h3 class="text-sm font-display tracking-wide">
								{phase === 'pre'
									? 'Predicted scoreline distribution'
									: 'Match result · scoreline distribution'}
							</h3>
							<div class="flex flex-wrap items-center gap-2 text-[10px] font-mono">
								{#if phase === 'pre'}
									<span class="inline-flex items-center gap-1"
										><span class="w-2.5 h-2.5 rounded-sm bg-info/30 border border-info/50" />{homeCode} win</span
									>
									<span class="inline-flex items-center gap-1"
										><span class="w-2.5 h-2.5 rounded-sm bg-base-content/15 border border-base-content/30" />Draw</span
									>
									<span class="inline-flex items-center gap-1"
										><span class="w-2.5 h-2.5 rounded-sm bg-warning/30 border border-warning/50" />{awayCode} win</span
									>
								{:else}
									<span class="inline-flex items-center gap-1"
										><span class="w-2.5 h-2.5 rounded-sm bg-success/40 border border-success/60" />Exact ★</span
									>
									<span class="inline-flex items-center gap-1"
										><span class="w-2.5 h-2.5 rounded-sm bg-warning/30 border border-warning/50" />Outcome</span
									>
									<span class="inline-flex items-center gap-1"
										><span class="w-2.5 h-2.5 rounded-sm bg-error/15 border border-error/40" />No pts</span
									>
								{/if}
								<span class="inline-flex items-center gap-1 text-primary"
									><span class="w-2.5 h-2.5 rounded-full border-2 border-primary" />{phase === 'pre'
										? 'Your pick'
										: 'You'}</span
								>
							</div>
						</header>

						<!-- 5×5 grid: rows = home_score (0..4 top-to-bottom), cols = away_score (0..4 left-to-right) -->
						<div class="overflow-x-auto">
							<table class="w-full table-fixed text-xs">
								<thead>
									<tr>
										<th class="w-10 sm:w-12 text-right pr-2 text-[10px] font-mono uppercase tracking-widest text-base-content/40">
											{homeCode}↓
										</th>
										{#each RANGE as a}
											<th class="text-center text-[10px] font-mono uppercase tracking-widest text-base-content/40 pb-1"
												>{a}</th
											>
										{/each}
									</tr>
									<tr>
										<th
											class="text-right pr-2 text-[10px] font-mono uppercase tracking-widest text-base-content/40"
										>
											{awayCode}→
										</th>
										<th colspan={RANGE.length}></th>
									</tr>
								</thead>
								<tbody>
									{#each RANGE as h}
										<tr>
											<th
												class="text-right pr-2 text-[10px] font-mono uppercase tracking-widest text-base-content/40 align-middle"
											>
												{h}
											</th>
											{#each RANGE as a (a)}
												{@const cell = cellAt(h, a)}
												{@const count = cell?.players.length ?? 0}
												<td class="p-1">
													<div
														class="relative aspect-square flex items-center justify-center rounded-md border {cellBg(
															h,
															a,
															count
														)} {cellIsActual(h, a)
															? 'ring-2 ring-success ring-offset-1 ring-offset-base-100'
															: ''}"
														title="{h}–{a}: {count} {count === 1 ? 'pick' : 'picks'}"
													>
														{#if count > 0}
															<span class="font-display text-base sm:text-lg leading-none">{count}</span>
														{:else}
															<span class="text-[10px] opacity-30">·</span>
														{/if}
														{#if cellHasYou(h, a)}
															<span
																class="absolute -top-1 -right-1 inline-flex items-center justify-center w-5 h-5 rounded-full bg-primary text-primary-content text-[9px] font-bold border-2 border-base-100"
																>YOU</span
															>
														{/if}
														{#if cellIsActual(h, a)}
															<span
																class="absolute -bottom-1.5 left-1/2 -translate-x-1/2 text-[8px] uppercase tracking-widest font-mono text-success font-bold"
																>FT</span
															>
														{/if}
													</div>
												</td>
											{/each}
										</tr>
									{/each}
								</tbody>
							</table>
						</div>

						<p class="text-[10px] text-base-content/40 mt-2 text-center font-mono">
							{gridPlayers.length} predictions{gridPlayers.length > 0
								? ` · scores ≥${GRID_MAX + 1} clamped to row/col ${GRID_MAX}`
								: ''}
						</p>
					</section>

					<!-- RIGHT: per-match leaderboard -->
					<section class="stadium-card no-glow overflow-hidden flex flex-col max-h-[640px]">
						<header class="px-4 py-3 border-b border-base-300/40 bg-base-300/20">
							<h3 class="text-sm font-display tracking-wide">Per-match leaderboard</h3>
							<p class="text-[10px] font-mono text-base-content/40 mt-0.5">
								{rankedPlayers.length} predictions ·
								{phase === 'pre' ? 'pre-lock view' : 'sorted by points earned'}
							</p>
						</header>
						<div class="overflow-y-auto divide-y divide-base-300/30 flex-1">
							{#each rankedPlayers as p, i (p.name)}
								{@const pp = pickPointsForPlayer(p)}
								<div
									class="flex items-center gap-2 sm:gap-3 px-3 sm:px-4 py-2 text-sm {p.you
										? 'bg-primary/10 border-l-4 border-primary'
										: ''}"
								>
									<span class="w-7 text-right text-xs font-mono text-base-content/40 tabular-nums"
										>{i + 1}</span
									>
									<span
										class="w-7 h-7 rounded-full bg-base-300/60 flex items-center justify-center text-xs font-bold uppercase shrink-0"
									>
										{p.initial}
									</span>
									<div class="flex-1 min-w-0">
										<div class="font-medium text-sm truncate">
											{p.name}
											{#if p.you}<span class="text-primary text-[10px] font-mono ml-1">YOU</span>{/if}
										</div>
										{#if p.totalPts != null}
											<div class="text-[10px] text-base-content/40 font-mono">
												Comp #{p.rank ?? '—'} · {p.totalPts} pts
											</div>
										{/if}
									</div>
									<div class="text-right">
										<div class="font-display text-base tracking-wide leading-none">
											{p.home}<span class="text-base-content/40 mx-0.5">–</span>{p.away}
										</div>
										{#if phase === 'post'}
											<div class="text-[10px] font-mono mt-0.5 leading-none">
												{#if pp.exact}
													<span class="text-success">★ +{pp.pts}</span>
												{:else if pp.outcome}
													<span class="text-warning-text">+{pp.pts}</span>
												{:else}
													<span class="text-base-content/30">—</span>
												{/if}
											</div>
										{/if}
									</div>
								</div>
							{/each}
							{#if rankedPlayers.length === 0}
								<div class="px-4 py-8 text-center text-sm text-base-content/40">
									No predictions to show.
								</div>
							{/if}
						</div>
					</section>
				</div>
			{/if}
		{/if}
	</div>
{/if}
