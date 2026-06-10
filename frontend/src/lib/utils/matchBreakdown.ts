/**
 * Per-match breakdown helper for the Results & Fixtures page.
 *
 * Given a fixture, the caller's prediction, agreement counts for that fixture,
 * and the active scoring config, this returns the structured "breakdown" that
 * the result card renders: the four pills (Outcome / Exact / Rarity / Total),
 * the tier (border colour), the visible "Your pick" chip state, and a
 * live-now scoring projection when the match is in play.
 *
 * The rarity bonus mirrors the backend's LogarithmicScoring formula:
 *   R = min(rarity_cap, round(alpha * log2(1 / (2f))))
 * where f = agrees_outcome / total (per-fixture predictor counts) and
 * alpha = 10/log2(15). `agrees_outcome` IS `correct_predictors` whenever the
 * caller's outcome matches the actual result — so the projection is exact for
 * finished matches and a faithful "what will I get if my pick stands"
 * estimate for upcoming ones. R is capped at rarity_cap and gated at f >= 0.5.
 */

import type { Fixture, MatchPrediction } from '$types';
import type { FixtureAgreement } from '$api/predictions';
import type { ScoringConfig } from '$api/competition';

export type MatchState = 'finished' | 'live' | 'locked' | 'open';
export type ResultTier =
	| 'tier-exact'
	| 'tier-outcome'
	| 'tier-miss'
	| 'tier-live'
	| 'tier-locked'
	| 'tier-open';

export type PillState =
	| 'hit-exact'
	| 'hit-outcome'
	| 'hit-rarity'
	| 'hit-rarity solo'
	| 'miss'
	| 'potential'
	| 'potential solo'
	| 'none';

export interface Pill {
	state: PillState;
	pts: number;
	lab: string;
}

export type YpickClass = '' | 'empty' | 'exact' | 'outcome' | 'miss';

export interface RarityTier {
	cls: 'solo' | 'rare' | 'uncommon' | 'common';
	lbl: string;
}

export interface MatchBreakdown {
	state: MatchState;
	tier: ResultTier;
	outcomePill: Pill;
	scorePill: Pill;
	rarityPill: Pill;
	totalPts: number;
	totalLabel: string;
	totalDisplay: string; // pre-formatted (e.g. "+12", "0", "—")
	ypickClass: YpickClass;
	ypickLabel: string;
	/** Live-only: result if the match froze at the current score. */
	liveResult: 'exact' | 'outcome' | 'miss' | null;
}

/** Map an integer rarity bonus + the pool size to a human-readable tier. */
export function rarityTier(bonus: number, agreesOutcome: number): RarityTier {
	if (agreesOutcome <= 1) return { cls: 'solo', lbl: 'Only You' };
	if (bonus >= 5) return { cls: 'rare', lbl: 'Rare' };
	if (bonus >= 2) return { cls: 'uncommon', lbl: 'Uncommon' };
	return { cls: 'common', lbl: 'Common' };
}

/** Logarithmic rarity bonus — mirror of backend `_logarithmic_rarity_bonus`.
 * Anchor: alpha chosen so f = 1/30 hits the cap of 10.
 */
const LOG_ALPHA = 10 / Math.log2(15);

export function logarithmicRarityBonus(
	total: number,
	correct: number,
	cap: number
): number {
	if (total <= 0 || correct <= 0) return 0;
	const f = correct / total;
	if (f >= 0.5) return 0;
	const raw = LOG_ALPHA * Math.log2(1 / (2 * f));
	return Math.min(cap, Math.max(0, Math.round(raw)));
}

/** Pure match-points calculation — mirror of backend `compute_match_points`
 * (`backend/app/services/scoring.py`). Takes only primitives so both languages
 * validate against the SAME shared golden cases (`shared/scoring-parity-cases.json`).
 * `computeBreakdown` routes its banked/live total through this, so the displayed
 * projection can't drift from the backend's awarded points. `cap` is unused for
 * mode 'fixed'. */
export function computeMatchPoints(p: {
	mode: string;
	predictedHome: number;
	predictedAway: number;
	actualHome: number;
	actualAway: number;
	totalPredictors: number;
	correctPredictors: number;
	outcomePoints: number;
	exactPoints: number;
	cap: number;
}): { points: number; correctOutcome: boolean; exactScore: boolean } {
	const correctOutcome =
		outcomeSign(p.predictedHome, p.predictedAway) === outcomeSign(p.actualHome, p.actualAway);
	const exactScore = p.predictedHome === p.actualHome && p.predictedAway === p.actualAway;

	let points = 0;
	if (correctOutcome) {
		points += p.outcomePoints;
		if (p.mode === 'hybrid') {
			if (p.correctPredictors > 0) {
				points += Math.min(p.cap, Math.floor(p.totalPredictors / p.correctPredictors));
			}
		} else if (p.mode === 'logarithmic') {
			points += logarithmicRarityBonus(p.totalPredictors, p.correctPredictors, p.cap);
		}
		// mode 'fixed': no rarity bonus.
	}
	if (exactScore) points += p.exactPoints;

	return { points, correctOutcome, exactScore };
}

/**
 * What status bucket does this fixture fall into for the Results page?
 * Live fixtures keep showing a (possibly partial) score; locked ones are
 * scheduled-but-inside-the-5-min-window; open is scheduled-and-not-yet-locked.
 */
export function matchState(fixture: Fixture): MatchState {
	if (fixture.status === 'finished') return 'finished';
	if (fixture.status === 'live' || fixture.status === 'halftime') return 'live';
	if (fixture.is_locked) return 'locked';
	return 'open';
}

function outcomeSign(h: number, a: number): '1' | 'X' | '2' {
	if (h > a) return '1';
	if (h < a) return '2';
	return 'X';
}

/**
 * Compute the per-match breakdown for the Results card. Pure — no I/O.
 */
export function computeBreakdown(
	fixture: Fixture,
	prediction: MatchPrediction | undefined,
	agreement: FixtureAgreement | undefined,
	config: ScoringConfig
): MatchBreakdown {
	const state = matchState(fixture);
	const isFinished = state === 'finished';
	const isLive = state === 'live';
	const isUpcoming = !isFinished && !isLive;

	// Rarity bonus we'd earn IF the caller's outcome is correct.
	// `agrees_outcome` = number of predictors (incl. caller) who picked the
	// same 1/X/2 as the caller — which IS `correct_predictors` precisely
	// when the caller's outcome matches the actual result.
	const wantRarity = config.mode === 'logarithmic';
	const projectedBonus =
		wantRarity && agreement && agreement.agrees_outcome > 0
			? logarithmicRarityBonus(
					agreement.total,
					agreement.agrees_outcome,
					config.rarity_cap
				)
			: 0;
	const rar =
		agreement && wantRarity
			? rarityTier(projectedBonus, agreement.agrees_outcome)
			: null;

	// Score state vs. caller's pick — for finished matches AND for live
	// matches (treated as "if FT now"). Locked/open have no score yet.
	let liveResult: 'exact' | 'outcome' | 'miss' | null = null;
	let finishedResult: 'exact' | 'outcome' | 'miss' | null = null;
	if (prediction && fixture.score) {
		const exact =
			prediction.home_score === fixture.score.home_score &&
			prediction.away_score === fixture.score.away_score;
		const sameOutcome =
			outcomeSign(prediction.home_score, prediction.away_score) === fixture.score.outcome;
		const result = exact ? 'exact' : sameOutcome ? 'outcome' : 'miss';
		if (isFinished) finishedResult = result;
		else if (isLive) liveResult = result;
	}

	// Tier (top-border colour on the breakdown strip)
	let tier: ResultTier;
	if (isFinished) {
		tier =
			finishedResult === 'exact'
				? 'tier-exact'
				: finishedResult === 'outcome'
				? 'tier-outcome'
				: 'tier-miss';
	} else if (isLive) {
		tier =
			liveResult === 'exact'
				? 'tier-exact'
				: liveResult === 'outcome'
				? 'tier-outcome'
				: liveResult === 'miss'
				? 'tier-miss'
				: 'tier-live';
	} else if (state === 'locked') {
		tier = 'tier-locked';
	} else {
		tier = 'tier-open';
	}

	// Pills + totals
	let outcomePill: Pill;
	let scorePill: Pill;
	let rarityPill: Pill;
	let totalPts = 0;
	let totalLabel = '';

	const resultNow = finishedResult ?? liveResult;

	if (isFinished || (isLive && resultNow)) {
		// Earned (or live-projected) points. The TOTAL is computed by the shared
		// `computeMatchPoints` so it can't drift from the backend's awarded points;
		// the pills below are display-only decompositions of that same total.
		totalPts =
			prediction && fixture.score
				? computeMatchPoints({
						mode: config.mode,
						predictedHome: prediction.home_score,
						predictedAway: prediction.away_score,
						actualHome: fixture.score.home_score,
						actualAway: fixture.score.away_score,
						totalPredictors: agreement?.total ?? 0,
						correctPredictors: agreement?.agrees_outcome ?? 0,
						outcomePoints: config.outcome_points,
						exactPoints: config.exact_points,
						cap: config.rarity_cap
					}).points
				: 0;

		if (resultNow === 'exact') {
			outcomePill = { state: 'hit-outcome', pts: config.outcome_points, lab: 'Outcome' };
			scorePill = { state: 'hit-exact', pts: config.exact_points, lab: 'Exact' };
			if (wantRarity && projectedBonus > 0) {
				rarityPill = {
					state: rar && rar.cls === 'solo' ? 'hit-rarity solo' : 'hit-rarity',
					pts: projectedBonus,
					lab: rar?.lbl ?? 'Rarity'
				};
			} else {
				rarityPill = { state: 'none', pts: 0, lab: wantRarity ? 'No bonus' : 'Fixed' };
			}
		} else if (resultNow === 'outcome') {
			outcomePill = { state: 'hit-outcome', pts: config.outcome_points, lab: 'Outcome' };
			scorePill = { state: 'miss', pts: 0, lab: 'Exact' };
			if (wantRarity && projectedBonus > 0) {
				rarityPill = {
					state: rar && rar.cls === 'solo' ? 'hit-rarity solo' : 'hit-rarity',
					pts: projectedBonus,
					lab: rar?.lbl ?? 'Rarity'
				};
			} else {
				rarityPill = { state: 'none', pts: 0, lab: wantRarity ? 'No bonus' : 'Fixed' };
			}
		} else {
			// miss
			outcomePill = { state: 'miss', pts: 0, lab: 'Outcome' };
			scorePill = { state: 'miss', pts: 0, lab: 'Exact' };
			rarityPill = { state: 'none', pts: 0, lab: 'Void' };
		}
		totalLabel = isFinished ? 'Banked' : 'If FT now';
	} else {
		// Locked / open / live-without-pick → "potential" pills, dashed
		outcomePill = { state: 'potential', pts: config.outcome_points, lab: 'Outcome' };
		scorePill = { state: 'potential', pts: config.exact_points, lab: 'Exact' };
		if (wantRarity && projectedBonus > 0) {
			rarityPill = {
				state: rar && rar.cls === 'solo' ? 'potential solo' : 'potential',
				pts: projectedBonus,
				lab: rar?.lbl ?? 'Rarity'
			};
		} else {
			rarityPill = {
				state: 'none',
				pts: 0,
				lab: !prediction ? 'No pick' : wantRarity ? 'No bonus' : 'Fixed'
			};
		}
		totalPts = prediction
			? config.outcome_points + config.exact_points + (rarityPill.state === 'none' ? 0 : projectedBonus)
			: 0;
		totalLabel = state === 'locked' ? 'Locked' : 'Up to';
	}

	// Your-pick chip
	let ypickClass: YpickClass = '';
	if (!prediction) ypickClass = 'empty';
	else if (isFinished && finishedResult) ypickClass = finishedResult;
	else if (isLive && liveResult) ypickClass = liveResult;

	let ypickLabel = 'Pick';
	if (isFinished) {
		ypickLabel =
			finishedResult === 'exact'
				? '✓ Exact'
				: finishedResult === 'outcome'
				? '✓ Outcome'
				: '✗ Miss';
	} else if (isLive && liveResult === 'exact') ypickLabel = '◉ On track';
	else if (isLive && liveResult === 'outcome') ypickLabel = '◉ Outcome';
	else if (isLive && liveResult === 'miss') ypickLabel = '◉ Off pace';

	// Display string for the total cell
	let totalDisplay: string;
	if (isFinished || (isLive && resultNow)) {
		totalDisplay = totalPts > 0 ? `+${totalPts}` : '0';
	} else if (prediction) {
		totalDisplay = `+${totalPts}`;
	} else {
		totalDisplay = '—';
	}

	return {
		state,
		tier,
		outcomePill,
		scorePill,
		rarityPill,
		totalPts,
		totalLabel,
		totalDisplay,
		ypickClass,
		ypickLabel,
		liveResult
	};
}

/** Format a stage code (round_of_32, quarter_final, etc.) for display. */
export function stageLabel(stage: string): string {
	const map: Record<string, string> = {
		round_of_32: 'Round of 32',
		round_of_16: 'Round of 16',
		quarter_final: 'Quarter-final',
		semi_final: 'Semi-final',
		final: 'Final',
		third_place: 'Third place'
	};
	return map[stage] ?? stage.replace(/_/g, ' ');
}

/** Short stage code for compact pills/headers ("R32", "QF", "F"). */
export function stageShort(stage: string): string {
	const map: Record<string, string> = {
		round_of_32: 'R32',
		round_of_16: 'R16',
		quarter_final: 'QF',
		semi_final: 'SF',
		final: 'F',
		third_place: '3rd'
	};
	return map[stage] ?? stage.toUpperCase();
}
