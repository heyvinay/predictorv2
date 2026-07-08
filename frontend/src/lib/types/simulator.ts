/**
 * What-if bracket simulator types (pure re-rank engine, KO-only stage).
 *
 * Lives OUTSIDE the `$lib/types` barrel deliberately — same convention as
 * `results.ts` / `admin.ts` (the barrel carries uncommitted user WIP and
 * must not be touched). Import directly: `from '$lib/types/simulator'`.
 *
 * Bonus-question points are never rescored by a hypothetical bracket —
 * neither category is resolved by who wins a KO match — so both ride
 * through unchanged from the real leaderboard: group-stage bonus is
 * folded into `group_points`, knockout-stage bonus is its own field.
 * Only KO advancement points get rescored per scenario.
 */

/** One entry's bracket picks, served by GET /api/simulator/bracket-picks.
 *  Field names mirror `BracketPrediction` (frontend/src/lib/types/index.ts)
 *  so the same helpers (`bracketPicksForRound`) work on both shapes. */
export interface SimulatorBracketPicks {
	round_of_32: string[];
	round_of_16: string[];
	quarter_finals: string[];
	semi_finals: string[];
	final: string[];
	winner: string | null;
}

/** One pool entry's identity, live standing, and bracket picks. */
export interface SimulatorEntryPicks {
	entry_id: string;
	entry_name: string;
	user_id: string;
	user_name: string;
	/** Current (real) leaderboard position — 1-based. */
	position: number;
	/** Current (real) total points — group + knockout + bonus, banked. */
	total_points: number;
	/** Current (real) group-stage points, INCLUDING group-stage bonus
	 *  questions — held fixed across every what-if scenario; only the
	 *  knockout advancement component gets rescored. */
	group_points: number;
	/** Current (real) knockout-stage bonus-question points (e.g. the
	 *  Top/Flop question) — held fixed across every what-if scenario,
	 *  same as `group_points`, since no bonus question is resolved by
	 *  who wins a bracket match. */
	bonus_knockout_points: number;
	picks: SimulatorBracketPicks;
}

/** GET /api/simulator/bracket-picks response envelope. */
export interface SimulatorPicksResponse {
	entries: SimulatorEntryPicks[];
	last_calculated: string;
}

// ── Pure engine types ─────────────────────────────────────────────────────

/** Hypothetical winners the user has chosen for still-unplayed matches,
 *  keyed by FIFA match number (73-104). Matches not present fall back to
 *  the real result (if finished) or stay unresolved. */
export type HypoWinners = Map<number, string>;

/** One resolved KO match under a scenario (real result + hypo overrides
 *  layered on top). `home`/`away` are null until their upstream source
 *  resolves; `winner` is null until the match itself resolves. */
export interface ResolvedMatch {
	home: string | null;
	away: string | null;
	winner: string | null;
}

/** Output of `resolveScenario`: every team's furthest-reached round rank
 *  under the scenario, the resolved champion (if the Final has a winner),
 *  and the full per-match resolution (useful for debugging/UI). */
export interface ResolvedScenario {
	/** team name -> highest round rank reached (see ROUND_RANK below). */
	reached: Map<string, number>;
	champion: string | null;
	matches: Map<number, ResolvedMatch>;
}

/** One row of the projected (what-if) standings table.
 *
 *  Satisfies `NamedEntryRow` (leaderboardV4.ts) — carries `user_id` +
 *  `user_name` + `entry_name` — so the same `rowDisplayName()` and
 *  `multiEntryUserIds()` helpers the main leaderboard uses can render
 *  the "Person — Entry name" / "Person" naming on this table too. */
export interface ProjectedRow {
	entry_id: string;
	entry_name: string;
	user_id: string;
	user_name: string;
	oldPos: number;
	oldTotal: number;
	newTotal: number;
	newPos: number;
	/** oldPos - newPos: positive = moved up, negative = moved down. */
	deltaPos: number;
	/** newTotal - oldTotal. */
	deltaPts: number;
}

/** One still-open KO match whose two possible outcomes are compared for
 *  their effect on a single entry's projected rank ("pivotal" = high
 *  swing). Produced by `pivotalMatches`. */
export interface PivotalMatch {
	matchNumber: number;
	home: string;
	away: string;
	/** My entry's `newPos` if `home` wins this match. */
	posIfHome: number;
	/** My entry's `newPos` if `away` wins this match. */
	posIfAway: number;
	/** abs(posIfHome - posIfAway) — how much this match's outcome moves me. */
	swing: number;
}

// ── Gating — admin master switch only ───────────────────────────────────────

/** GET /api/simulator/status response. `feature_enabled` reflects the
 *  active competition's admin-controlled master switch; admins always
 *  have full access regardless of its value. */
export interface SimulatorStatus {
	feature_enabled: boolean;
	is_admin: boolean;
}
