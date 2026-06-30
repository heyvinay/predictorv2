/**
 * Match Detail (V4) derivations — all pure, all pinned by vitest.
 *
 * Points math routes through the parity-pinned computeMatchPoints /
 * logarithmicRarityBonus from matchBreakdown.ts — this module derives
 * VIEWS of the pool (splits, grids, payouts, rows), never new scoring.
 *
 * Upset badge (spec C.3, amended in plan §Deviations): fires when the
 * actual winner's pick share is < 30% with a pool of ≥ 10. The
 * cross-fixture tie-break is dropped — it would cost one /community
 * fetch per fixture in the round.
 */

import type {
	CommunityPredictionWithRank,
	OutcomePayout,
	PoolRow,
	RoundDef,
	ScoringRules,
	SpreadGrid
} from '$lib/types/results';
import { computeMatchPoints, logarithmicRarityBonus, rarityTier } from './matchBreakdown';

export type Outcome = '1' | 'X' | '2';
export type Side = 'home' | 'draw' | 'away';

export function outcomeOf(h: number, a: number): Outcome {
	if (h > a) return '1';
	if (h < a) return '2';
	return 'X';
}

export function sideOf(h: number, a: number): Side {
	if (h > a) return 'home';
	if (h < a) return 'away';
	return 'draw';
}

/** Loser side of a KO fixture, resolving pens → ET → regulation (mirrors
 *  the backend `Score.outcome` priority). Returns null when the result
 *  is level on every leg the data carries (group-stage draws, or a KO
 *  fixture not yet decided).
 *
 *  Used by every surface that needs to grey out the eliminated team —
 *  match-detail hero, results round/KO row, dashboard latest-results
 *  cell. Regulation-only comparison would leave both sides un-greyed
 *  for any 1-1 → ET/pens result. */
export type LoserSide = 'home' | 'away' | null;

interface KoScoreLike {
	home_score: number;
	away_score: number;
	home_score_et: number | null;
	away_score_et: number | null;
	home_penalties: number | null;
	away_penalties: number | null;
}

export function koLoserSide(score: KoScoreLike | null | undefined): LoserSide {
	if (!score) return null;
	const ph = score.home_penalties;
	const pa = score.away_penalties;
	if (ph != null && pa != null && ph !== pa) return ph < pa ? 'home' : 'away';
	const eh = score.home_score_et;
	const ea = score.away_score_et;
	if (eh != null && ea != null && eh !== ea) return eh < ea ? 'home' : 'away';
	if (score.home_score < score.away_score) return 'home';
	if (score.home_score > score.away_score) return 'away';
	return null;
}

/** Winner side — inverse of koLoserSide. Distinct named function so call
 *  sites read fluently ("dim the loser" vs "highlight the winner"). */
export function koWinnerSide(score: KoScoreLike | null | undefined): LoserSide {
	const loser = koLoserSide(score);
	if (loser === 'home') return 'away';
	if (loser === 'away') return 'home';
	return null;
}

const SIDE_TO_OUTCOME: Record<Side, Outcome> = { home: '1', draw: 'X', away: '2' };

/** Outcome split across the pool — counts + integer percentages. */
export function poolSplit(preds: CommunityPredictionWithRank[]): {
	counts: Record<Side, number>;
	pcts: Record<Side, number>;
} {
	const counts: Record<Side, number> = { home: 0, draw: 0, away: 0 };
	for (const p of preds) counts[sideOf(p.home_score, p.away_score)]++;
	const total = preds.length;
	const pct = (n: number) => (total > 0 ? Math.round((n / total) * 100) : 0);
	return {
		counts,
		pcts: { home: pct(counts.home), draw: pct(counts.draw), away: pct(counts.away) }
	};
}

/** [home][away] pick counts on a 0..cap axis; scores above cap clamp in. */
export function spreadGrid(preds: CommunityPredictionWithRank[], cap = 3): SpreadGrid {
	const grid: number[][] = Array.from({ length: cap + 1 }, () =>
		Array.from({ length: cap + 1 }, () => 0)
	);
	for (const p of preds) {
		const h = Math.min(p.home_score, cap);
		const a = Math.min(p.away_score, cap);
		grid[h][a]++;
	}
	return grid;
}

/** Pool rows for the played layout: status + points per entry, split into
 *  banked (scored) and missed. `youReference` flags the caller's entry. */
export function poolRows(
	preds: CommunityPredictionWithRank[],
	actual: { home: number; away: number },
	rules: ScoringRules,
	youReference: string | null
): { banked: PoolRow[]; missed: PoolRow[] } {
	const total = preds.length;
	const actualOutcome = outcomeOf(actual.home, actual.away);
	const correct = preds.filter(
		(p) => outcomeOf(p.home_score, p.away_score) === actualOutcome
	).length;

	const rows: PoolRow[] = preds.map((p) => {
		const r = computeMatchPoints({
			mode: rules.mode,
			predictedHome: p.home_score,
			predictedAway: p.away_score,
			actualHome: actual.home,
			actualAway: actual.away,
			totalPredictors: total,
			correctPredictors: correct,
			outcomePoints: rules.match.correct_outcome,
			exactPoints: rules.match.exact_score,
			cap: rules.match.rarity_cap
		});
		return {
			name: p.user_name,
			entryName: p.entry_name,
			reference: p.entry_reference,
			rank: p.rank ?? null,
			pick: `${p.home_score}-${p.away_score}`,
			status: r.exactScore ? 'exact' : r.correctOutcome ? 'result' : 'miss',
			pts: r.points,
			you: youReference !== null && p.entry_reference === youReference
		};
	});

	const banked = rows
		.filter((r) => r.pts > 0)
		.sort((a, b) => b.pts - a.pts || (a.rank ?? 9999) - (b.rank ?? 9999));
	const missed = rows
		.filter((r) => r.pts <= 0)
		.sort((a, b) => (a.rank ?? 9999) - (b.rank ?? 9999));
	return { banked, missed };
}

/** Prospective payout per outcome for the upcoming layout. base =
 *  correct_outcome; rarity from the pool share of that side. The
 *  exact-score bonus is shown separately by the UI ("exact adds
 *  +{exact} on top"), not folded in here.
 *
 *  Mode-gated (same rule as BreakdownCard / RarityExplainer): while
 *  rarity is paused (scoring-rules mode !== "logarithmic") the rarity
 *  component is 0 and `band` is null so the UI doesn't promise bonus
 *  points the engine won't pay. */
export function outcomePayouts(
	preds: CommunityPredictionWithRank[],
	rules: ScoringRules
): Record<Side, OutcomePayout> {
	const { counts, pcts } = poolSplit(preds);
	const total = preds.length;
	const rarityActive = rules.mode === 'logarithmic';
	const make = (side: Side): OutcomePayout => {
		const count = counts[side];
		const rarity = rarityActive
			? logarithmicRarityBonus(total, count, rules.match.rarity_cap)
			: 0;
		const tier = rarityTier(rarity, count);
		return {
			base: rules.match.correct_outcome,
			rarity,
			total: rules.match.correct_outcome + rarity,
			band: !rarityActive
				? null
				: tier.cls === 'solo'
				? 'solo'
				: tier.cls === 'rare'
				? 'rare'
				: tier.cls === 'uncommon'
				? 'uncommon'
				: 'common',
			count,
			pct: pcts[side]
		};
	};
	return { home: make('home'), draw: make('draw'), away: make('away') };
}

/** Upset badge heuristic (C.3, no cross-fixture tie-break). */
export function isUpset(
	preds: CommunityPredictionWithRank[],
	actualOutcome: Outcome
): boolean {
	const total = preds.length;
	if (total < 10) return false;
	const winners = preds.filter(
		(p) => outcomeOf(p.home_score, p.away_score) === actualOutcome
	).length;
	return winners / total < 0.3;
}

/** How many pool entries called the given side — for the rarity note. */
export function sideCallers(preds: CommunityPredictionWithRank[], side: Side): number {
	const want = SIDE_TO_OUTCOME[side];
	return preds.filter((p) => outcomeOf(p.home_score, p.away_score) === want).length;
}

/** Locate a fixture inside its round for the prev/next pager. */
export function prevNextInRound(
	rounds: RoundDef[],
	fixtureId: string
): {
	roundId: RoundDef['id'];
	label: string;
	index: number;
	count: number;
	prevId: string | null;
	nextId: string | null;
} | null {
	for (const r of rounds) {
		const index = r.fixtureIds.indexOf(fixtureId);
		if (index === -1) continue;
		return {
			roundId: r.id,
			label: r.label,
			index,
			count: r.fixtureIds.length,
			prevId: index > 0 ? r.fixtureIds[index - 1] : null,
			nextId: index < r.fixtureIds.length - 1 ? r.fixtureIds[index + 1] : null
		};
	}
	return null;
}
