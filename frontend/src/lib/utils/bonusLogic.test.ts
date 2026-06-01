import { describe, expect, it } from 'vitest';

import {
	bonusBorderClass,
	countAnsweredQuestions,
	filterTeamsInTopN,
	filterTeamsOutsideTopN,
	validateBonusAnswer
} from './bonusLogic';

describe('countAnsweredQuestions', () => {
	it('returns 0 for empty answers', () => {
		expect(countAnsweredQuestions(['a', 'b'], new Map())).toBe(0);
	});

	it('counts non-empty answers tied to live questions', () => {
		const answers = new Map([
			['a', 'France'],
			['b', 'Spain']
		]);
		expect(countAnsweredQuestions(['a', 'b'], answers)).toBe(2);
	});

	it('ignores answers whose question ID is not in the live list', () => {
		// This is the bug guard: stored answer for a removed question
		// ID must not inflate the counter past the denominator.
		const answers = new Map([
			['most_goals_scored_group', 'France'],
			['best_player', 'Mbappe'], // <-- removed question, still in draft
			['top_scorer', 'Haaland'] // <-- also removed
		]);
		const liveIds = ['most_goals_scored_group', 'most_goals_conceded_group', 'dark_horse', 'flop'];
		expect(countAnsweredQuestions(liveIds, answers)).toBe(1);
	});

	it('ignores whitespace-only answers', () => {
		const answers = new Map([
			['a', '   '],
			['b', 'France']
		]);
		expect(countAnsweredQuestions(['a', 'b'], answers)).toBe(1);
	});

	it('ignores empty-string answers', () => {
		const answers = new Map([
			['a', ''],
			['b', 'France']
		]);
		expect(countAnsweredQuestions(['a', 'b'], answers)).toBe(1);
	});

	it('handles all-orphan case — returns 0', () => {
		// User pasted an old draft into a fresh competition; every
		// answer is for a removed question.
		const answers = new Map([
			['best_player', 'Mbappe'],
			['golden_glove', 'Donnarumma']
		]);
		expect(countAnsweredQuestions(['most_goals_scored_group', 'dark_horse'], answers)).toBe(0);
	});
});

describe('bonusBorderClass', () => {
	it('returns thick green border when answered', () => {
		expect(bonusBorderClass(true)).toBe('border-success/60');
	});

	it('returns thick red border when not answered', () => {
		expect(bonusBorderClass(false)).toBe('border-error/60');
	});
});

describe('filterTeamsOutsideTopN', () => {
	const allTeams = ['France', 'Spain', 'Senegal', 'Norway', 'Mexico', 'Brazil'];
	const top10 = ['France', 'Spain', 'Brazil'];

	it('excludes all FIFA-top teams', () => {
		const result = filterTeamsOutsideTopN(allTeams, top10);
		expect(result).not.toContain('France');
		expect(result).not.toContain('Spain');
		expect(result).not.toContain('Brazil');
	});

	it('includes every non-top team', () => {
		const result = filterTeamsOutsideTopN(allTeams, top10);
		expect(result).toContain('Senegal');
		expect(result).toContain('Norway');
		expect(result).toContain('Mexico');
	});

	it('preserves order from allTeams', () => {
		const result = filterTeamsOutsideTopN(allTeams, top10);
		expect(result).toEqual(['Senegal', 'Norway', 'Mexico']);
	});

	it('handles empty top list (everyone qualifies as outside-top)', () => {
		expect(filterTeamsOutsideTopN(allTeams, [])).toEqual(allTeams);
	});

	it('handles empty allTeams (nothing to filter)', () => {
		expect(filterTeamsOutsideTopN([], top10)).toEqual([]);
	});
});

describe('filterTeamsInTopN', () => {
	const allTeams = ['France', 'Spain', 'Senegal', 'Norway'];
	const top10 = ['France', 'Spain', 'Argentina']; // Argentina hypothetically missing from tournament

	it('returns only top teams that ARE in the active competition', () => {
		const result = filterTeamsInTopN(allTeams, top10);
		expect(result).toContain('France');
		expect(result).toContain('Spain');
		expect(result).not.toContain('Argentina'); // top, but absent from allTeams
	});

	it('preserves order from topTeams (FIFA-rank order)', () => {
		const result = filterTeamsInTopN(allTeams, top10);
		expect(result).toEqual(['France', 'Spain']);
	});

	it('excludes non-top teams entirely', () => {
		const result = filterTeamsInTopN(allTeams, top10);
		expect(result).not.toContain('Senegal');
		expect(result).not.toContain('Norway');
	});

	it('returns empty when no top team is in the active competition', () => {
		expect(filterTeamsInTopN(['Mexico'], ['France', 'Spain'])).toEqual([]);
	});

	it('handles empty top list', () => {
		expect(filterTeamsInTopN(allTeams, [])).toEqual([]);
	});
});

describe('validateBonusAnswer', () => {
	const top10 = ['France', 'Spain', 'Brazil', 'Morocco'];
	const allTeams = ['France', 'Spain', 'Brazil', 'Morocco', 'Senegal', 'Mexico', 'Norway'];

	describe('team_outside_top_n (Dark Horse)', () => {
		const q = { input_type: 'team_outside_top_n' as const };

		it('accepts a non-top, in-tournament team', () => {
			expect(validateBonusAnswer(q, 'Senegal', top10, allTeams)).toBe(true);
		});

		it('rejects a stored top-N team (the headline bug)', () => {
			// User had 'Brazil' saved when input_type was just 'team'.
			// Now Brazil is excluded — counter should NOT count this as answered.
			expect(validateBonusAnswer(q, 'Brazil', top10, allTeams)).toBe(false);
		});

		it('rejects a team not in the active tournament when allTeams provided', () => {
			expect(validateBonusAnswer(q, 'Atlantis', top10, allTeams)).toBe(false);
		});

		it('accepts non-top team without allTeams pool (degraded mode)', () => {
			// Before groupFixtures resolves, allTeams is unknown. Falls
			// back to fifa-only check.
			expect(validateBonusAnswer(q, 'Senegal', top10)).toBe(true);
		});

		it('rejects empty string', () => {
			expect(validateBonusAnswer(q, '', top10, allTeams)).toBe(false);
		});

		it('rejects whitespace-only', () => {
			expect(validateBonusAnswer(q, '   ', top10, allTeams)).toBe(false);
		});
	});

	describe('team_in_top_n (Bottlers)', () => {
		const q = { input_type: 'team_in_top_n' as const };

		it('accepts a top-N, in-tournament team', () => {
			expect(validateBonusAnswer(q, 'France', top10, allTeams)).toBe(true);
		});

		it('rejects a stored non-top team (the symmetric bug)', () => {
			// User had 'Senegal' saved as flop when it was input_type: team.
			// Senegal isn't in top_n — must not count as answered now.
			expect(validateBonusAnswer(q, 'Senegal', top10, allTeams)).toBe(false);
		});

		it('rejects a top-N team that didn\'t qualify for the tournament', () => {
			// Hypothetical: Italy was in fifa_top_teams but absent from allTeams.
			const top10WithItaly = [...top10, 'Italy'];
			expect(validateBonusAnswer(q, 'Italy', top10WithItaly, allTeams)).toBe(false);
		});

		it('accepts top-N team without allTeams pool (degraded mode)', () => {
			expect(validateBonusAnswer(q, 'France', top10)).toBe(true);
		});
	});

	describe('team (legacy, any team)', () => {
		const q = { input_type: 'team' as const };

		it('accepts any team in the tournament', () => {
			expect(validateBonusAnswer(q, 'Senegal', top10, allTeams)).toBe(true);
			expect(validateBonusAnswer(q, 'France', top10, allTeams)).toBe(true);
		});

		it('rejects a team not in the tournament', () => {
			expect(validateBonusAnswer(q, 'Atlantis', top10, allTeams)).toBe(false);
		});

		it('accepts any non-empty value when allTeams unknown', () => {
			expect(validateBonusAnswer(q, 'Senegal', top10)).toBe(true);
		});
	});

	describe('player (legacy free-text)', () => {
		const q = { input_type: 'player' as const };

		it('accepts any non-empty string', () => {
			expect(validateBonusAnswer(q, 'Mbappe', top10, allTeams)).toBe(true);
		});

		it('rejects empty', () => {
			expect(validateBonusAnswer(q, '', top10, allTeams)).toBe(false);
		});
	});

	describe('unknown input_type', () => {
		it('conservatively rejects so the user re-picks', () => {
			const q = { input_type: 'team_in_bottom_half' as const };
			expect(validateBonusAnswer(q, 'France', top10, allTeams)).toBe(false);
		});
	});
});

// ---------------------------------------------------------------------
// TypeScript regression — pin the BonusInputType union shape so removing
// one of the filtered variants would surface as a compile error here.
// ---------------------------------------------------------------------
describe('BonusInputType union', () => {
	it('accepts all four current input_type literals', () => {
		// If any of these `satisfies` checks fail, the type union has
		// drifted out of sync with the YAML / backend.
		const a = 'team' satisfies import('$api/bonus').BonusInputType;
		const b = 'player' satisfies import('$api/bonus').BonusInputType;
		const c = 'team_outside_top_n' satisfies import('$api/bonus').BonusInputType;
		const d = 'team_in_top_n' satisfies import('$api/bonus').BonusInputType;
		expect([a, b, c, d]).toEqual(['team', 'player', 'team_outside_top_n', 'team_in_top_n']);
	});
});
