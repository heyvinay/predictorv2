/**
 * Client-side derivation of per-group point totals for an entry.
 *
 * The backend's LeaderboardEntry.breakdown exposes per-phase aggregates
 * (match_outcome_points, exact_score_points, hybrid_bonus_points) but
 * NOT a per-letter (A-L) breakdown. Rather than ship a new endpoint
 * today, we derive letter totals locally from predictions + fixtures.
 *
 * This is a comparative view for the dashboard strip — for authoritative
 * point totals hit `/leaderboard/breakdown/{entry_id}`. The 5/10 base
 * (outcome / exact) is exact; the rarity bonus is NOT included here
 * because per-fixture predictor counts aren't available in this scope.
 * Small magnitude difference vs the authoritative total is acceptable
 * for visualisation.
 */

import type { Fixture, MatchPrediction } from '$types';

const ALL_GROUPS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'] as const;
export type GroupKey = (typeof ALL_GROUPS)[number];

export function computeGroupTotals(
	fixtures: Fixture[],
	predictions: MatchPrediction[]
): Record<GroupKey, number> {
	const totals = Object.fromEntries(ALL_GROUPS.map((g) => [g, 0])) as Record<GroupKey, number>;
	const predByFixture = new Map(predictions.map((p) => [p.fixture_id, p]));
	for (const f of fixtures) {
		if (!f.group || !(ALL_GROUPS as readonly string[]).includes(f.group)) continue;
		if (f.status !== 'finished' || !f.score) continue;
		const pred = predByFixture.get(f.id);
		if (!pred) continue;
		const actualOutcome =
			f.score.home_score > f.score.away_score
				? 'home'
				: f.score.home_score === f.score.away_score
				? 'draw'
				: 'away';
		const predOutcome =
			pred.home_score > pred.away_score
				? 'home'
				: pred.home_score === pred.away_score
				? 'draw'
				: 'away';
		const exact =
			pred.home_score === f.score.home_score && pred.away_score === f.score.away_score;
		if (exact) totals[f.group as GroupKey] += 10;
		else if (actualOutcome === predOutcome) totals[f.group as GroupKey] += 5;
	}
	return totals;
}
