import { describe, expect, it } from 'vitest';
import type { MatchMetaEntry, ScenarioOutcome } from '$lib/types/winProbability';
import { groupScenariosByChampion } from './pathToTrophy';

// Bracket: 101 = SF1 (France v Spain), 102 = SF2 (England v Argentina),
// 104 = Final.
const META: MatchMetaEntry[] = [
	{ match_number: 101, home_team: 'France', away_team: 'Spain', stage: 'semi_final' },
	{ match_number: 102, home_team: 'England', away_team: 'Argentina', stage: 'semi_final' },
	{ match_number: 104, home_team: 'TBD', away_team: 'TBD', stage: 'final' }
];

function scn(
	outcomes: Record<number, string>,
	weight: number,
	...champions: string[]
): ScenarioOutcome {
	return {
		outcomes: Object.fromEntries(Object.entries(outcomes)),
		weight,
		champion_entry_ids: champions,
		champion_points: 1000
	};
}

describe('groupScenariosByChampion', () => {
	it('reports only the match that is invariant across a champion group (the bug)', () => {
		// "hedge" wins in 3 scenarios that all share SF1 = France, but differ
		// on SF2 and on the final. The condition must be "France win SF1"
		// ALONE — never a clause about the final, which varies.
		const scenarios = [
			scn({ 101: 'France', 102: 'England', 104: 'France' }, 0.2, 'hedge'),
			scn({ 101: 'France', 102: 'Argentina', 104: 'France' }, 0.15, 'hedge'),
			scn({ 101: 'France', 102: 'Argentina', 104: 'Argentina' }, 0.1, 'hedge')
		];
		const [group] = groupScenariosByChampion(scenarios, META);

		expect(group.entryId).toBe('hedge');
		expect(group.scenarioCount).toBe(3);
		expect(group.fixedMatches).toHaveLength(1);
		expect(group.fixedMatches[0]).toMatchObject({
			matchNumber: 101,
			winningTeam: 'France',
			stage: 'semi_final'
		});
		expect(group.winsUnconditionally).toBe(false);
		expect(group.totalWeight).toBeCloseTo(0.45);
	});

	it('a single-scenario group fixes every match (nothing to filter)', () => {
		const scenarios = [scn({ 101: 'Spain', 102: 'England', 104: 'England' }, 0.1, 'solo')];
		const [group] = groupScenariosByChampion(scenarios, META);

		expect(group.fixedMatches.map((f) => f.matchNumber)).toEqual([101, 102, 104]);
		expect(group.winsUnconditionally).toBe(false);
	});

	it('counts a tied scenario toward every tied champion', () => {
		const scenarios = [scn({ 101: 'France', 102: 'England', 104: 'France' }, 0.3, 'a', 'b')];
		const groups = groupScenariosByChampion(scenarios, META);

		expect(groups.map((g) => g.entryId).sort()).toEqual(['a', 'b']);
		for (const g of groups) {
			expect(g.scenarioCount).toBe(1);
			expect(g.totalWeight).toBeCloseTo(0.3);
		}
	});

	it('flags an unconditional winner (>1 scenario, nothing fixed)', () => {
		// "always" tops the pool no matter who wins anything.
		const scenarios = [
			scn({ 101: 'France', 102: 'England', 104: 'France' }, 0.25, 'always'),
			scn({ 101: 'Spain', 102: 'Argentina', 104: 'Spain' }, 0.25, 'always')
		];
		const [group] = groupScenariosByChampion(scenarios, META);

		expect(group.fixedMatches).toHaveLength(0);
		expect(group.winsUnconditionally).toBe(true);
	});

	it('orders groups by total weight, most-likely first', () => {
		const scenarios = [
			scn({ 101: 'France', 102: 'England', 104: 'France' }, 0.5, 'big'),
			scn({ 101: 'Spain', 102: 'England', 104: 'Spain' }, 0.1, 'small')
		];
		const groups = groupScenariosByChampion(scenarios, META);
		expect(groups.map((g) => g.entryId)).toEqual(['big', 'small']);
	});
});
