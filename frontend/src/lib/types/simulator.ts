/**
 * What-if bracket simulator types (pure re-rank engine, KO-only stage).
 *
 * Lives OUTSIDE the `$lib/types` barrel deliberately — same convention as
 * `results.ts` / `admin.ts` (the barrel carries uncommitted user WIP and
 * must not be touched). Import directly: `from '$lib/types/simulator'`.
 *
 * Bonus-question scoring is explicitly deferred — this stage covers KO
 * advancement points only (see CLAUDE.md / task scope).
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
	/** Current (real) group-stage points — held fixed across every
	 *  what-if scenario; only the knockout component gets rescored. */
	group_points: number;
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

/** One row of the projected (what-if) standings table. */
export interface ProjectedRow {
	entry_id: string;
	entry_name: string;
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

// ── Game-show unlock gate (v2.194.x) ────────────────────────────────────────

/** GET/POST /api/simulator/status|challenge envelope shape. `runs_remaining`
 *  is `null` for admins (unlimited); non-admins get a finite countdown
 *  against `cap`. `reset_at` is an ISO timestamp for when `runs_used` next
 *  resets, or `null` if there's no reset window (or the user is admin). */
export interface SimulatorStatus {
	feature_enabled: boolean;
	unlocked: boolean;
	is_admin: boolean;
	runs_used: number;
	runs_remaining: number | null;
	cap: number;
	reset_at: string | null;
}

/** GET /api/simulator/challenge response. Deliberately carries no answer
 *  field — the server is the only party that knows which option is
 *  correct, both at question time and at grading time. */
export interface ChallengeQuestion {
	question_id: string;
	question: string;
	options: string[];
}

/** POST /api/simulator/challenge request body. `elapsed_ms` is measured
 *  client-side from question render to option click (or timeout) via
 *  `performance.now()`; the server independently rejects anything over
 *  15000ms regardless of what the client reports. */
export interface ChallengeAttempt {
	question_id: string;
	answer_index: number;
	elapsed_ms: number;
}

/** POST /api/simulator/challenge response — the graded outcome plus a
 *  fresh status snapshot (unlocked flips true on a correct answer). */
export interface UnlockResult {
	unlocked: boolean;
	status: SimulatorStatus;
}
