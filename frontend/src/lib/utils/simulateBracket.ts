/**
 * What-if bracket simulator — pure re-rank engine (KO advancement only).
 *
 * A user picks winners of UNPLAYED knockout matches; those propagate down
 * the bracket tree (R32 → R16 → QF → SF → Final); every pool entry's
 * knockout points are recomputed against the resulting hypothetical
 * lineup, and the whole leaderboard re-ranks.
 *
 * Bonus-question points are never rescored — no bonus question is
 * resolved by who wins a KO match, so both categories ride through
 * unchanged from the server: group-stage bonus inside `group_points`,
 * knockout-stage bonus via its own `bonus_knockout_points` field. Only
 * KO advancement points (`fixtureKoHits` / `stagePointsForRound`) are
 * rescored per scenario.
 *
 * No Svelte/store/`$app` imports — this module must stay pure so it can
 * run in a Web Worker later if the full-pool rescore gets expensive.
 */

import type { BracketPrediction, Fixture } from '$types';
import type { RoundId } from '$lib/types/results';
import type {
	HypoWinners,
	PivotalMatch,
	ProjectedRow,
	ResolvedMatch,
	ResolvedScenario,
	SimulatorBracketPicks,
	SimulatorEntryPicks
} from '$lib/types/simulator';
import {
	FINAL,
	QUARTER_FINALS,
	ROUND_OF_16,
	ROUND_OF_32,
	SEMI_FINALS,
	type KnockoutMatch
} from '$lib/config/bracketConfig';
import { buildMatchNumberIndex } from './bracketGeometry';
import { bracketPicksForRound, stagePointsForRound } from './koPoints';
import { koWinnerSide } from './matchDetailV4';

/** Config matches in resolution order — upstream rounds first so every
 *  `winner` source is already known by the time a later round reads it. */
const CONFIG_IN_ORDER: KnockoutMatch[] = [
	...ROUND_OF_32,
	...ROUND_OF_16,
	...QUARTER_FINALS,
	...SEMI_FINALS,
	FINAL
];

/** Round rank scale used by `reached`/`rankOf`. Matches the KO progression
 *  order R32 < R16 < QF < SF < F; the champion additionally reaches rank 6
 *  (one past the Final) so "won the Final" and "reached the Final" are
 *  distinguishable via rank comparison alone. */
const ROUND_RANK: Record<RoundId, number> = {
	summary: 0,
	r1: 0,
	r2: 0,
	r3: 0,
	groups: 0,
	bracket: 0,
	r32: 1,
	r16: 2,
	qf: 3,
	sf: 4,
	f: 5,
	winner: 0 // unused for rank lookups — champion rank is hardcoded to 6 below
};

const CHAMPION_RANK = 6;

const KO_ROUND_ORDER: RoundId[] = ['r32', 'r16', 'qf', 'sf', 'f'];

/** Round rank a team must reach for a pick in `roundId` to hit. */
export function rankOf(roundId: RoundId): number {
	return ROUND_RANK[roundId];
}

/** A placeholder home/away value ("slot:round_of_32:537416:home") or an
 *  unresolved seed label ("1A", "3ABCDF") — never a real team name. Same
 *  heuristic as `koPoints.ts`'s `lineupSeeded`: real team names never
 *  contain digits, placeholders always do. */
function isRealTeamName(name: string | null | undefined): name is string {
	return !!name && !/\d/.test(name);
}

/** Real winner of a FINISHED, non-third_place fixture, else null.
 *
 *  Resolves pens → ET → regulation via the canonical `koWinnerSide` (the
 *  same resolver every read surface uses), so a knockout decided on
 *  penalties after a regulation draw still yields a winner. Reading
 *  `score.outcome` alone missed shootouts: such a match stayed winnerless —
 *  it never advanced, never propagated its real winner downstream, and
 *  (being finished) wasn't clickable either, leaving the chip dead. */
function realWinnerOf(fixture: Fixture | undefined): string | null {
	if (!fixture || fixture.status !== 'finished' || !fixture.score) return null;
	if (fixture.stage === 'third_place') return null;
	const side = koWinnerSide(fixture.score);
	if (side === 'home') return fixture.home_team;
	if (side === 'away') return fixture.away_team;
	return null;
}

/**
 * Resolve one match's two participant teams from its config sources.
 *
 * R32 teams come straight from the fixture's real home/away (group-stage
 * lineup); later rounds' participants are the previous round's resolved
 * winners (real or hypothetical).
 */
function resolveParticipants(
	cfg: KnockoutMatch,
	fixture: Fixture | undefined,
	matches: Map<number, ResolvedMatch>
): { home: string | null; away: string | null } {
	if (cfg.round === 'round_of_32') {
		const home = isRealTeamName(fixture?.home_team) ? fixture!.home_team : null;
		const away = isRealTeamName(fixture?.away_team) ? fixture!.away_team : null;
		return { home, away };
	}
	const sourceTeam = (source: KnockoutMatch['homeSource']): string | null => {
		if (source.type !== 'winner') return null; // third_place has no config in later rounds
		return matches.get(source.matchNumber)?.winner ?? null;
	};
	return { home: sourceTeam(cfg.homeSource), away: sourceTeam(cfg.awaySource) };
}

/**
 * Resolve a full KO scenario: real results layered with the caller's
 * hypothetical winners for any still-open match.
 *
 * Algorithm (see module docstring): walk `CONFIG_IN_ORDER` (R32 → Final)
 * so upstream winners are always resolved before a downstream match reads
 * them. For each match:
 *   1. Resolve its two participant teams (R32: from the real fixture;
 *      later rounds: previous round's resolved winner).
 *   2. Determine the winner: the REAL result wins if the fixture is
 *      FINISHED; otherwise the caller's hypothetical pick wins IF it
 *      matches one of the two resolved participants; otherwise the match
 *      stays unresolved (winner = null) and nothing propagates downstream.
 *   3. Record every resolved participant as having "reached" that round
 *      in the `reached` map (rank = round's rank). The Final's winner
 *      additionally reaches CHAMPION_RANK and becomes `champion`.
 *
 * `third_place` is skipped entirely — unscored stage, not part of the
 * advancement tree (CLAUDE.md invariant).
 */
export function resolveScenario(fixtures: Fixture[], hypoWinners: HypoWinners): ResolvedScenario {
	const fixtureIndex = buildMatchNumberIndex(fixtures);
	const matches = new Map<number, ResolvedMatch>();
	const reached = new Map<string, number>();
	let champion: string | null = null;

	const markReached = (team: string | null, rank: number) => {
		if (!team) return;
		const prev = reached.get(team) ?? 0;
		if (rank > prev) reached.set(team, rank);
	};

	const roundRankOf = (round: KnockoutMatch['round']): number => {
		switch (round) {
			case 'round_of_32':
				return ROUND_RANK.r32;
			case 'round_of_16':
				return ROUND_RANK.r16;
			case 'quarter_finals':
				return ROUND_RANK.qf;
			case 'semi_finals':
				return ROUND_RANK.sf;
			case 'final':
				return ROUND_RANK.f;
			default:
				return 0;
		}
	};

	for (const cfg of CONFIG_IN_ORDER) {
		const fixture = fixtureIndex.get(cfg.matchNumber);
		const { home, away } = resolveParticipants(cfg, fixture, matches);

		const rank = roundRankOf(cfg.round);
		markReached(home, rank);
		markReached(away, rank);

		let winner = realWinnerOf(fixture);
		if (!winner) {
			const hypo = hypoWinners.get(cfg.matchNumber);
			if (hypo && (hypo === home || hypo === away)) {
				winner = hypo;
			}
		}

		matches.set(cfg.matchNumber, { home, away, winner: winner ?? null });

		if (cfg.round === 'final' && winner) {
			champion = winner;
			markReached(winner, CHAMPION_RANK);
		}
	}

	return { reached, champion, matches };
}

/** Adapt `SimulatorBracketPicks` into the `BracketPrediction` shape that
 *  `bracketPicksForRound` expects. Field names already match one-to-one;
 *  `group_winners` is irrelevant here (KO-only scope) so it's stubbed. */
function asBracketPrediction(picks: SimulatorBracketPicks): BracketPrediction {
	return {
		group_winners: {},
		round_of_32: picks.round_of_32,
		round_of_16: picks.round_of_16,
		quarter_finals: picks.quarter_finals,
		semi_finals: picks.semi_finals,
		final: picks.final,
		winner: picks.winner ?? ''
	};
}

/**
 * Rescore one entry's knockout points against a resolved scenario.
 *
 * For each KO round, every team the entry picked to reach that round
 * that ACTUALLY reaches (or surpasses) that round's rank under the
 * scenario earns that round's stage points. The Final winner pick earns
 * `adv.winner` additionally when it matches the scenario's champion.
 *
 * This intentionally mirrors `computeKoTotal` (`frontend/src/routes/
 * results/+page.svelte`) semantics when `reached` is derived from the
 * REAL fixtures with no hypothetical overrides — see the parity test.
 */
export function rescoreEntryKo(
	picks: SimulatorBracketPicks,
	reached: Map<string, number>,
	champion: string | null,
	adv: Record<string, number>
): number {
	const bracket = asBracketPrediction(picks);
	let total = 0;
	for (const roundId of KO_ROUND_ORDER) {
		const roundPicks = bracketPicksForRound(bracket, roundId);
		const stagePts = stagePointsForRound(adv, roundId);
		const requiredRank = rankOf(roundId);
		for (const team of roundPicks) {
			if ((reached.get(team) ?? 0) >= requiredRank) {
				total += stagePts;
			}
		}
	}
	if (picks.winner && champion && picks.winner === champion) {
		total += adv.winner ?? 0;
	}
	return total;
}

/**
 * Project the whole pool's standings under a resolved scenario.
 *
 * `newTotal` = server-supplied group points (untouched — includes
 * group-stage bonus, held fixed since group stage isn't part of this
 * what-if) + rescored KO advancement points + server-supplied
 * knockout-stage bonus points (also untouched — no bonus question is
 * resolved by who wins a bracket match). This is the invariant that
 * keeps the simulator trustworthy: with an empty `HypoWinners` map
 * (nothing hypothetical), `newTotal` must reproduce the entry's real
 * `total_points` exactly — see the parity test in
 * simulateBracket.test.ts. Sorted by newTotal descending, ties broken
 * alphabetically by entry_name (stable, matches `sortRows`'s A→Z
 * tie-break convention in `leaderboardV4.ts`).
 */
export function projectStandings(
	entries: SimulatorEntryPicks[],
	reached: Map<string, number>,
	champion: string | null,
	adv: Record<string, number>
): ProjectedRow[] {
	const withTotals = entries.map((entry) => {
		const koPoints = rescoreEntryKo(entry.picks, reached, champion, adv);
		const newTotal = entry.group_points + koPoints + entry.bonus_knockout_points;
		return { entry, newTotal };
	});

	const sorted = [...withTotals].sort((a, b) => {
		if (b.newTotal !== a.newTotal) return b.newTotal - a.newTotal;
		return a.entry.entry_name.localeCompare(b.entry.entry_name, undefined, {
			sensitivity: 'base'
		});
	});

	return sorted.map(({ entry, newTotal }, idx) => {
		const newPos = idx + 1;
		return {
			entry_id: entry.entry_id,
			entry_name: entry.entry_name,
			user_id: entry.user_id,
			user_name: entry.user_name,
			oldPos: entry.position,
			oldTotal: entry.total_points,
			newTotal,
			newPos,
			deltaPos: entry.position - newPos,
			deltaPts: newTotal - entry.total_points
		};
	});
}

/**
 * Seed a hypothetical-winners map from the signed-in user's own bracket
 * picks, for UNPLAYED matches only.
 *
 * A match is seeded only when the user's picked winner for that match is
 * actually one of the match's two CURRENTLY resolved real teams (i.e. the
 * pick hasn't already been eliminated / wasn't for a team that never made
 * this fixture's slot). Matches whose pick is absent or eliminated are
 * left unset — the scenario simply has no override there, so
 * `resolveScenario` reports that match (and everything downstream of it)
 * as unresolved rather than silently guessing.
 *
 * Resolved round-by-round (R32 → R16 → QF → SF → F), re-resolving the
 * scenario after each round's picks are folded in. This lets an earlier
 * hypothetical winner (e.g. the user's R32 pick) seed a later round's
 * participant slot (e.g. that team showing up as one of the R16 fixture's
 * two teams) so the user's SF/Final picks can also seed correctly even
 * though those matches' upstream fixtures haven't been played yet.
 */
export function fillFromMyPicks(fixtures: Fixture[], myBracket: BracketPrediction): HypoWinners {
	const hypoWinners: HypoWinners = new Map();

	const roundConfigs: Array<{ roundId: RoundId; matches: KnockoutMatch[] }> = [
		{ roundId: 'r32', matches: ROUND_OF_32 },
		{ roundId: 'r16', matches: ROUND_OF_16 },
		{ roundId: 'qf', matches: QUARTER_FINALS },
		{ roundId: 'sf', matches: SEMI_FINALS },
		{ roundId: 'f', matches: [FINAL] }
	];

	for (const { roundId, matches } of roundConfigs) {
		const picks = bracketPicksForRound(myBracket, roundId);
		if (picks.size === 0) continue;
		// Re-resolve with everything seeded so far, so this round's matches
		// see any upstream hypothetical winners already folded in.
		const scenario = resolveScenario(fixtures, hypoWinners);
		for (const cfg of matches) {
			const resolved = scenario.matches.get(cfg.matchNumber);
			if (!resolved || resolved.winner) continue; // already played (or otherwise settled)
			const { home, away } = resolved;
			const candidate = [home, away].find((team) => team && picks.has(team));
			if (candidate) hypoWinners.set(cfg.matchNumber, candidate);
			// else: pick absent/eliminated from this slot — leave open.
		}
	}

	return hypoWinners;
}

/**
 * Rank one entry's `newPos` out of a projected-standings run, or `null` if
 * the entry isn't present (defensive — caller already guards this, but
 * keeps this helper safe to reuse standalone).
 */
function myPosIn(rows: ProjectedRow[], myEntryId: string): number | null {
	return rows.find((row) => row.entry_id === myEntryId)?.newPos ?? null;
}

/**
 * Find the still-open KO matches whose outcome most changes MY entry's
 * projected rank — i.e. the matches worth watching.
 *
 * A match is a CANDIDATE when, under the base scenario (real results +
 * `baseHypo` overrides already applied), both its participants have
 * resolved to real team names but the match itself has no winner yet
 * (still open). For each candidate we branch the base scenario twice —
 * once per possible winner — re-resolve, re-project the whole pool, and
 * read my entry's `newPos` in each branch. `swing` is the absolute
 * difference between the two: matches with a bigger swing matter more to
 * my outcome.
 *
 * Reuses `resolveScenario`/`projectStandings` unchanged — this is purely a
 * "run the engine twice per candidate and diff" scan, so it stays
 * consistent with every other what-if surface by construction.
 */
export function pivotalMatches(
	entries: SimulatorEntryPicks[],
	baseHypo: HypoWinners,
	fixtures: Fixture[],
	adv: Record<string, number>,
	myEntryId: string,
	limit = 3
): PivotalMatch[] {
	if (!entries.some((entry) => entry.entry_id === myEntryId)) return [];

	const base = resolveScenario(fixtures, baseHypo);

	const candidates: PivotalMatch[] = [];

	for (const [matchNumber, resolved] of base.matches) {
		if (resolved.winner) continue; // already settled (real or hypo) — not open
		const { home, away } = resolved;
		if (!isRealTeamName(home) || !isRealTeamName(away)) continue; // one side still a placeholder

		const branch = (winner: string): number | null => {
			const hypo = new Map(baseHypo);
			hypo.set(matchNumber, winner);
			const scenario = resolveScenario(fixtures, hypo);
			// Defensive: if the pick didn't actually resolve this match to the
			// intended winner (shouldn't happen given the isRealTeamName guard
			// above, but resolveScenario is the source of truth), skip it.
			if (scenario.matches.get(matchNumber)?.winner !== winner) return null;
			const rows = projectStandings(entries, scenario.reached, scenario.champion, adv);
			return myPosIn(rows, myEntryId);
		};

		const posIfHome = branch(home);
		const posIfAway = branch(away);
		if (posIfHome === null || posIfAway === null) continue;

		candidates.push({
			matchNumber,
			home,
			away,
			posIfHome,
			posIfAway,
			swing: Math.abs(posIfHome - posIfAway)
		});
	}

	candidates.sort((a, b) => {
		if (b.swing !== a.swing) return b.swing - a.swing;
		return a.matchNumber - b.matchNumber;
	});

	return candidates.slice(0, limit);
}
