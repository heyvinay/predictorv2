/**
 * Cross-language parity for match-points scoring.
 *
 * Frontend half of a two-language guarantee: the SAME golden cases in
 * `shared/scoring-parity-cases.json` are also run by the backend pytest suite
 * (`backend/tests/test_scoring_parity.py`). Both `computeMatchPoints` (here) and
 * `compute_match_points` (Python) must return identical points/correctOutcome/
 * exactScore for every case, so the Results-card projection can never drift from
 * the points the backend actually awards.
 *
 * The fixture lives at the repo root (outside the SvelteKit project), so we
 * locate it with a Node parent-walk.
 */

import { describe, it, expect } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { computeMatchPoints } from './matchBreakdown';

interface ScoringCase {
	name: string;
	mode: string;
	predicted_home: number;
	predicted_away: number;
	actual_home: number;
	actual_away: number;
	total_predictors: number;
	correct_predictors: number;
	outcome_points: number;
	exact_points: number;
	cap: number;
	expected_points: number;
	expected_correct_outcome: boolean;
	expected_exact_score: boolean;
}

function findCasesFile(): string | null {
	let dir = dirname(fileURLToPath(import.meta.url));
	for (let i = 0; i < 12; i++) {
		const candidate = resolve(dir, 'shared/scoring-parity-cases.json');
		if (existsSync(candidate)) return candidate;
		const parent = dirname(dir);
		if (parent === dir) break;
		dir = parent;
	}
	return null;
}

const casesFile = findCasesFile();
const cases: ScoringCase[] = casesFile
	? (JSON.parse(readFileSync(casesFile, 'utf-8')) as { cases: ScoringCase[] }).cases
	: [];

describe('scoring parity (frontend ↔ backend golden cases)', () => {
	it('found the shared fixture file (else parity is untested)', () => {
		expect(casesFile, 'shared/scoring-parity-cases.json not found via parent-walk').not.toBeNull();
		expect(cases.length).toBeGreaterThan(0);
	});

	for (const c of cases) {
		it(`${c.name}`, () => {
			const { points, correctOutcome, exactScore } = computeMatchPoints({
				mode: c.mode,
				predictedHome: c.predicted_home,
				predictedAway: c.predicted_away,
				actualHome: c.actual_home,
				actualAway: c.actual_away,
				totalPredictors: c.total_predictors,
				correctPredictors: c.correct_predictors,
				outcomePoints: c.outcome_points,
				exactPoints: c.exact_points,
				cap: c.cap
			});
			expect(points, `points for ${c.name}`).toBe(c.expected_points);
			expect(correctOutcome, `correctOutcome for ${c.name}`).toBe(c.expected_correct_outcome);
			expect(exactScore, `exactScore for ${c.name}`).toBe(c.expected_exact_score);
		});
	}
});
