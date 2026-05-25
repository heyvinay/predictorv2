/**
 * Smart Fill — auto-generate predictions from FIFA ranking points.
 *
 * Implements the algorithm specced in
 * `C:\Users\vinay\.claude\plans\prompt-1-i-need-eventual-thimble.md`:
 *
 *   1. diff = abs(home_pts - away_pts)
 *   2. Map diff -> base scoreline by tier (stronger team always wins)
 *   3. Seeded variation (hash(user_id, fixture_id) -> tier wobble)
 *   4. Orient so the stronger team's score is on the correct side
 *
 * Variation distribution:
 *   - Draw tier (base 1-1): 50% stays 1-1, 20% -> 0-0, 20% -> 2-2, 10% -> 3-3
 *   - Non-draw tiers (base w-l): 60% stays w-l, 20% loser+1, 10% winner+1,
 *     10% both+1
 *
 * Per spec: "stronger team always wins" — variation only wobbles the
 * scoreline, never the outcome direction.
 *
 * IMPORTANT: ranking points are hardcoded here for v1. Replacing this
 * lookup with a backend-served table (scraped from FIFA monthly) is the
 * intended follow-up — see the plan for the proposed
 * /admin/rankings/sync endpoint.
 */

// Approximate FIFA ranking points (late 2025 snapshot) for the 48
// WC 2026 qualifying teams + a handful of common alt-spellings the
// fixture data uses ("South Korea" / "Korea Republic" etc).
//
// These are intentionally approximate — the algorithm uses *differences*
// between teams, so as long as the relative ordering is roughly correct
// the predictions will read as plausible.
export const FIFA_POINTS: Record<string, number> = {
	Argentina: 1886,
	France: 1854,
	Spain: 1850,
	England: 1812,
	Brazil: 1779,
	Portugal: 1778,
	Netherlands: 1754,
	Belgium: 1735,
	Croatia: 1714,
	Italy: 1714,
	Morocco: 1694,
	Uruguay: 1679,
	Colombia: 1679,
	Germany: 1660,
	Switzerland: 1654,
	'United States': 1647,
	USA: 1647,
	Japan: 1646,
	Mexico: 1640,
	Senegal: 1636,
	Iran: 1632,
	Denmark: 1631,
	Austria: 1583,
	'South Korea': 1576,
	'Korea Republic': 1576,
	Ecuador: 1568,
	'Ivory Coast': 1564,
	"Cote d'Ivoire": 1564,
	Ukraine: 1559,
	Australia: 1554,
	Sweden: 1538,
	Turkey: 1521,
	'Republic of Ireland': 1480,
	Norway: 1497,
	Wales: 1471,
	Czechia: 1452,
	'Czech Republic': 1452,
	Algeria: 1495,
	Egypt: 1505,
	Nigeria: 1499,
	Canada: 1485,
	'Saudi Arabia': 1428,
	Qatar: 1397,
	Iraq: 1410,
	Cameroon: 1457,
	Tunisia: 1481,
	'South Africa': 1430,
	Mali: 1466,
	'Cape Verde Islands': 1387,
	'Cape Verde': 1387,
	'Bosnia-Herzegovina': 1396,
	'Bosnia and Herzegovina': 1396,
	Slovakia: 1452,
	Romania: 1471,
	Greece: 1455,
	Albania: 1450,
	Honduras: 1297,
	Jamaica: 1372,
	Panama: 1395,
	Bolivia: 1395,
	Venezuela: 1497,
	'Costa Rica': 1395,
	Paraguay: 1463,
	Peru: 1465,
	Chile: 1497,
	'New Zealand': 1183,
	'El Salvador': 1192,
	Guatemala: 1357,
	'Trinidad and Tobago': 1224,
	Curacao: 1281
};

/** Lookup with safe default — unknown teams treated as mid-table. */
export function fifaPoints(teamName: string): number {
	return FIFA_POINTS[teamName] ?? 1300;
}

/** Tier table -> base scoreline (stronger, weaker). */
function baseScoreline(diff: number): [number, number] {
	if (diff < 40) return [1, 1];
	if (diff < 100) return [1, 0];
	if (diff < 180) return [2, 1];
	if (diff < 260) return [2, 0];
	if (diff < 340) return [3, 1];
	if (diff < 420) return [3, 0];
	if (diff < 490) return [4, 1];
	return [5, 0];
}

/**
 * Fast deterministic hash of a string to a non-negative 32-bit int.
 * Used to seed the per-(user, fixture) variation roll.
 */
function hashString(s: string): number {
	let h = 2166136261; // FNV offset basis
	for (let i = 0; i < s.length; i++) {
		h ^= s.charCodeAt(i);
		h = (h * 16777619) >>> 0; // FNV prime, force uint32
	}
	return h >>> 0;
}

/**
 * Seeded float in [0, 1). Deterministic for a given seed.
 * Uses a single mulberry32 step — perfectly fine for "pick a tier wobble".
 */
function seededRoll(seed: number): number {
	let t = (seed + 0x6d2b79f5) >>> 0;
	t = Math.imul(t ^ (t >>> 15), t | 1);
	t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
	return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}

/**
 * Apply seeded variation to a base scoreline. Respects the hard
 * "stronger team always wins" constraint (variation only wobbles the
 * scoreline, never the outcome direction).
 *
 * @returns [winner_score, loser_score]
 */
function applyVariation(base: [number, number], roll: number): [number, number] {
	const [w, l] = base;
	// Draw tier
	if (w === l && w === 1) {
		if (roll < 0.5) return [1, 1];
		if (roll < 0.7) return [0, 0];
		if (roll < 0.9) return [2, 2];
		return [3, 3];
	}
	// Non-draw tiers
	if (roll < 0.6) return [w, l];
	if (roll < 0.8) return [w, l + 1];
	if (roll < 0.9) return [w + 1, l];
	return [w + 1, l + 1];
}

/**
 * Compute a smart-fill score for a fixture.
 *
 * @param homeTeam  Home team name
 * @param awayTeam  Away team name
 * @param userId    User id (used in the seed so different users get
 *                  visibly different variations)
 * @param fixtureId Fixture id (used in the seed so each match
 *                  gets its own roll)
 * @returns [home_score, away_score]
 */
export function smartFillScoreline(
	homeTeam: string,
	awayTeam: string,
	userId: string,
	fixtureId: string
): [number, number] {
	const homePts = fifaPoints(homeTeam);
	const awayPts = fifaPoints(awayTeam);
	const diff = Math.abs(homePts - awayPts);

	const base = baseScoreline(diff);
	const seed = hashString(`${userId}:${fixtureId}`);
	const roll = seededRoll(seed);
	const [strong, weak] = applyVariation(base, roll);

	// Orient: stronger team's score goes to the appropriate side.
	if (homePts >= awayPts) {
		return [strong, weak];
	}
	return [weak, strong];
}

// ---------------------------------------------------------------------------
// Bracket auto-fill: "higher-ranked team always wins" per FIFA points
// ---------------------------------------------------------------------------

import {
	initializeBracketState,
	setMatchWinner,
	getDisplayMatches,
	bracketStateToPrediction,
	type GroupStandingsMap
} from './bracketResolver';
import type { BracketPrediction } from '$lib/types';

/**
 * Returns the winner of a head-to-head matchup based on FIFA ranking points.
 *
 * - Strict winner: team with higher fifaPoints() wins, every time.
 * - Equal points: deterministic seeded coin flip keyed on
 *   `${userId}:bracket:${matchKey}`. The "bracket:" prefix in the seed
 *   string keeps this draw-key namespace separate from the per-fixture
 *   variation seeds used by smartFillScoreline.
 */
export function pickHigherRanked(
	homeTeam: string,
	awayTeam: string,
	userId: string,
	matchKey: string
): string {
	const homePts = fifaPoints(homeTeam);
	const awayPts = fifaPoints(awayTeam);
	if (homePts > awayPts) return homeTeam;
	if (awayPts > homePts) return awayTeam;
	// Tie — seeded coin flip
	const seed = hashString(`${userId}:bracket:${matchKey}`);
	return seededRoll(seed) < 0.5 ? homeTeam : awayTeam;
}

/**
 * Auto-fill the full Phase 1 knockout bracket from the predicted group
 * standings. Walks R32 -> R16 -> QF -> SF -> Final -> 3rd-place,
 * picking the higher-ranked team in each pairing. Cascading is handled
 * by bracketResolver.setMatchWinner so later rounds' teams populate as
 * upstream winners are committed.
 *
 * Caller is responsible for ensuring `standings` contains every group's
 * top-4 (i.e. every group fixture must already have a prediction). If
 * the standings don't fully resolve to 32 teams, the returned
 * BracketPrediction will have null entries — caller should gate on this.
 */
export function smartFillBracket(
	standings: GroupStandingsMap,
	userId: string
): BracketPrediction {
	let state = initializeBracketState(standings);

	const ROUNDS = [
		'round_of_32',
		'round_of_16',
		'quarter_finals',
		'semi_finals',
		'final',
		'third_place'
	] as const;

	for (const round of ROUNDS) {
		// Re-read display matches each round because state cascades
		// populate later rounds' home/away after winners are set.
		const matches = getDisplayMatches(state, round);
		for (const m of matches) {
			if (m.homeTeam && m.awayTeam && !m.winner) {
				const winner = pickHigherRanked(
					m.homeTeam,
					m.awayTeam,
					userId,
					`match-${m.match.matchNumber}`
				);
				state = setMatchWinner(state, m.match.matchNumber, winner);
			}
		}
	}

	return bracketStateToPrediction(state);
}
