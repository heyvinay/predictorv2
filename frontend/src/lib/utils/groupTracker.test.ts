import { describe, it, expect } from 'vitest';
import type { Fixture, MatchPrediction, BracketPrediction } from '$types';
import type { BonusQuestion } from '$api/bonus';
import type { BonusPredictionRead } from '$lib/types/leaderboard';
import type { TeamStanding } from './standings';
import type { GroupStandingsMap } from './bracketResolver';
import {
	entryPickSlotState,
	qtrackFromEntry,
	groupStatusFromStandings,
	qualificationNeeds,
	groupVerdict,
	predictedBestThirdRankMap,
	bestThirdOverlayState,
	bestThirdDroppedPicks,
	bestThirdShiftSummary,
	projectedR32Pairings,
	r32DifferencesVsPrediction,
	groupPhaseBonusState,
	predictedStandingsMap
} from './groupTracker';

function standing(overrides: Partial<TeamStanding> & { team: string; group: string }): TeamStanding {
	return {
		played: 3,
		won: 0,
		drawn: 0,
		lost: 0,
		goalsFor: 0,
		goalsAgainst: 0,
		goalDifference: 0,
		points: 0,
		...overrides
	};
}

function fixture(overrides: Partial<Fixture> & { id: string }): Fixture {
	return {
		home_team: 'Home',
		away_team: 'Away',
		kickoff: '2026-06-12T00:00:00Z',
		stage: 'group',
		group: 'A',
		match_number: null,
		status: 'finished',
		minute: null,
		is_locked: true,
		time_until_lock: null,
		score: null,
		venue_city: null,
		venue_country: null,
		venue_country_code: null,
		...overrides
	};
}

describe('entryPickSlotState', () => {
	const picks: [string, string] = ['Brazil', 'Argentina'];

	it('hit — pick in its predicted slot', () => {
		expect(entryPickSlotState('Brazil', 1, picks)).toBe('hit');
		expect(entryPickSlotState('Argentina', 2, picks)).toBe('hit');
	});

	it('swap — pick in the other top-2 slot', () => {
		expect(entryPickSlotState('Brazil', 2, picks)).toBe('swap');
		expect(entryPickSlotState('Argentina', 1, picks)).toBe('swap');
	});

	it('warn — pick slipped to 3rd (best-3rd bubble)', () => {
		expect(entryPickSlotState('Brazil', 3, picks)).toBe('warn');
	});

	it('miss — pick eliminated at 4th', () => {
		expect(entryPickSlotState('Brazil', 4, picks)).toBe('miss');
	});

	it('up — surprise qualifier not picked', () => {
		expect(entryPickSlotState('Uruguay', 1, picks)).toBe('up');
		expect(entryPickSlotState('Uruguay', 2, picks)).toBe('up');
	});

	it('null — neither picked nor qualifying', () => {
		expect(entryPickSlotState('Uruguay', 3, picks)).toBe(null);
		expect(entryPickSlotState('Uruguay', 4, picks)).toBe(null);
	});
});

describe('qtrackFromEntry', () => {
	const picks: [string, string] = ['Brazil', 'Argentina'];

	it('both hit → [hit, hit]', () => {
		const standings = [
			standing({ team: 'Brazil', group: 'A' }),
			standing({ team: 'Argentina', group: 'A' }),
			standing({ team: 'Chile', group: 'A' }),
			standing({ team: 'Peru', group: 'A' })
		];
		expect(qtrackFromEntry(picks, standings)).toEqual(['hit', 'hit']);
	});

	it('both swapped → [swap, swap]', () => {
		const standings = [
			standing({ team: 'Argentina', group: 'A' }),
			standing({ team: 'Brazil', group: 'A' }),
			standing({ team: 'Chile', group: 'A' }),
			standing({ team: 'Peru', group: 'A' })
		];
		expect(qtrackFromEntry(picks, standings)).toEqual(['swap', 'swap']);
	});

	it('one hit, one dropped out → [hit, miss]', () => {
		const standings = [
			standing({ team: 'Brazil', group: 'A' }),
			standing({ team: 'Chile', group: 'A' }),
			standing({ team: 'Peru', group: 'A' }),
			standing({ team: 'Argentina', group: 'A' })
		];
		expect(qtrackFromEntry(picks, standings)).toEqual(['hit', 'miss']);
	});

	it('one hit, one on best-3rd bubble → dot still reads miss (only 3 dot colours)', () => {
		const standings = [
			standing({ team: 'Brazil', group: 'A' }),
			standing({ team: 'Chile', group: 'A' }),
			standing({ team: 'Argentina', group: 'A' }),
			standing({ team: 'Peru', group: 'A' })
		];
		expect(qtrackFromEntry(picks, standings)).toEqual(['hit', 'miss']);
	});
});

describe('groupStatusFromStandings', () => {
	it('final when every team has played 3', () => {
		const s = ['A', 'B', 'C', 'D'].map((t) => standing({ team: t, group: 'A', played: 3 }));
		expect(groupStatusFromStandings(s)).toBe('final');
	});

	it('oneToPlay when every team has played 2', () => {
		const s = ['A', 'B', 'C', 'D'].map((t) => standing({ team: t, group: 'A', played: 2 }));
		expect(groupStatusFromStandings(s)).toBe('oneToPlay');
	});

	it('twoToPlay when every team has played 1', () => {
		const s = ['A', 'B', 'C', 'D'].map((t) => standing({ team: t, group: 'A', played: 1 }));
		expect(groupStatusFromStandings(s)).toBe('twoToPlay');
	});

	it('upcoming when no team has played', () => {
		const s = ['A', 'B', 'C', 'D'].map((t) => standing({ team: t, group: 'A', played: 0 }));
		expect(groupStatusFromStandings(s)).toBe('upcoming');
	});

	it('uses the MINIMUM played across teams for mixed matchday state', () => {
		const s = [
			standing({ team: 'A', group: 'A', played: 2 }),
			standing({ team: 'B', group: 'A', played: 2 }),
			standing({ team: 'C', group: 'A', played: 1 }),
			standing({ team: 'D', group: 'A', played: 2 })
		];
		expect(groupStatusFromStandings(s)).toBe('twoToPlay');
	});
});

describe('qualificationNeeds', () => {
	it('names the single remaining opponent when only one fixture is left', () => {
		const fixtures = [
			fixture({ id: 'f1', group: 'A', home_team: 'Chile', away_team: 'Peru', status: 'finished' }),
			fixture({ id: 'f2', group: 'A', home_team: 'Chile', away_team: 'Bolivia', status: 'scheduled' })
		];
		const result = qualificationNeeds('Chile', 'A', fixtures, null);
		expect(result).toContain('Chile');
		expect(result).toContain('Bolivia');
	});

	it('names the rival AND their opponent when a rival is still in flight too', () => {
		const fixtures = [
			fixture({ id: 'f1', group: 'A', home_team: 'Chile', away_team: 'Bolivia', status: 'scheduled' }),
			fixture({ id: 'f2', group: 'A', home_team: 'Uruguay', away_team: 'Peru', status: 'scheduled' })
		];
		const result = qualificationNeeds('Chile', 'A', fixtures, 'Uruguay');
		expect(result).toContain('Chile');
		expect(result).toContain('Bolivia');
		expect(result).toContain('Uruguay');
		expect(result).toContain('Peru');
	});

	it('returns null when the team has no remaining group fixtures', () => {
		const fixtures = [
			fixture({ id: 'f1', group: 'A', home_team: 'Chile', away_team: 'Peru', status: 'finished' })
		];
		expect(qualificationNeeds('Chile', 'A', fixtures, null)).toBe(null);
	});

	it('gives a generic message when 2+ fixtures remain', () => {
		const fixtures = [
			fixture({ id: 'f1', group: 'A', home_team: 'Chile', away_team: 'Peru', status: 'scheduled' }),
			fixture({ id: 'f2', group: 'A', home_team: 'Chile', away_team: 'Bolivia', status: 'scheduled' })
		];
		const result = qualificationNeeds('Chile', 'A', fixtures, null);
		expect(result).toContain('Chile');
		expect(result).toContain('2');
	});
});

describe('groupVerdict', () => {
	const picks: [string, string] = ['Brazil', 'Argentina'];

	it('good tone when both picks locked in the correct order, final', () => {
		const standings = [
			standing({ team: 'Brazil', group: 'A', played: 3 }),
			standing({ team: 'Argentina', group: 'A', played: 3 }),
			standing({ team: 'Chile', group: 'A', played: 3 }),
			standing({ team: 'Peru', group: 'A', played: 3 })
		];
		const v = groupVerdict(picks, standings, 'A', []);
		expect(v.tone).toBe('good');
		expect(v.detail).toBe('R32 seed as predicted');
		expect(v.needs).toBe(null);
	});

	it('warn tone (order swap) when both correct teams but wrong slots', () => {
		const standings = [
			standing({ team: 'Argentina', group: 'A', played: 3 }),
			standing({ team: 'Brazil', group: 'A', played: 3 }),
			standing({ team: 'Chile', group: 'A', played: 3 }),
			standing({ team: 'Peru', group: 'A', played: 3 })
		];
		const v = groupVerdict(picks, standings, 'A', []);
		expect(v.tone).toBe('warn');
		expect(v.label).toContain('wrong order');
	});

	it('miss tone names the team that dropped out AND its replacement, final', () => {
		const standings = [
			standing({ team: 'Brazil', group: 'A', played: 3 }),
			standing({ team: 'Chile', group: 'A', played: 3 }),
			standing({ team: 'Peru', group: 'A', played: 3 }),
			standing({ team: 'Argentina', group: 'A', played: 3 })
		];
		const v = groupVerdict(picks, standings, 'A', []);
		expect(v.tone).toBe('miss');
		expect(v.label).toContain('Argentina');
		expect(v.label).toContain('Chile');
		expect(v.needs).toBe(null); // final — nothing left to influence
	});

	it('warn tone (best-3rd bubble) with a needs line when the group is still open', () => {
		const standings = [
			standing({ team: 'Brazil', group: 'A', played: 2 }),
			standing({ team: 'Chile', group: 'A', played: 2 }),
			standing({ team: 'Argentina', group: 'A', played: 2 }),
			standing({ team: 'Peru', group: 'A', played: 2 })
		];
		const fixtures = [
			fixture({ id: 'f1', group: 'A', home_team: 'Argentina', away_team: 'Peru', status: 'scheduled' })
		];
		const v = groupVerdict(picks, standings, 'A', fixtures);
		expect(v.tone).toBe('warn');
		expect(v.label).toContain('Argentina');
		expect(v.needs).not.toBe(null);
	});

	it('pend tone when the group has not kicked off', () => {
		const standings = ['Brazil', 'Argentina', 'Chile', 'Peru'].map((t) =>
			standing({ team: t, group: 'A', played: 0 })
		);
		const v = groupVerdict(picks, standings, 'A', []);
		expect(v.tone).toBe('pend');
		expect(v.label).toBe('Group not yet underway');
	});
});

describe('predictedBestThirdRankMap + bestThirdOverlayState', () => {
	function map3rd(teams: [string, number, number, number][]): GroupStandingsMap {
		// teams: [name, pts, gd, gf] — used as the group's 3rd-placed entry.
		const out: GroupStandingsMap = {};
		teams.forEach(([team, points, goalDifference, goalsFor], i) => {
			const group = String.fromCharCode(65 + i); // A, B, C...
			out[group] = [
				standing({ team: `${group}-1st`, group, points: 9 }),
				standing({ team: `${group}-2nd`, group, points: 6 }),
				standing({ team, group, points, goalDifference, goalsFor }),
				standing({ team: `${group}-4th`, group, points: 0 })
			];
		});
		return out;
	}

	it('ranks third-placed teams by points → GD → GF, assigns 1..N', () => {
		const standings = map3rd([
			['Peru', 4, 2, 5],
			['Ecuador', 4, 1, 4],
			['Bolivia', 3, 0, 2]
		]);
		const rankMap = predictedBestThirdRankMap(standings);
		expect(rankMap.get('Peru')?.rank).toBe(1);
		expect(rankMap.get('Ecuador')?.rank).toBe(2);
		expect(rankMap.get('Bolivia')?.rank).toBe(3);
	});

	it('bestThirdOverlayState: hit when same team same rank', () => {
		const rankMap = new Map([['Peru', { rank: 1, group: 'A' }]]);
		const state = bestThirdOverlayState('Peru', 1, rankMap);
		expect(state.marker).toBe('hit');
	});

	it('bestThirdOverlayState: swap when same team different rank', () => {
		const rankMap = new Map([['Peru', { rank: 3, group: 'A' }]]);
		const state = bestThirdOverlayState('Peru', 1, rankMap);
		expect(state.marker).toBe('swap');
		expect(state.userRank).toBe(3);
	});

	it('bestThirdOverlayState: up when team not in the predicted cohort but qualifies', () => {
		const rankMap = new Map<string, { rank: number; group: string }>();
		const state = bestThirdOverlayState('Peru', 4, rankMap);
		expect(state.marker).toBe('up');
	});

	it('bestThirdOverlayState: miss when predicted team falls outside top-8', () => {
		const rankMap = new Map([['Peru', { rank: 4, group: 'A' }]]);
		const state = bestThirdOverlayState('Peru', 9, rankMap);
		expect(state.marker).toBe('miss');
		expect(state.userRank).toBe(4);
	});

	it('bestThirdOverlayState: null when neither picked nor qualifying', () => {
		const rankMap = new Map<string, { rank: number; group: string }>();
		const state = bestThirdOverlayState('Peru', 9, rankMap);
		expect(state.marker).toBe(null);
	});

	it('bestThirdDroppedPicks: flags a predicted best-3rd team now 4th in its own group', () => {
		const rankMap = new Map([['Turkey', { rank: 1, group: 'D' }]]);
		const actualThirdPlaceTable: TeamStanding[] = [
			standing({ team: 'Paraguay', group: 'D', points: 4 })
		];
		const actualStandingsMap: GroupStandingsMap = {
			D: [
				standing({ team: 'Netherlands', group: 'D', points: 9 }),
				standing({ team: 'Senegal', group: 'D', points: 6 }),
				standing({ team: 'Paraguay', group: 'D', points: 4 }),
				standing({ team: 'Turkey', group: 'D', points: 3 })
			]
		};
		const dropped = bestThirdDroppedPicks(rankMap, actualThirdPlaceTable, actualStandingsMap);
		expect(dropped).toHaveLength(1);
		expect(dropped[0].team).toBe('Turkey');
		expect(dropped[0].currentGroupPosition).toBe(4);
	});

	it('bestThirdShiftSummary tallies each state and surfaces the biggest shifts first', () => {
		const rankMap = new Map([
			['Denmark', { rank: 3, group: 'G' }], // perfect (actual rank 3 too)
			['SouthKorea', { rank: 7, group: 'A' }], // swap (actual rank 5)
			['Turkey', { rank: 1, group: 'D' }] // dropped entirely
		]);
		const actualThirdPlaceTable: TeamStanding[] = [
			standing({ team: 'Bosnia', group: 'B' }),
			standing({ team: 'Paraguay', group: 'D' }),
			standing({ team: 'Denmark', group: 'G' }),
			standing({ team: 'Vietnam', group: 'F' }),
			standing({ team: 'SouthKorea', group: 'A' })
		];
		const actualStandingsMap: GroupStandingsMap = {
			D: [
				standing({ team: 'X', group: 'D', points: 9 }),
				standing({ team: 'Y', group: 'D', points: 6 }),
				standing({ team: 'Paraguay', group: 'D', points: 4 }),
				standing({ team: 'Turkey', group: 'D', points: 3 })
			]
		};
		const summary = bestThirdShiftSummary(rankMap, actualThirdPlaceTable, actualStandingsMap, 2);
		expect(summary.perfect).toBe(1); // Denmark
		expect(summary.rankSwap).toBe(1); // SouthKorea
		expect(summary.droppedEntirely).toBe(1); // Turkey
		expect(summary.surpriseIn).toBe(3); // Bosnia, Paraguay, Vietnam
		// Turkey's magnitude is Infinity (dropped) so it sorts first.
		expect(summary.biggestShifts[0].team).toBe('Turkey');
	});
});

describe('projectedR32Pairings + r32DifferencesVsPrediction', () => {
	const GROUPS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'];

	function fullStandingsMap(swapGroupAOrder = false): GroupStandingsMap {
		const map: GroupStandingsMap = {};
		for (const g of GROUPS) {
			const first = swapGroupAOrder && g === 'A' ? `${g}-2` : `${g}-1`;
			const second = swapGroupAOrder && g === 'A' ? `${g}-1` : `${g}-2`;
			map[g] = [
				standing({ team: first, group: g, points: 9 }),
				standing({ team: second, group: g, points: 6 }),
				standing({ team: `${g}-3`, group: g, points: 3 }),
				standing({ team: `${g}-4`, group: g, points: 0 })
			];
		}
		return map;
	}

	it('produces 16 R32 pairings with resolved home/away teams', () => {
		const pairings = projectedR32Pairings(fullStandingsMap());
		expect(pairings).toHaveLength(16);
		for (const p of pairings) {
			expect(p.home).not.toBe(null);
			expect(p.away).not.toBe(null);
		}
	});

	it('flags a difference when a group order swap changes an R32 slot', () => {
		const baseline = projectedR32Pairings(fullStandingsMap(false));
		const swapped = projectedR32Pairings(fullStandingsMap(true));

		// Build a synthetic entry bracket prediction matching the baseline lineup.
		const entryBracket: BracketPrediction = {
			group_winners: {},
			round_of_32: baseline.flatMap((p) => [p.home ?? '', p.away ?? '']),
			round_of_16: [],
			quarter_finals: [],
			semi_finals: [],
			final: [],
			winner: ''
		};

		const diffs = r32DifferencesVsPrediction(swapped, entryBracket);
		expect(diffs.length).toBeGreaterThan(0);
	});

	it('reports no differences when predicted and projected lineups match', () => {
		const pairings = projectedR32Pairings(fullStandingsMap());
		const entryBracket: BracketPrediction = {
			group_winners: {},
			round_of_32: pairings.flatMap((p) => [p.home ?? '', p.away ?? '']),
			round_of_16: [],
			quarter_finals: [],
			semi_finals: [],
			final: [],
			winner: ''
		};
		const diffs = r32DifferencesVsPrediction(pairings, entryBracket);
		expect(diffs).toHaveLength(0);
	});
});

describe('groupPhaseBonusState', () => {
	const questions: BonusQuestion[] = [
		{
			id: 'q1',
			category: 'group_stage',
			label: 'Which team scores the most goals in the group stage?',
			input_type: 'team',
			points: 10
		},
		{
			id: 'q2',
			category: 'group_stage',
			label: 'Which team concedes the most goals in the group stage?',
			input_type: 'team',
			points: 10
		}
	];

	const fixtures: Fixture[] = [
		fixture({
			id: 'f1',
			home_team: 'Germany',
			away_team: 'Ivory Coast',
			status: 'finished',
			score: {
				home_score: 10,
				away_score: 4,
				home_score_et: null,
				away_score_et: null,
				home_penalties: null,
				away_penalties: null,
				outcome: '1'
			}
		}),
		fixture({
			id: 'f2',
			home_team: 'Brazil',
			away_team: 'Morocco',
			status: 'finished',
			score: {
				home_score: 7,
				away_score: 1,
				home_score_et: null,
				away_score_et: null,
				home_penalties: null,
				away_penalties: null,
				outcome: '1'
			}
		})
	];

	it('marks the user as leading when their pick matches the current leader', () => {
		const answers: BonusPredictionRead[] = [
			{ question_id: 'q1', answer: 'Germany', category: 'group_stage', points: null, hit: null }
		];
		const result = groupPhaseBonusState(fixtures, questions, answers);
		expect(result.mostScored?.status).toBe('leading');
		expect(result.mostScored?.leaders).toContain('Germany');
	});

	it('marks the user as fading/missed when far behind the leader', () => {
		const answers: BonusPredictionRead[] = [
			{ question_id: 'q1', answer: 'Morocco', category: 'group_stage', points: null, hit: null }
		];
		const result = groupPhaseBonusState(fixtures, questions, answers);
		// Morocco scored 1, Germany leads with 10 — delta of 9 → missed.
		expect(result.mostScored?.status).toBe('missed');
	});

	it('returns null for a question the entry never answered', () => {
		const result = groupPhaseBonusState(fixtures, questions, []);
		expect(result.mostScored).toBe(null);
		expect(result.mostConceded).toBe(null);
	});
});

describe('predictedStandingsMap', () => {
	it('builds a per-group standings map from the entry\'s own score predictions', () => {
		const fixtures: Fixture[] = [
			fixture({ id: 'f1', group: 'A', home_team: 'Brazil', away_team: 'Chile' }),
			fixture({ id: 'f2', group: 'B', home_team: 'France', away_team: 'Poland' })
		];
		const predictions = new Map<string, MatchPrediction>([
			[
				'f1',
				{
					id: 'p1',
					entry_id: 'e1',
					fixture_id: 'f1',
					home_score: 2,
					away_score: 0,
					phase: 'phase_1',
					locked_at: null,
					created_at: '',
					updated_at: '',
					is_locked: false
				}
			],
			[
				'f2',
				{
					id: 'p2',
					entry_id: 'e1',
					fixture_id: 'f2',
					home_score: 1,
					away_score: 1,
					phase: 'phase_1',
					locked_at: null,
					created_at: '',
					updated_at: '',
					is_locked: false
				}
			]
		]);
		const map = predictedStandingsMap(fixtures, predictions);
		expect(Object.keys(map).sort()).toEqual(['A', 'B']);
		expect(map['A'][0].team).toBe('Brazil');
		expect(map['B'].find((s) => s.team === 'France')?.points).toBe(1);
	});
});
