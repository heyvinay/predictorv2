/**
 * Tests for utils/standings.ts — the FIFA tiebreaker chain used to compute
 * the wizard's *predicted* group standings.
 *
 * The chain (FWC2026 Regulations, Article 13):
 *   points → H2H (points → GD → goals, recomputed per remaining subset)
 *         → overall GD → overall goals → alphabetical (+warning)
 *   i.e. head-to-head is applied BEFORE overall goal difference.
 *
 * Covered:
 *   - applyFifaTiebreakers directly with synthetic standings (3-way H2H
 *     separation, partial H2H + alphabetical sub-tie, no-H2H cross-group case)
 *   - calculateGroupStandingsWithWarnings end-to-end through Fixture+prediction
 *   - computeGroupStandingsMapWithWarnings aggregating warnings across groups
 */

import { describe, it, expect } from 'vitest';
import {
	applyFifaTiebreakers,
	calculateGroupStandings,
	calculateGroupStandingsWithWarnings,
	computeGroupStandingsMapWithWarnings,
	type TeamStanding
} from './standings';
import type { Fixture, MatchPrediction } from '$types';

// ---------------------------------------------------------------------------
// Fixture builders
// ---------------------------------------------------------------------------

function _ts(team: string, group: string, points: number, gd: number, gf = 0): TeamStanding {
	return {
		team,
		group,
		played: 3,
		won: 0,
		drawn: 0,
		lost: 0,
		goalsFor: gf,
		goalsAgainst: gf - gd,
		goalDifference: gd,
		points
	};
}

function _fixture(id: string, home: string, away: string, group = 'A'): Fixture {
	return {
		id,
		home_team: home,
		away_team: away,
		kickoff: '2026-06-11T19:00:00Z',
		stage: 'group',
		group,
		match_number: null,
		status: 'finished',
		minute: null,
		is_locked: true,
		time_until_lock: null,
		score: null,
		venue_city: null,
		venue_country: null,
		venue_country_code: null
	};
}

function _pred(id: string, homeScore: number, awayScore: number): [string, MatchPrediction] {
	return [
		id,
		{
			id: `pred-${id}`,
			entry_id: 'entry-test',
			fixture_id: id,
			home_score: homeScore,
			away_score: awayScore,
			phase: 'phase_1',
			locked_at: null,
			created_at: '2026-06-11T00:00:00Z',
			updated_at: '2026-06-11T00:00:00Z',
			is_locked: false
		}
	];
}

// ---------------------------------------------------------------------------
// applyFifaTiebreakers — direct unit tests
// ---------------------------------------------------------------------------

describe('applyFifaTiebreakers', () => {
	it('separates a clean overall ranking with no warnings', () => {
		const teams = [
			_ts('France', 'A', 9, 5, 7),
			_ts('Germany', 'A', 6, 2, 4),
			_ts('Spain', 'A', 3, 0, 2),
			_ts('Italy', 'A', 0, -7, 0)
		];
		const { sorted, warnings } = applyFifaTiebreakers(teams, [], new Map(), 'group_standings');
		expect(sorted.map((t) => t.team)).toEqual(['France', 'Germany', 'Spain', 'Italy']);
		expect(warnings).toEqual([]);
	});

	it('falls to alphabetical with a warning when no H2H matches are provided', () => {
		// Three teams tied on overall stats, no H2H to consult → alphabetical + warning.
		const teams = [
			_ts('Wales', 'A', 3, 0, 1),
			_ts('Senegal', 'A', 3, 0, 1),
			_ts('Iran', 'A', 3, 0, 1)
		];
		const { sorted, warnings } = applyFifaTiebreakers(
			teams,
			[],
			new Map(),
			'third_place_qualifying'
		);
		expect(sorted.map((t) => t.team)).toEqual(['Iran', 'Senegal', 'Wales']);
		expect(warnings.length).toBe(1);
		expect(warnings[0].tiedTeams).toEqual(['Iran', 'Senegal', 'Wales']);
		expect(warnings[0].context).toBe('third_place_qualifying');
	});

	it('uses H2H to separate a 3-way tie cleanly (no warning)', () => {
		// A, B, C all tied on overall (5pts, GD 0, GF 2). H2H mini-table:
		// A beats B, A beats C, B beats C → A=6 H2H pts, B=3, C=0.
		const teams = [
			_ts('Argentina', 'A', 5, 0, 2),
			_ts('Brazil', 'A', 5, 0, 2),
			_ts('Chile', 'A', 5, 0, 2)
		];
		const fixtures: Fixture[] = [
			_fixture('m1', 'Argentina', 'Brazil'),
			_fixture('m2', 'Brazil', 'Chile'),
			_fixture('m3', 'Argentina', 'Chile')
		];
		const predictions = new Map([_pred('m1', 1, 0), _pred('m2', 1, 0), _pred('m3', 1, 0)]);
		const { sorted, warnings } = applyFifaTiebreakers(
			teams,
			fixtures,
			predictions,
			'group_standings'
		);
		expect(sorted.map((t) => t.team)).toEqual(['Argentina', 'Brazil', 'Chile']);
		expect(warnings).toEqual([]);
	});

	it('partially resolves a tie via H2H then alphabetical on the sub-tie', () => {
		// A beats both B and C, but B and C draw → H2H mini-table:
		//   A = 6pts, B = 1pt, C = 1pt → A clear first; B/C tied on H2H → alphabetical.
		const teams = [
			_ts('Argentina', 'A', 5, 0, 2),
			_ts('Brazil', 'A', 5, 0, 2),
			_ts('Chile', 'A', 5, 0, 2)
		];
		const fixtures: Fixture[] = [
			_fixture('m1', 'Argentina', 'Brazil'),
			_fixture('m2', 'Brazil', 'Chile'),
			_fixture('m3', 'Argentina', 'Chile')
		];
		const predictions = new Map([_pred('m1', 1, 0), _pred('m2', 0, 0), _pred('m3', 1, 0)]);
		const { sorted, warnings } = applyFifaTiebreakers(
			teams,
			fixtures,
			predictions,
			'group_standings'
		);
		expect(sorted[0].team).toBe('Argentina');
		expect(sorted.slice(1).map((t) => t.team)).toEqual(['Brazil', 'Chile']);
		expect(warnings.length).toBe(1);
		expect(warnings[0].tiedTeams).toEqual(['Brazil', 'Chile']);
	});

	it('respects goal difference before goals-for in the overall sort', () => {
		const teams = [
			_ts('TeamHighGd', 'A', 6, +5, 5),
			_ts('TeamLowGd', 'A', 6, +1, 5)
		];
		const { sorted } = applyFifaTiebreakers(teams, [], new Map(), 'group_standings');
		expect(sorted[0].team).toBe('TeamHighGd');
	});

	it('respects goals-for after points and GD tie', () => {
		const teams = [_ts('Lo', 'A', 6, +2, 3), _ts('Hi', 'A', 6, +2, 5)];
		const { sorted } = applyFifaTiebreakers(teams, [], new Map(), 'group_standings');
		expect(sorted[0].team).toBe('Hi');
	});

	it('ranks the head-to-head winner above a team with better OVERALL GD (FWC2026 Art.13)', () => {
		// THE discriminating case: both level on points. "Bigger" has the better
		// overall goal difference (+5 vs +2), but "Winner" beat "Bigger" head-to-head.
		// FWC2026 Article 13 applies head-to-head BEFORE overall GD → Winner ranks first.
		// (The old overall-first order would have ranked Bigger first — this test locks
		// in the corrected behaviour.)
		const teams = [
			_ts('Bigger', 'A', 6, 5, 8), // better overall GD
			_ts('Winner', 'A', 6, 2, 4) // worse overall GD, but won the h2h
		];
		const fixtures: Fixture[] = [_fixture('m1', 'Winner', 'Bigger')];
		const predictions = new Map([_pred('m1', 1, 0)]); // Winner beat Bigger 1-0
		const { sorted, warnings } = applyFifaTiebreakers(
			teams,
			fixtures,
			predictions,
			'group_standings'
		);
		expect(sorted.map((t) => t.team)).toEqual(['Winner', 'Bigger']);
		expect(warnings).toEqual([]);
	});

	it('falls to overall GD after a head-to-head cycle (Art.13 Step 2 d)', () => {
		// 3 teams level on points; H2H is a perfect 1-0 cycle (each beats one, loses
		// one) → all equal on h2h points/GD/goals, so Step 1 separates no one.
		// Step 2 d) overall goal difference then decides: +4 > +2 > 0.
		const teams = [
			_ts('Cyc1', 'A', 6, 4, 6),
			_ts('Cyc2', 'A', 6, 2, 5),
			_ts('Cyc3', 'A', 6, 0, 4)
		];
		const fixtures: Fixture[] = [
			_fixture('m1', 'Cyc1', 'Cyc2'),
			_fixture('m2', 'Cyc2', 'Cyc3'),
			_fixture('m3', 'Cyc3', 'Cyc1')
		];
		const predictions = new Map([_pred('m1', 1, 0), _pred('m2', 1, 0), _pred('m3', 1, 0)]);
		const { sorted, warnings } = applyFifaTiebreakers(
			teams,
			fixtures,
			predictions,
			'group_standings'
		);
		expect(sorted.map((t) => t.team)).toEqual(['Cyc1', 'Cyc2', 'Cyc3']);
		expect(warnings).toEqual([]);
	});
});

// ---------------------------------------------------------------------------
// calculateGroupStandings(WithWarnings) — end-to-end through fixtures + predictions
// ---------------------------------------------------------------------------

describe('calculateGroupStandings', () => {
	it('computes a clean 4-team group with no warnings', () => {
		// France beats all, Germany beats Spain & Italy, Spain beats Italy.
		const fixtures: Fixture[] = [
			_fixture('1', 'France', 'Germany'),
			_fixture('2', 'France', 'Spain'),
			_fixture('3', 'France', 'Italy'),
			_fixture('4', 'Germany', 'Spain'),
			_fixture('5', 'Germany', 'Italy'),
			_fixture('6', 'Spain', 'Italy')
		];
		const predictions = new Map([
			_pred('1', 2, 1),
			_pred('2', 3, 0),
			_pred('3', 1, 0),
			_pred('4', 2, 1),
			_pred('5', 2, 1),
			_pred('6', 1, 0)
		]);
		const { standings, warnings } = calculateGroupStandingsWithWarnings(fixtures, predictions, 'A');
		expect(standings.map((t) => t.team)).toEqual(['France', 'Germany', 'Spain', 'Italy']);
		expect(standings.map((t) => t.points)).toEqual([9, 6, 3, 0]);
		expect(warnings).toEqual([]);
	});

	it('returns an empty list with no warnings when no predictions are set', () => {
		const fixtures: Fixture[] = [_fixture('1', 'France', 'Germany')];
		const { standings, warnings } = calculateGroupStandingsWithWarnings(
			fixtures,
			new Map(),
			'A'
		);
		// Both teams appear with 0 played; sort is overall-stats tied so alphabetical
		// kicks in, producing one warning.
		expect(standings.length).toBe(2);
		expect(warnings.length).toBe(1);
		expect(warnings[0].tiedTeams).toEqual(['France', 'Germany']);
	});

	it('emits a warning when all teams draw 0-0 (overall + H2H all equal)', () => {
		const fixtures: Fixture[] = [
			_fixture('1', 'Argentina', 'Belgium'),
			_fixture('2', 'Argentina', 'Croatia'),
			_fixture('3', 'Argentina', 'Denmark'),
			_fixture('4', 'Belgium', 'Croatia'),
			_fixture('5', 'Belgium', 'Denmark'),
			_fixture('6', 'Croatia', 'Denmark')
		];
		const predictions = new Map([
			_pred('1', 0, 0),
			_pred('2', 0, 0),
			_pred('3', 0, 0),
			_pred('4', 0, 0),
			_pred('5', 0, 0),
			_pred('6', 0, 0)
		]);
		const { standings, warnings } = calculateGroupStandingsWithWarnings(fixtures, predictions, 'A');
		expect(standings.map((t) => t.team)).toEqual([
			'Argentina',
			'Belgium',
			'Croatia',
			'Denmark'
		]);
		expect(warnings.length).toBe(1);
		expect(warnings[0].tiedTeams).toEqual(['Argentina', 'Belgium', 'Croatia', 'Denmark']);
		expect(warnings[0].context).toBe('group_standings');
		expect(warnings[0].group).toBe('A');
	});

	it('emits a warning when two teams tie on overall + H2H (drew their H2H)', () => {
		// France & Germany both 2-0 vs Spain and Italy; H2H 1-1.
		const fixtures: Fixture[] = [
			_fixture('1', 'France', 'Germany'),
			_fixture('2', 'France', 'Spain'),
			_fixture('3', 'France', 'Italy'),
			_fixture('4', 'Germany', 'Spain'),
			_fixture('5', 'Germany', 'Italy'),
			_fixture('6', 'Spain', 'Italy')
		];
		const predictions = new Map([
			_pred('1', 1, 1), // France-Germany draw
			_pred('2', 2, 0),
			_pred('3', 1, 0),
			_pred('4', 2, 0),
			_pred('5', 1, 0),
			_pred('6', 1, 0)
		]);
		const { standings, warnings } = calculateGroupStandingsWithWarnings(fixtures, predictions, 'A');
		// France and Germany should occupy positions 1 and 2 (both 7 pts, GD +3, GF 4)
		expect(standings.slice(0, 2).map((t) => t.team).sort()).toEqual(['France', 'Germany']);
		const tieWarning = warnings.find((w) =>
			w.tiedTeams.includes('France') && w.tiedTeams.includes('Germany')
		);
		expect(tieWarning).toBeDefined();
		expect(tieWarning!.context).toBe('group_standings');
	});

	it('backwards-compat: calculateGroupStandings returns only the sorted list', () => {
		const fixtures: Fixture[] = [_fixture('1', 'France', 'Germany')];
		const predictions = new Map([_pred('1', 2, 1)]);
		const result = calculateGroupStandings(fixtures, predictions, 'A');
		expect(Array.isArray(result)).toBe(true);
		expect(result[0].team).toBe('France');
	});
});

// ---------------------------------------------------------------------------
// computeGroupStandingsMapWithWarnings
// ---------------------------------------------------------------------------

describe('computeGroupStandingsMapWithWarnings', () => {
	it('aggregates warnings from multiple groups', () => {
		const groupAFixtures: Fixture[] = [
			_fixture('a1', 'X', 'Y', 'A'),
			_fixture('a2', 'X', 'Z', 'A'),
			_fixture('a3', 'Y', 'Z', 'A')
		];
		const groupBFixtures: Fixture[] = [
			_fixture('b1', 'P', 'Q', 'B'),
			_fixture('b2', 'P', 'R', 'B'),
			_fixture('b3', 'Q', 'R', 'B')
		];
		const predictions = new Map([
			// Group A all 0-0 → 3-way warning
			_pred('a1', 0, 0),
			_pred('a2', 0, 0),
			_pred('a3', 0, 0),
			// Group B all 0-0 → 3-way warning
			_pred('b1', 0, 0),
			_pred('b2', 0, 0),
			_pred('b3', 0, 0)
		]);

		const { standingsMap, warnings } = computeGroupStandingsMapWithWarnings(
			[
				{ group: 'A', fixtures: groupAFixtures },
				{ group: 'B', fixtures: groupBFixtures }
			],
			predictions
		);
		expect(Object.keys(standingsMap).sort()).toEqual(['A', 'B']);
		const groupAWarnings = warnings.filter((w) => w.group === 'A');
		const groupBWarnings = warnings.filter((w) => w.group === 'B');
		expect(groupAWarnings.length).toBe(1);
		expect(groupBWarnings.length).toBe(1);
	});
});
