/**
 * Group Standings reality-check overlay — pure derivations.
 *
 * Answers the pool member's question: "do my picked qualifiers match
 * the current group standings, and does the order matter for R32?"
 * Every function here is pure (fixtures/predictions/standings in,
 * derived UI state out) so the whole overlay is unit-testable without
 * a running Svelte component.
 *
 * Composes existing tiebreaker + bracket-resolution machinery rather
 * than reimplementing it:
 *   - `calculateGroupStandings()` (standings.ts) for predicted
 *     per-group standings from the entry's own score predictions.
 *   - `getQualifyingThirdPlaceTeamsWithWarnings()` (bracketResolver.ts)
 *     for the predicted best-3rd cohort + rank (FIFA tiebreak chain).
 *   - `initializeBracketState()` (bracketResolver.ts) for the
 *     projected R32 lineup, including the FIFA Annex C third-place
 *     permutation table.
 */

import type { Fixture, MatchPrediction, BracketPrediction } from '$types';
import type { BonusQuestion } from '$api/bonus';
import type { BonusPredictionRead } from '$lib/types/leaderboard';
import { calculateGroupStandings, type TeamStanding } from './standings';
import {
	getQualifyingThirdPlaceTeamsWithWarnings,
	initializeBracketState,
	type GroupStandingsMap
} from './bracketResolver';
import { ROUND_OF_32 } from '$lib/config/bracketConfig';
import { groupGoalsSuperlatives } from './goalsSuperlatives';

// ---------------------------------------------------------------------------
// Predicted standings (from the entry's own group-stage score picks)
// ---------------------------------------------------------------------------

/** Builds a GroupStandingsMap from an entry's predicted scores. */
export function predictedStandingsMap(
	fixtures: Fixture[],
	predictionsByFixtureId: Map<string, MatchPrediction>
): GroupStandingsMap {
	const groups = new Set<string>();
	for (const f of fixtures) {
		if (f.stage === 'group' && f.group) groups.add(f.group);
	}
	const map: GroupStandingsMap = {};
	for (const group of groups) {
		const groupFixtures = fixtures.filter((f) => f.stage === 'group' && f.group === group);
		map[group] = calculateGroupStandings(groupFixtures, predictionsByFixtureId, group);
	}
	return map;
}

// ---------------------------------------------------------------------------
// Group-card PICK marker + two-dot tracker
// ---------------------------------------------------------------------------

export type PickSlotState = 'hit' | 'swap' | 'warn' | 'miss' | 'up' | null;

/**
 * Marker state for one row of an actual-standings group table, given
 * the entry's top-2 predicted picks for that group.
 *
 *   hit  — team is one of the entry's top-2 picks AND sits in the same slot.
 *   swap — team is one of the entry's top-2 picks but in the OTHER top-2 slot.
 *   warn — team is one of the entry's top-2 picks but has slipped to 3rd
 *          (still alive via best-3rd — WC26's top-2 + best-3rd format).
 *   miss — team is one of the entry's top-2 picks but is currently 4th (out).
 *   up   — team is NOT one of the entry's picks but is currently in the
 *          top-2 (a surprise qualifier the entry didn't back).
 *   null — team is neither picked nor currently qualifying.
 */
export function entryPickSlotState(
	team: string,
	actualRank: 1 | 2 | 3 | 4,
	predictedTop2: [string | undefined, string | undefined]
): PickSlotState {
	const [pick1, pick2] = predictedTop2;
	const isPicked = team === pick1 || team === pick2;
	const pickedSlot = team === pick1 ? 1 : team === pick2 ? 2 : null;

	if (isPicked) {
		if (actualRank === pickedSlot) return 'hit';
		if (actualRank === 1 || actualRank === 2) return 'swap';
		if (actualRank === 3) return 'warn';
		return 'miss';
	}
	if (actualRank === 1 || actualRank === 2) return 'up';
	return null;
}

export type QDotState = 'hit' | 'swap' | 'miss';

/** Two-dot header summary — one dot per entry pick, in predicted-slot order. */
export function qtrackFromEntry(
	predictedTop2: [string | undefined, string | undefined],
	actualStandings: TeamStanding[]
): [QDotState, QDotState] {
	const rankOf = (team: string | undefined): 1 | 2 | 3 | 4 | null => {
		if (!team) return null;
		const idx = actualStandings.findIndex((s) => s.team === team);
		return idx === -1 ? null : ((idx + 1) as 1 | 2 | 3 | 4);
	};
	const dotFor = (team: string | undefined): QDotState => {
		const rank = rankOf(team);
		if (rank === null) return 'miss';
		const state = entryPickSlotState(team as string, rank, predictedTop2);
		if (state === 'hit') return 'hit';
		if (state === 'swap') return 'swap';
		return 'miss'; // warn (bubble) and miss both read as the "at risk" dot colour
	};
	return [dotFor(predictedTop2[0]), dotFor(predictedTop2[1])];
}

// ---------------------------------------------------------------------------
// Group status (how many matchdays remain)
// ---------------------------------------------------------------------------

export type GroupStatus = 'final' | 'oneToPlay' | 'twoToPlay' | 'upcoming';

/** Filter chip keys for the group grid — 'all' plus one per risk bucket. */
export type GroupFilter = 'all' | 'locked' | 'atRisk' | 'orderSwap' | 'upcoming';

/** Derives group status from the minimum `played` count across its 4 teams. */
export function groupStatusFromStandings(standings: TeamStanding[]): GroupStatus {
	if (standings.length === 0) return 'upcoming';
	const minPlayed = Math.min(...standings.map((s) => s.played));
	const remaining = 3 - minPlayed;
	if (remaining <= 0) return 'final';
	if (remaining === 1) return 'oneToPlay';
	if (remaining === 2) return 'twoToPlay';
	return 'upcoming';
}

/**
 * True while any group still has a team with fewer than 3 matches
 * played. Single source of truth for two call sites that must never
 * drift apart: the "refreshes every minute" banner copy, and the
 * poll-loop gate that stops hitting the standings endpoint once the
 * group stage is fully settled (nothing left there can change).
 */
export function anyGroupIncomplete(standingsByGroup: Record<string, { played: number }[]>): boolean {
	return Object.values(standingsByGroup).some((g) => g.some((t) => t.played < 3));
}

// ---------------------------------------------------------------------------
// Verdict + qualification-math micro-line
// ---------------------------------------------------------------------------

export type VerdictTone = 'good' | 'warn' | 'miss' | 'pend';

export interface GroupVerdict {
	tone: VerdictTone;
	label: string;
	detail: string;
	needs: string | null;
}

/**
 * Finds the team currently occupying `predictedTop2`'s "missing" slot —
 * used to name who surprised the entry's pick out.
 */
function surpriseReplacement(
	predictedTop2: [string | undefined, string | undefined],
	actualStandings: TeamStanding[]
): string | null {
	const top2Actual = actualStandings.slice(0, 2).map((s) => s.team);
	const surprise = top2Actual.find((t) => t !== predictedTop2[0] && t !== predictedTop2[1]);
	return surprise ?? null;
}

/**
 * Best-effort qualification-math hint for a still-open group where a
 * pick has slipped. Deliberately NOT a full constraint solver — it
 * names the team's next remaining group fixture (and the rival's, if
 * relevant) rather than proving mathematical qualification scenarios.
 * Returns null when the group is final (nothing left to influence) or
 * when there's nothing at risk to explain.
 */
export function qualificationNeeds(
	team: string,
	group: string,
	fixtures: Fixture[],
	rivalTeam: string | null
): string | null {
	const remaining = fixtures.filter(
		(f) =>
			f.stage === 'group' &&
			f.group === group &&
			f.status !== 'finished' &&
			(f.home_team === team || f.away_team === team)
	);
	if (remaining.length === 0) return null;

	const opponentIn = (f: Fixture, referenceTeam: string): string =>
		f.home_team === referenceTeam ? f.away_team : f.home_team;

	if (remaining.length === 1) {
		const opp = opponentIn(remaining[0], team);
		const rivalRemaining = rivalTeam
			? fixtures.filter(
					(f) =>
						f.stage === 'group' &&
						f.group === group &&
						f.status !== 'finished' &&
						(f.home_team === rivalTeam || f.away_team === rivalTeam)
				)
			: [];
		if (rivalTeam && rivalRemaining.length > 0) {
			const rivalOpp = opponentIn(rivalRemaining[0], rivalTeam);
			return `${team} needs a win vs ${opp} AND ${rivalTeam} to drop points against ${rivalOpp}.`;
		}
		return `${team} needs a win vs ${opp} to have a realistic path back.`;
	}

	return `${team} needs to win their remaining ${remaining.length} fixtures to have a realistic path back.`;
}

/**
 * Verdict + optional needs line for a group card, given the entry's
 * top-2 predicted picks and the group's actual standings.
 */
export function groupVerdict(
	predictedTop2: [string | undefined, string | undefined],
	actualStandings: TeamStanding[],
	group: string,
	fixtures: Fixture[]
): GroupVerdict {
	const status = groupStatusFromStandings(actualStandings);
	const rankOf = (team: string | undefined): 1 | 2 | 3 | 4 | null => {
		if (!team) return null;
		const idx = actualStandings.findIndex((s) => s.team === team);
		return idx === -1 ? null : ((idx + 1) as 1 | 2 | 3 | 4);
	};

	if (status === 'upcoming') {
		return { tone: 'pend', label: 'Group not yet underway', detail: 'Kickoff pending', needs: null };
	}

	const rank1 = rankOf(predictedTop2[0]);
	const rank2 = rankOf(predictedTop2[1]);
	const states = [
		predictedTop2[0] && rank1 ? entryPickSlotState(predictedTop2[0], rank1, predictedTop2) : null,
		predictedTop2[1] && rank2 ? entryPickSlotState(predictedTop2[1], rank2, predictedTop2) : null
	];

	const detail = status === 'final' ? 'R32 seed as predicted' : leftLabel(status);

	if (states.every((s) => s === 'hit')) {
		return {
			tone: 'good',
			label:
				status === 'final' ? 'Both picks locked, correct order' : 'Both picks in top-2, correct order',
			detail,
			needs: null
		};
	}
	if (states.every((s) => s === 'swap' || s === 'hit')) {
		return {
			tone: 'warn',
			label: 'Right teams, wrong order',
			detail: status === 'final' ? 'R32 draw flips' : 'Order can still swap',
			needs: null
		};
	}

	// One or both picks have slipped — find the worse of the two states.
	const missIdx = states.findIndex((s) => s === 'miss');
	const warnIdx = states.findIndex((s) => s === 'warn');
	if (missIdx !== -1) {
		const team = predictedTop2[missIdx]!;
		const replacement = surpriseReplacement(predictedTop2, actualStandings);
		const label = replacement
			? `Lost a qualifier · ${team} out, ${replacement} in`
			: `Lost a qualifier · ${team} out`;
		return {
			tone: 'miss',
			label,
			detail: status === 'final' ? 'R32 pairing shifts' : 'Path narrow',
			needs: status === 'final' ? null : qualificationNeeds(team, group, fixtures, replacement)
		};
	}
	if (warnIdx !== -1) {
		const team = predictedTop2[warnIdx]!;
		const replacement = surpriseReplacement(predictedTop2, actualStandings);
		return {
			tone: 'warn',
			label: `${team} slipped to best-3rd bubble`,
			detail: 'Recoverable',
			needs: status === 'final' ? null : qualificationNeeds(team, group, fixtures, replacement)
		};
	}

	return { tone: 'pend', label: 'Both picks won openers', detail: leftLabel(status), needs: null };
}

function leftLabel(status: GroupStatus): string {
	if (status === 'oneToPlay') return '1 MD left';
	if (status === 'twoToPlay') return '2 MDs left';
	return 'Kickoff pending';
}

// ---------------------------------------------------------------------------
// Best-3rd table overlay (rank-aware — position determines R32 slot)
// ---------------------------------------------------------------------------

export type BestThirdMarker = 'hit' | 'swap' | 'miss' | 'up' | null;

export interface BestThirdRowState {
	marker: BestThirdMarker;
	userRank: number | null;
	tooltip: string;
}

/** The entry's implied best-3rd cohort + rank (1-8), from predicted standings. */
export function predictedBestThirdRankMap(
	predictions: GroupStandingsMap
): Map<string, { rank: number; group: string }> {
	const { qualifying } = getQualifyingThirdPlaceTeamsWithWarnings(predictions);
	const map = new Map<string, { rank: number; group: string }>();
	qualifying.forEach(({ team, group }, i) => map.set(team, { rank: i + 1, group }));
	return map;
}

/** Five-state overlay marker for one row of the actual best-3rd table. */
export function bestThirdOverlayState(
	team: string,
	actualRank: number,
	userRankMap: Map<string, { rank: number; group: string }>
): BestThirdRowState {
	const userEntry = userRankMap.get(team);
	const inTop8 = actualRank <= 8;

	if (userEntry && inTop8) {
		if (userEntry.rank === actualRank) {
			return { marker: 'hit', userRank: userEntry.rank, tooltip: 'Perfect · same team, same rank' };
		}
		return {
			marker: 'swap',
			userRank: userEntry.rank,
			tooltip: `You had ${team} at #${userEntry.rank}`
		};
	}
	if (userEntry && !inTop8) {
		return {
			marker: 'miss',
			userRank: userEntry.rank,
			tooltip: `You had ${team} at #${userEntry.rank} — missed the cut`
		};
	}
	if (!userEntry && inTop8) {
		return { marker: 'up', userRank: null, tooltip: `You didn't predict ${team} as a best-3rd qualifier` };
	}
	return { marker: null, userRank: null, tooltip: '' };
}

export interface DroppedBestThirdPick {
	team: string;
	userRank: number;
	currentGroupPosition: number | null;
}

/**
 * Teams the entry predicted into the best-3rd top-8 that AREN'T even
 * in the actual best-3rd table (currently 4th of their own group —
 * i.e. not a 3rd-placed team at all). Distinct from a missed-cut
 * (predicted top-8, actually ranked 9+ among real 3rd-placed teams).
 */
export function bestThirdDroppedPicks(
	userRankMap: Map<string, { rank: number; group: string }>,
	actualThirdPlaceTable: TeamStanding[],
	actualStandingsMap: GroupStandingsMap
): DroppedBestThirdPick[] {
	const actualThirdTeams = new Set(actualThirdPlaceTable.map((t) => t.team));
	const out: DroppedBestThirdPick[] = [];
	for (const [team, { rank, group }] of userRankMap) {
		if (actualThirdTeams.has(team)) continue; // still a 3rd-placed team, just ranked differently
		const groupStandings = actualStandingsMap[group] ?? [];
		const pos = groupStandings.findIndex((s) => s.team === team);
		out.push({ team, userRank: rank, currentGroupPosition: pos === -1 ? null : pos + 1 });
	}
	return out.sort((a, b) => a.userRank - b.userRank);
}

export interface BestThirdShift {
	team: string;
	userRank: number;
	actualRank: number | null;
	magnitude: number;
}

export interface BestThirdShiftSummary {
	perfect: number;
	rankSwap: number;
	missedCut: number;
	surpriseIn: number;
	droppedEntirely: number;
	biggestShifts: BestThirdShift[];
}

/** Rollup stats for the best-3rd summary strip + "biggest shifts" callout. */
export function bestThirdShiftSummary(
	userRankMap: Map<string, { rank: number; group: string }>,
	actualThirdPlaceTable: TeamStanding[],
	actualStandingsMap: GroupStandingsMap,
	topShifts = 2
): BestThirdShiftSummary {
	let perfect = 0;
	let rankSwap = 0;
	let missedCut = 0;
	let surpriseIn = 0;
	const shifts: BestThirdShift[] = [];

	actualThirdPlaceTable.forEach((row, i) => {
		const actualRank = i + 1;
		const state = bestThirdOverlayState(row.team, actualRank, userRankMap);
		if (state.marker === 'hit') perfect++;
		else if (state.marker === 'swap') {
			rankSwap++;
			shifts.push({
				team: row.team,
				userRank: state.userRank!,
				actualRank,
				magnitude: Math.abs(state.userRank! - actualRank)
			});
		} else if (state.marker === 'miss') missedCut++;
		else if (state.marker === 'up') surpriseIn++;
	});

	const dropped = bestThirdDroppedPicks(userRankMap, actualThirdPlaceTable, actualStandingsMap);
	const droppedEntirely = dropped.length;
	for (const d of dropped) {
		shifts.push({ team: d.team, userRank: d.userRank, actualRank: null, magnitude: Infinity });
	}

	shifts.sort((a, b) => b.magnitude - a.magnitude);

	return {
		perfect,
		rankSwap,
		missedCut,
		surpriseIn,
		droppedEntirely,
		biggestShifts: shifts.slice(0, topShifts)
	};
}

// ---------------------------------------------------------------------------
// R32 impact preview
// ---------------------------------------------------------------------------

export interface R32Pairing {
	matchNumber: number;
	home: string | null;
	away: string | null;
}

/** Projected R32 lineup if the given standings map were final right now. */
export function projectedR32Pairings(standingsMap: GroupStandingsMap): R32Pairing[] {
	const state = initializeBracketState(standingsMap);
	return ROUND_OF_32.map((m) => ({
		matchNumber: m.matchNumber,
		home: state.matchResults[m.matchNumber]?.homeTeam ?? null,
		away: state.matchResults[m.matchNumber]?.awayTeam ?? null
	}));
}

export interface R32Difference {
	matchNumber: number;
	predicted: { home: string | null; away: string | null };
	projected: { home: string | null; away: string | null };
}

/**
 * Compares the entry's stored R32 bracket prediction against the
 * projected lineup. Returns only pairings that differ (unordered
 * team-set comparison per match, so a home/away swap alone doesn't
 * count as a difference).
 */
export function r32DifferencesVsPrediction(
	projected: R32Pairing[],
	entryBracket: BracketPrediction
): R32Difference[] {
	const out: R32Difference[] = [];
	ROUND_OF_32.forEach((m, i) => {
		const predictedHome = entryBracket.round_of_32?.[i * 2] ?? null;
		const predictedAway = entryBracket.round_of_32?.[i * 2 + 1] ?? null;
		const proj = projected.find((p) => p.matchNumber === m.matchNumber);
		if (!proj) return;

		const predictedSet = new Set([predictedHome, predictedAway].filter(Boolean));
		const projectedSet = new Set([proj.home, proj.away].filter(Boolean));
		const same =
			predictedSet.size === projectedSet.size &&
			[...predictedSet].every((t) => projectedSet.has(t));
		if (!same) {
			out.push({
				matchNumber: m.matchNumber,
				predicted: { home: predictedHome, away: predictedAway },
				projected: { home: proj.home, away: proj.away }
			});
		}
	});
	return out;
}

// ---------------------------------------------------------------------------
// Group-phase bonus mirror (Q1 most-scored / Q2 most-conceded)
// ---------------------------------------------------------------------------

export type BonusLeaderStatus = 'leading' | 'alive' | 'fading' | 'missed';

export interface GroupPhaseBonusPickState {
	userPick: string | null;
	userTally: number;
	leaders: string[];
	leaderTally: number;
	status: BonusLeaderStatus;
}

export interface GroupPhaseBonusState {
	mostScored: GroupPhaseBonusPickState | null;
	mostConceded: GroupPhaseBonusPickState | null;
}

function findGroupStageQuestion(
	questions: BonusQuestion[],
	matchLabel: (label: string) => boolean,
	fallbackIndex: number
): BonusQuestion | null {
	const groupStage = questions.filter((q) => q.category === 'group_stage');
	const byLabel = groupStage.find((q) => matchLabel(q.label.toLowerCase()));
	return byLabel ?? groupStage[fallbackIndex] ?? null;
}

function pickState(
	userPick: string | null,
	tallyOf: Map<string, number>,
	leaders: string[],
	leaderTally: number
): GroupPhaseBonusPickState | null {
	if (!userPick) return null;
	const userTally = tallyOf.get(userPick) ?? 0;
	let status: BonusLeaderStatus;
	if (leaders.includes(userPick)) status = 'leading';
	else if (leaderTally - userTally <= 1) status = 'alive';
	else if (leaderTally - userTally <= 3) status = 'fading';
	else status = 'missed';
	return { userPick, userTally, leaders, leaderTally, status };
}

/**
 * Group-phase bonus mirror (Q1 most-scored / Q2 most-conceded).
 * Reuses `groupGoalsSuperlatives()` — the same derivation backing the
 * Insights tab's Tournament Superlatives card — so both surfaces
 * always agree on who's leading.
 */
export function groupPhaseBonusState(
	fixtures: Fixture[],
	bonusQuestions: BonusQuestion[],
	bonusAnswers: BonusPredictionRead[]
): GroupPhaseBonusState {
	const { mostScored, mostConceded } = groupGoalsSuperlatives(fixtures);
	const { gf, ga } = ((): { gf: Map<string, number>; ga: Map<string, number> } => {
		// Rebuild the raw maps once for tally lookups (leaders already known).
		const gfMap = new Map<string, number>();
		const gaMap = new Map<string, number>();
		for (const f of fixtures) {
			if (f.stage !== 'group' || f.status !== 'finished' || !f.score) continue;
			gfMap.set(f.home_team, (gfMap.get(f.home_team) ?? 0) + f.score.home_score);
			gfMap.set(f.away_team, (gfMap.get(f.away_team) ?? 0) + f.score.away_score);
			gaMap.set(f.home_team, (gaMap.get(f.home_team) ?? 0) + f.score.away_score);
			gaMap.set(f.away_team, (gaMap.get(f.away_team) ?? 0) + f.score.home_score);
		}
		return { gf: gfMap, ga: gaMap };
	})();

	const scoredQ = findGroupStageQuestion(bonusQuestions, (l) => l.includes('scor'), 0);
	const concededQ = findGroupStageQuestion(bonusQuestions, (l) => l.includes('conced'), 1);

	const scoredAnswer = scoredQ
		? (bonusAnswers.find((a) => a.question_id === scoredQ.id)?.answer ?? null)
		: null;
	const concededAnswer = concededQ
		? (bonusAnswers.find((a) => a.question_id === concededQ.id)?.answer ?? null)
		: null;

	return {
		mostScored: pickState(scoredAnswer, gf, mostScored.keys, mostScored.n),
		mostConceded: pickState(concededAnswer, ga, mostConceded.keys, mostConceded.n)
	};
}
