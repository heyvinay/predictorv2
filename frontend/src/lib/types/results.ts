/**
 * V4 Results page types (v2.163.0).
 *
 * Lives outside the `$lib/types` barrel deliberately — the barrel
 * (types/index.ts) carries uncommitted user WIP and must not be touched
 * during this phase. Import directly: `from '$lib/types/results'`.
 */

import type { CommunityPrediction, MatchPrediction } from '$types';

/** Per-fixture points decomposition served by the backend for FINISHED
 *  fixtures (Phase 1, B.1). Mirrors backend PickPointsOut. */
export interface PickPoints {
	base: number;
	base_kind: 'miss' | 'result' | 'exact';
	rarity: number;
	total: number;
}

/** MatchPrediction as served since v2.163.0 — the `points` field exists on
 *  the wire but isn't declared on the barrel's MatchPrediction interface
 *  (user WIP lockout). V4 code paths cast through this. */
export type MatchPredictionWithPoints = MatchPrediction & {
	points?: PickPoints | null;
};

/** Round tab identifiers, in display order. `'groups'` is the
 *  Group Standings tab (v2.181.2) — a non-fixture-bearing tab sitting
 *  between R3 and R32. It carries no `fixtureIds` and uses its own
 *  pseudo-date label ("Live tables"). */
export type RoundId =
	| 'summary'
	| 'r1'
	| 'r2'
	| 'r3'
	| 'groups'
	| 'r32'
	| 'r16'
	| 'qf'
	| 'sf'
	| 'f'
	| 'winner';

/** One resolved round: its fixtures plus display metadata. */
export interface RoundDef {
	id: RoundId;
	label: string;
	/** "11 – 18 Jun" — derived from fixture kickoffs; '' when no fixtures. */
	dates: string;
	isKnockout: boolean;
	/** Fixture IDs in kickoff order. Empty for summary/winner. */
	fixtureIds: string[];
}

/** Rank + points for an entry, pulled from the leaderboard for pills. */
export interface EntryRankInfo {
	position: number;
	total_points: number;
}

/** CommunityPrediction as served since v2.163.0 — the `rank` field (B.3)
 *  exists on the wire but not on the barrel interface (WIP lockout). */
export type CommunityPredictionWithRank = CommunityPrediction & {
	rank?: number | null;
};

/** One row of the Match Detail pool list (played layout). */
export interface PoolRow {
	name: string;
	entryName: string;
	reference: string;
	rank: number | null;
	pick: string; // "2-1"
	status: 'exact' | 'result' | 'miss';
	pts: number;
	you: boolean;
}

/** Prospective payout for one 1/X/2 outcome (upcoming layout). */
export interface OutcomePayout {
	base: number;
	rarity: number;
	total: number;
	/** Rarity band for the chip. `null` while the rarity bonus is paused
	 *  (scoring-rules mode !== "logarithmic") — consumers hide the band
	 *  chip and the "+N rarity" suffix instead of promising points that
	 *  won't be paid. */
	band: 'common' | 'uncommon' | 'rare' | 'solo' | null;
	count: number;
	pct: number; // integer 0..100
}

/** [home 0..3+][away 0..3+] pick counts. */
export type SpreadGrid = number[][];

// ───────────────────────────────────────────────────────────────────────
// Knockout Match Detail bundle — served by
// GET /api/predictions/matches/{fixture_id}/ko-detail. Mirrors
// backend/app/schemas/ko_match_detail.py one-to-one. Powers the
// /results/[fixture_id] page when fixture.stage is a knockout round.
// ───────────────────────────────────────────────────────────────────────

export interface KoCohortBreakdown {
	atlas: number;
	jmfa: number;
	guests: number;
}

export interface KoPoolSplitSide {
	team: string;
	count: number;
	pct: number;
	cohorts: KoCohortBreakdown;
}

export interface KoPoolSplit {
	total: number;
	home: KoPoolSplitSide;
	away: KoPoolSplitSide;
	/** Entries with BOTH teams in their bank-stage pick list (e.g. both teams
	 *  in their R16 picks for an R32 fixture). Such entries are outcome-immune
	 *  for this fixture's advancement credit — whichever wins, they bank. */
	both_picked: number;
	/** Entries with NEITHER team picked at the bank stage — no stake on this
	 *  fixture's advancement at all. */
	neither_picked: number;
}

export interface KoImplicationSide {
	team: string;
	r32_outcome: number;
	alive_r16: number;
	alive_qf: number;
	alive_sf: number;
	alive_final: number;
	alive_winner: number;
}

export interface KoImplications {
	home: KoImplicationSide;
	away: KoImplicationSide;
}

export interface KoExposedEntry {
	entry_id: string;
	user_name: string;
	entry_reference: string | null;
	entry_name: string;
	rank: number | null;
	points_at_stake: number;
	stages_at_stake: string[];
}

export interface KoMostExposed {
	home: KoExposedEntry[];
	away: KoExposedEntry[];
}

export interface KoPoolRollEntry {
	entry_id: string;
	user_name: string;
	entry_reference: string | null;
	entry_name: string;
	pick: string;
	rank: number | null;
}

export interface KoMatchDetailResponse {
	fixture_id: string;
	home_team: string;
	away_team: string;
	stage: string;
	pool_split: KoPoolSplit;
	implications: KoImplications;
	most_exposed: KoMostExposed;
	pool_roll: KoPoolRollEntry[];
}

/** Scoring rules served by GET /api/leaderboard/scoring-rules. The page
 *  loads this once and threads it everywhere a point value appears in
 *  copy (spec C.1 — no hardcoded numbers). */
export interface ScoringRules {
	mode: string;
	match: {
		correct_outcome: number;
		exact_score: number;
		rarity_cap: number;
		[key: string]: number;
	};
	advancement: {
		round_of_32: number;
		round_of_16: number;
		quarter_final: number;
		semi_final: number;
		final: number;
		winner: number;
		[key: string]: number;
	};
}
