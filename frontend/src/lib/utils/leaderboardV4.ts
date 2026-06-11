/**
 * V4 Leaderboard pure derivations (v2.164.0).
 *
 * Everything here is a pure function over server data — unit-tested in
 * leaderboardV4.test.ts. No stores, no fetches, no DOM.
 */

import type { Fixture, PointBreakdown } from '$types';
import type { ScoringRules } from '$lib/types/results';
import type {
	BonusFold,
	BonusPredictionRead,
	DnaSplit,
	LbEntryV4,
	LbPool,
	LbStage
} from '$lib/types/leaderboard';

// ── Pools ────────────────────────────────────────────────────────────────

/** Map a User.employer value onto a pool pill. Unknown/missing → Guests. */
export function poolOf(employer: string | null | undefined): Exclude<LbPool, 'All'> {
	if (employer === 'atlas') return 'Atlas';
	if (employer === 'jmfa') return 'JMFA';
	return 'Guests';
}

/** Filter rows to a pool. Server `position` values are NOT recomputed —
 *  the spec requires global ranks to survive filtering. */
export function filterByPool(rows: LbEntryV4[], pool: LbPool): LbEntryV4[] {
	if (pool === 'All') return rows;
	return rows.filter((r) => poolOf(r.employer) === pool);
}

/** Pill badge counts, computed once per leaderboard load. */
export function poolCounts(rows: LbEntryV4[]): Record<LbPool, number> {
	const counts: Record<LbPool, number> = { All: rows.length, Atlas: 0, JMFA: 0, Guests: 0 };
	for (const r of rows) counts[poolOf(r.employer)] += 1;
	return counts;
}

// ── Stage ────────────────────────────────────────────────────────────────

/** Knockout stage begins when any non-group fixture has a real team seeded
 *  (lineup-based, consistent with the scoring engine's advancement timing).
 *  Placeholder names like "Winner of Match 12" don't count. */
export function deriveStage(fixtures: Fixture[]): LbStage {
	const placeholder = /^(winner|loser|runner|1[a-l]|2[a-l]|3[a-l])\b/i;
	for (const f of fixtures) {
		if (f.stage === 'group') continue;
		for (const team of [f.home_team, f.away_team]) {
			if (team && team.trim() !== '' && !placeholder.test(team.trim())) {
				return 'knockout';
			}
		}
	}
	return 'group';
}

// ── Points DNA ───────────────────────────────────────────────────────────

/** Where an entry's points come from. exact + result + rarity + bracket +
 *  bonus === breakdown.total (server-computed fields). */
export function dnaOf(breakdown: PointBreakdown): DnaSplit {
	return {
		exact: breakdown.exact_score_points,
		result: breakdown.match_outcome_points,
		rarity: breakdown.hybrid_bonus_points,
		bracket: breakdown.bracket_total,
		bonus: breakdown.bonus_question_points
	};
}

// ── Bonus folding ────────────────────────────────────────────────────────

/** Fold per-question bonus reads into Group / Knockout column extras.
 *  category group_stage → Group; top_flop (and any future awards) → KO. */
export function foldBonus(reads: BonusPredictionRead[]): BonusFold {
	const fold: BonusFold = {
		group: 0,
		knockout: 0,
		groupHits: 0,
		knockoutHits: 0,
		hits: 0,
		answered: reads.length
	};
	for (const r of reads) {
		if (r.hit !== true || !r.points) continue;
		fold.hits += 1;
		if (r.category === 'group_stage') {
			fold.group += r.points;
			fold.groupHits += 1;
		} else {
			fold.knockout += r.points;
			fold.knockoutHits += 1;
		}
	}
	return fold;
}

// ── Column totals ────────────────────────────────────────────────────────

/** Group column = group-stage match points + group bracket credits +
 *  group-category bonus. Phase 2 is dormant; phase1 carries everything. */
export function groupPtsOf(row: LbEntryV4, bonusGroup: number): number {
	const p1 = row.breakdown.phase1;
	return p1.match_total + p1.group_advance_points + p1.group_position_points + bonusGroup;
}

/** Knockout column = KO bracket credits + knockout-category bonus.
 *  (Group matches are the only score predictions in this competition —
 *  match_total is all group.) */
export function koPtsOf(row: LbEntryV4, bonusKnockout: number): number {
	const p1 = row.breakdown.phase1;
	return (
		p1.round_of_32_points +
		p1.round_of_16_points +
		p1.quarter_final_points +
		p1.semi_final_points +
		p1.final_points +
		p1.winner_points +
		bonusKnockout
	);
}

// ── Ceiling (Points still on the table) ──────────────────────────────────

/** Max theoretical points still winnable by one entry.
 *
 *  banked total
 *  + champion alive & winner credit unpaid → advancement.winner
 *  + alive-but-uncredited finalist picks   → advancement.final each
 *  + shared remaining match points (identical for every entry)
 */
export function ceilingOf(
	row: LbEntryV4,
	rules: ScoringRules,
	remainingShared: number
): number {
	const winnerVal = rules.advancement.winner;
	const finalVal = rules.advancement.final;
	const b = row.breakdown;
	const championUpside = row.champion_alive && b.winner_points === 0 ? winnerVal : 0;
	const creditedFinalists = finalVal > 0 ? Math.round(b.final_points / finalVal) : 0;
	const uncreditedAlive = Math.max(0, (row.finalists_alive ?? 0) - creditedFinalists);
	return row.total_points + championUpside + uncreditedAlive * finalVal + remainingShared;
}

/** Max match points still on the table from unfinished score-predicted
 *  fixtures (group stage only — KO fixtures take no score predictions).
 *  Identical for every entry. */
export function remainingMatchPoints(fixtures: Fixture[], rules: ScoringRules): number {
	const perFixture =
		rules.match.correct_outcome + rules.match.exact_score + rules.match.rarity_cap;
	const remaining = fixtures.filter(
		(f) => f.stage === 'group' && f.status !== 'finished'
	).length;
	return remaining * perFixture;
}

// ── Row chrome helpers ───────────────────────────────────────────────────

/** Two-character avatar initials from an entry name. */
export function initialsOf(name: string): string {
	const words = name.trim().split(/\s+/).filter(Boolean);
	if (words.length === 0) return '??';
	if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
	return (words[0][0] + words[1][0]).toUpperCase();
}

/** One-sentence drawer story line. */
export function storyLine(row: LbEntryV4): string {
	const parts: string[] = [];
	const move = row.daily_movement;
	if (move == null || move === 0) parts.push('Held steady since yesterday');
	else if (move > 0) parts.push(`Climbed ${move} since yesterday`);
	else parts.push(`Slipped ${Math.abs(move)} since yesterday`);

	if (row.champion_pick) {
		parts.push(
			row.champion_alive
				? `${row.champion_pick} title pick alive`
				: `${row.champion_pick} title pick out`
		);
	}
	const picks = row.finalist_picks?.length ?? 0;
	if (picks > 0) parts.push(`${row.finalists_alive ?? 0} of ${picks} finalists standing`);
	return parts.join(' · ');
}

/** "best is #n · m pts off the lead" inputs for the your-entries strip. */
export function bestOwnSummary(
	rows: LbEntryV4[],
	userId: string | null | undefined
): { bestRank: number; ptsOffLead: number } | null {
	if (!userId || rows.length === 0) return null;
	const own = rows.filter((r) => r.user_id === userId);
	if (own.length === 0) return null;
	const best = own.reduce((a, b) => (b.position < a.position ? b : a));
	const leadPts = Math.max(...rows.map((r) => r.total_points));
	return { bestRank: best.position, ptsOffLead: leadPts - best.total_points };
}
