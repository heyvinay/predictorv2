/**
 * Knockout points + progressing + missed-picks derivations (V4 Results).
 *
 * KO points are LINEUP-BANKED (v2.161.0): a pick pays the moment the team
 * is seeded into a stage fixture, not when the match finishes. So hits
 * render for scheduled and live KO fixtures too. Stage values are
 * stage-specific from scoring-rules (R32:20 … F:75) — never hardcoded.
 *
 * third_place fixtures live on the Finals tab but carry no advancement
 * value — no chips, no points.
 */

import type { BracketPrediction, Fixture } from '$types';
import type { RoundId } from '$lib/types/results';
import { ROUND_STAGE } from './resultsRounds';

/** Bracket API fields are PLURAL for QF/SF (display convention). */
const ROUND_TO_BRACKET_FIELD: Record<string, keyof BracketPrediction> = {
	r32: 'round_of_32',
	r16: 'round_of_16',
	qf: 'quarter_finals',
	sf: 'semi_finals',
	f: 'final'
};

/** Team names the entry picked to reach the given KO round. */
export function bracketPicksForRound(
	bracket: BracketPrediction | null,
	roundId: RoundId
): Set<string> {
	if (!bracket) return new Set();
	const field = ROUND_TO_BRACKET_FIELD[roundId];
	if (!field) return new Set();
	const value = bracket[field];
	return Array.isArray(value) ? new Set(value) : new Set();
}

/** Stage-specific advancement points for a KO round id. */
export function stagePointsForRound(
	advancement: Record<string, number>,
	roundId: RoundId
): number {
	const stage = ROUND_STAGE[roundId];
	return stage ? advancement[stage] ?? 0 : 0;
}

/** Per-fixture bracket hits.
 *
 *  Returns hits=0 when:
 *   - The fixture is the bronze-medal playoff (third_place earns no
 *     advancement points by design — see CLAUDE.md invariant).
 *   - EITHER side is still a slot placeholder (string contains a digit,
 *     e.g. "slot:round_of_32:537416:home"). A half-resolved fixture
 *     like "Germany vs slot:..." would otherwise count Germany's hit
 *     into the round subtotal while the row itself displays as TBD —
 *     the production doubling bug from v2.183.2.
 *
 *  When a slot placeholder is present, both `home` and `away` are
 *  returned as `false` so callers that show pick chips per side don't
 *  light up the resolved side either (consistent with the
 *  "round-not-yet-resolvable" visual state).
 */
export function fixtureKoHits(
	fixture: Fixture,
	roundPicks: Set<string>
): { home: boolean; away: boolean; hits: number } {
	if (fixture.stage === 'third_place') {
		return { home: false, away: false, hits: 0 };
	}
	// Per-side seeded check (v2.184.x — same fix as FixtureRowKo).
	// Partial resolution: R16 home is the R32 winner, away still TBD —
	// the resolved side MUST be allowed to count its hit, otherwise the
	// Round Total shows 0 even though the row visibly displays +30×1.
	// Prior binary `seeded` flag zeroed everything if either side held a
	// slot:* placeholder, hiding the user's banked points from the
	// Round Total subtotal.
	const homeSeeded = !!fixture.home_team && !fixture.home_team.startsWith('slot:');
	const awaySeeded = !!fixture.away_team && !fixture.away_team.startsWith('slot:');
	const home = homeSeeded && roundPicks.has(fixture.home_team);
	const away = awaySeeded && roundPicks.has(fixture.away_team);
	return { home, away, hits: (home ? 1 : 0) + (away ? 1 : 0) };
}

/** Winners of FINISHED fixtures, split by next-round bracket membership. */
export function progressingSplit(
	fixtures: Fixture[],
	nextRoundPicks: Set<string>
): { inNext: string[]; notInNext: string[] } {
	const winners: string[] = [];
	for (const f of fixtures) {
		if (f.status !== 'finished' || !f.score) continue;
		if (f.stage === 'third_place') continue;
		if (f.score.outcome === '1') winners.push(f.home_team);
		else if (f.score.outcome === '2') winners.push(f.away_team);
		// 'X' on a finished knockout shouldn't happen (ET/pens resolve it);
		// skip defensively rather than guessing.
	}
	return {
		inNext: winners.filter((w) => nextRoundPicks.has(w)),
		notInNext: winners.filter((w) => !nextRoundPicks.has(w))
	};
}

/** Placeholder seed labels look like "1A" / "3ABCDF" / "W49" — short and
 *  containing digits. Real team names don't. */
function lineupSeeded(fixtures: Fixture[]): boolean {
	return (
		fixtures.length > 0 &&
		fixtures.every((f) => !/\d/.test(f.home_team) && !/\d/.test(f.away_team))
	);
}

/** Bracket picks for a KO round that never made the actual lineup (v2.184.x).
 *
 *  Generalises the older `missedR32Picks` for every knockout stage:
 *   - R32: picks that didn't qualify out of the group stage
 *   - R16: R16 picks whose team didn't survive R32
 *   - QF: QF picks whose team didn't survive R16
 *   - ... and so on
 *
 *  Gated by `lineupSeeded()` so we only return ✗ misses once we KNOW
 *  the round's lineup is fully resolved. During partial resolution
 *  (e.g. R16 with some R32s still scheduled) we return [] — the
 *  consuming card should then render its "lineup pending" state rather
 *  than tentative misses.
 *
 *  Third-place fixtures are excluded — unscored stage per the CLAUDE.md
 *  invariant. R32 has no third_place but later rounds inherit the
 *  filter defensively.
 */
export function missedPicksForRound(
	roundFixtures: Fixture[],
	roundPicks: Set<string>
): string[] {
	if (!lineupSeeded(roundFixtures)) return [];
	const seeded = new Set<string>();
	for (const f of roundFixtures) {
		if (f.stage === 'third_place') continue;
		seeded.add(f.home_team);
		seeded.add(f.away_team);
	}
	return [...roundPicks].filter((team) => !seeded.has(team)).sort();
}

/** Whether `roundFixtures` is fully resolved (no `slot:*` placeholders
 *  on either side). Surfaced for callers that need to gate UI states
 *  (e.g. show "lineup pending" copy on the RoundPicksCard until the
 *  upstream round finishes).
 */
export function isRoundLineupSeeded(roundFixtures: Fixture[]): boolean {
	return lineupSeeded(roundFixtures);
}

/** Teams from `roundPicks` already seeded into `roundFixtures` as a real
 *  (non-slot) name on either side. Works per-side so partial-resolution
 *  fixtures (one side real, one side slot:) still credit the confirmed half.
 *
 *  Used by RoundPicksCard's three-state pill renderer: ✓ confirmed,
 *  ✗ missed, — pending. Only meaningful when `isRoundLineupSeeded` is false;
 *  when true, `missedPicksForRound` already handles the full settled render.
 */
export function confirmedPicksForRound(
	roundFixtures: Fixture[],
	roundPicks: Set<string>
): Set<string> {
	const confirmed = new Set<string>();
	for (const f of roundFixtures) {
		if (f.stage === 'third_place') continue;
		if (f.home_team && !f.home_team.startsWith('slot:') && roundPicks.has(f.home_team)) {
			confirmed.add(f.home_team);
		}
		if (f.away_team && !f.away_team.startsWith('slot:') && roundPicks.has(f.away_team)) {
			confirmed.add(f.away_team);
		}
	}
	return confirmed;
}

/** Picks that can be marked definitively ✗ missed when the round lineup
 *  is NOT yet fully seeded.
 *
 *  A team is missed if and only if they have been eliminated from the
 *  tournament — i.e. they lost a finished KO fixture at any prior stage.
 *  Checking only the immediate previous round was wrong: a team still in
 *  R32 (not yet in any R16 fixture) was falling through as "not in inPlay"
 *  and being wrongly marked ✗ on the QF/SF/Finals chip strips.
 *
 *  Two elimination signals:
 *  1. Team appears as the LOSER in any finished KO fixture (any stage).
 *  2. R32 is fully seeded (all group stage done) and the team is absent
 *     from every R32 fixture — they didn't qualify from their group.
 *
 *  `allKoFixtures` = every KO-stage fixture (R32 through Final).
 */
export function partialMissedPicksForRound(
	roundPicks: Set<string>,
	confirmed: Set<string>,
	allKoFixtures: Fixture[]
): string[] {
	// Build eliminated set: losers of finished KO fixtures.
	const eliminated = new Set<string>();
	for (const f of allKoFixtures) {
		if (f.stage === 'third_place') continue;
		if (f.status !== 'finished' || !f.score) continue;
		const homeReal = !!f.home_team && !f.home_team.startsWith('slot:');
		const awayReal = !!f.away_team && !f.away_team.startsWith('slot:');
		if (f.score.outcome === '1' && awayReal) eliminated.add(f.away_team);
		else if (f.score.outcome === '2' && homeReal) eliminated.add(f.home_team);
	}

	// If R32 is fully seeded, teams absent from every R32 fixture missed
	// the group stage entirely.
	const r32 = allKoFixtures.filter((f) => f.stage === 'round_of_32');
	const r32FullySeeded =
		r32.length > 0 &&
		r32.every(
			(f) =>
				!!f.home_team &&
				!f.home_team.startsWith('slot:') &&
				!!f.away_team &&
				!f.away_team.startsWith('slot:')
		);
	const r32Teams = r32FullySeeded
		? new Set(r32.flatMap((f) => [f.home_team, f.away_team]))
		: null;

	return [...roundPicks]
		.filter((t) => {
			if (confirmed.has(t)) return false;
			if (eliminated.has(t)) return true;
			if (r32Teams !== null && !r32Teams.has(t)) return true;
			return false;
		})
		.sort();
}

/** @deprecated Use `missedPicksForRound`. Kept as an alias so existing
 *  tests + any straggler callers don't break — both delegate to the
 *  same implementation. */
export function missedR32Picks(
	r32Fixtures: Fixture[],
	r32Picks: Set<string>
): string[] {
	return missedPicksForRound(r32Fixtures, r32Picks);
}
