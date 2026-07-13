import { describe, expect, it } from 'vitest';
import type { MatchMetaEntry, ScenarioOutcome } from '$lib/types/winProbability';
import { buildOutcomeGrid } from './outcomeGrid';

// Real bracket shape verified against production on 2026-07-13: 101/102 are
// the semis (known participants), 104 is the final (home_team/away_team ""
// since the semis haven't been played — the whole reason the old
// stageLabel('') bug existed).
const META: MatchMetaEntry[] = [
	{ match_number: 101, home_team: 'France', away_team: 'Spain', stage: 'semi_final' },
	{ match_number: 102, home_team: 'England', away_team: 'Argentina', stage: 'semi_final' },
	{ match_number: 104, home_team: '', away_team: '', stage: 'final' }
];

function scn(outcomes: Record<number, string>, weight: number, ...champions: string[]): ScenarioOutcome {
	return {
		outcomes: Object.fromEntries(Object.entries(outcomes)),
		weight,
		champion_entry_ids: champions,
		champion_points: 1000
	};
}

// The exact 8-scenario production dataset pulled from /leaderboard/trophy-scenarios.
const REAL_SCENARIOS: ScenarioOutcome[] = [
	scn({ 101: 'France', 102: 'England', 104: 'France' }, 0.16270697441043652, 'ian'),
	scn({ 101: 'France', 102: 'England', 104: 'England' }, 0.16270697441043652, 'mark'),
	scn({ 101: 'France', 102: 'Argentina', 104: 'France' }, 0.13479302558956346, 'ian'),
	scn({ 101: 'France', 102: 'Argentina', 104: 'Argentina' }, 0.13479302558956346, 'ian'),
	scn({ 101: 'Spain', 102: 'England', 104: 'Spain' }, 0.11075012543903663, 'james'),
	scn({ 101: 'Spain', 102: 'England', 104: 'England' }, 0.11075012543903663, 'glenn'),
	scn({ 101: 'Spain', 102: 'Argentina', 104: 'Spain' }, 0.09174987456096338, 'matthew'),
	scn({ 101: 'Spain', 102: 'Argentina', 104: 'Argentina' }, 0.09174987456096338, 'chris')
];

describe('buildOutcomeGrid', () => {
	it('empty scenario list produces an empty grid', () => {
		expect(buildOutcomeGrid([], META)).toEqual({ columns: [], rows: [], totalWeight: 0 });
	});

	it('a single scenario is one fully-owned row with nothing varying', () => {
		const grid = buildOutcomeGrid([scn({ 101: 'Spain', 102: 'England', 104: 'England' }, 0.4, 'solo')], META);
		expect(grid.rows).toHaveLength(1);
		expect(grid.rows[0].cells.map((c) => c.rowSpan)).toEqual([1, 1, 1]);
		expect(grid.rows[0].champion).toMatchObject({
			entryIds: ['solo'],
			weight: 0.4,
			rowSpan: 1,
			varyingStages: []
		});
	});

	it('orders rows so shared prefixes stay adjacent, ranking the final by which semi fed it', () => {
		const grid = buildOutcomeGrid(REAL_SCENARIOS, META);
		// Row order must reproduce the natural bracket order: France-side
		// rows first (home team of SF1), Spain-side second; within each,
		// England-side (home of SF2) before Argentina-side.
		const order = grid.rows.map((r) => r.cells.map((c) => c.team).join('/'));
		expect(order).toEqual([
			'France/England/France',
			'France/England/England',
			'France/Argentina/France',
			'France/Argentina/Argentina',
			'Spain/England/Spain',
			'Spain/England/England',
			'Spain/Argentina/Spain',
			'Spain/Argentina/Argentina'
		]);
	});

	it('merges the champion cell across rows where the outcome does not change who wins (the bug this replaces)', () => {
		const grid = buildOutcomeGrid(REAL_SCENARIOS, META);
		// Row 0 (France/England/France) = ian, alone.
		expect(grid.rows[0].champion).toMatchObject({ entryIds: ['ian'], rowSpan: 1, varyingStages: [] });
		// Row 1 (France/England/England) = mark, alone — proves ian's row 0
		// condition is NOT "whenever France win their semi": this adjacent
		// row shares that fact and belongs to someone else.
		expect(grid.rows[1].champion).toMatchObject({ entryIds: ['mark'], rowSpan: 1 });
		// Rows 2-3 (France/Argentina/{France,Argentina}) both belong to ian
		// — merged into one 2-row cell, with the final flagged as the only
		// varying column: the result of the final doesn't matter here.
		expect(grid.rows[2].champion).toMatchObject({
			entryIds: ['ian'],
			rowSpan: 2,
			varyingStages: ['final']
		});
		expect(grid.rows[2].champion.weight).toBeCloseTo(0.13479302558956346 * 2);
		// Row 3 is subsumed by row 2's span — it must not own its own cell.
		expect(grid.rows[3].champion).toMatchObject({ rowSpan: 0 });
	});

	it('merges outcome-column cells hierarchically (prefix-based rowspans)', () => {
		const grid = buildOutcomeGrid(REAL_SCENARIOS, META);
		// SF1 column: France spans all 4 France-side rows, Spain spans the
		// other 4 — top-level grouping.
		expect(grid.rows[0].cells[0]).toMatchObject({ team: 'France', rowSpan: 4 });
		expect(grid.rows[1].cells[0].rowSpan).toBe(0); // subsumed by row 0
		expect(grid.rows[4].cells[0]).toMatchObject({ team: 'Spain', rowSpan: 4 });
		// SF2 column: within the France block, England spans 2, Argentina spans 2.
		expect(grid.rows[0].cells[1]).toMatchObject({ team: 'England', rowSpan: 2 });
		expect(grid.rows[2].cells[1]).toMatchObject({ team: 'Argentina', rowSpan: 2 });
		// Final column never merges — every row's final result is its own,
		// distinct fact even when the champion cell spans across them.
		expect(grid.rows.every((r) => r.cells[2].rowSpan === 1)).toBe(true);
	});

	it('a tied scenario keeps both entries in one champion cell, isolated from neighbors', () => {
		const scenarios = [
			scn({ 101: 'France', 102: 'England', 104: 'France' }, 0.3, 'a', 'b'),
			scn({ 101: 'France', 102: 'England', 104: 'England' }, 0.2, 'a')
		];
		const grid = buildOutcomeGrid(scenarios, META);
		expect(grid.rows[0].champion).toMatchObject({ entryIds: ['a', 'b'], rowSpan: 1, weight: 0.3 });
		expect(grid.rows[1].champion).toMatchObject({ entryIds: ['a'], rowSpan: 1, weight: 0.2 });
	});

	it('totalWeight sums every scenario', () => {
		const grid = buildOutcomeGrid(REAL_SCENARIOS, META);
		expect(grid.totalWeight).toBeCloseTo(1.0);
	});
});
