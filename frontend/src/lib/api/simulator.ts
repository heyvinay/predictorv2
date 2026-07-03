/**
 * What-if bracket simulator API — game-show unlock gate + run recording.
 *
 * Mirrors the call style in `api/leaderboard.ts`: thin wrappers around the
 * shared `api` client, typed responses, no local error handling — callers
 * catch `ApiResponseError` and branch on `.status` (see client.ts doc
 * comment). `recordSimulatorRun` in particular MUST propagate a 403
 * (locked) or 429 (capped, non-admin) untouched so the caller can route
 * to the right UI state instead of a generic failure toast.
 */

import { api } from './client';
import type {
	ChallengeAttempt,
	ChallengeQuestion,
	SimulatorPicksResponse,
	SimulatorStatus,
	UnlockResult
} from '$lib/types/simulator';

/** GET /api/simulator/status — feature flag, unlock state, and run quota. */
export async function getSimulatorStatus(): Promise<SimulatorStatus> {
	return api.get<SimulatorStatus>('/simulator/status');
}

/** GET /api/simulator/challenge — a fresh game-show question. No answer
 *  field in the response; only the server can grade it. */
export async function getSimulatorChallenge(): Promise<ChallengeQuestion> {
	return api.get<ChallengeQuestion>('/simulator/challenge');
}

/** POST /api/simulator/challenge — submit an attempt. The server verifies
 *  both the answer AND that `elapsed_ms <= 15000`; `unlocked` in the
 *  response reflects whether THIS attempt succeeded (unlimited attempts,
 *  no lockout on failure). */
export async function submitSimulatorChallenge(
	attempt: ChallengeAttempt
): Promise<UnlockResult> {
	return api.post<UnlockResult>('/simulator/challenge', attempt);
}

/** POST /api/simulator/challenge/fifty-fifty — spend the lifeline. Returns
 *  two option indexes that the server guarantees are NOT the correct
 *  answer, so the client can grey them out and disable clicks — the
 *  remaining pair still includes the correct answer. Correct index never
 *  leaves the server; disclosing two wrong indexes still leaves a real
 *  two-way choice.  */
export async function getSimulatorFiftyFifty(question_id: string): Promise<number[]> {
	const resp = await api.post<{ wrong_indexes: number[] }>(
		'/simulator/challenge/fifty-fifty',
		{ question_id }
	);
	return resp.wrong_indexes;
}

/** POST /api/simulator/run — record a what-if run against the caller's
 *  quota. Can reject with `ApiResponseError`:
 *    - 403 when the gate isn't unlocked yet
 *    - 429 when the non-admin run cap is exhausted
 *  Both are rethrown as-is (not caught here) so the caller's catch block
 *  can branch on `e.status` to show the right message — swallowing either
 *  here would make locked/capped indistinguishable from a real failure. */
export async function recordSimulatorRun(): Promise<SimulatorStatus> {
	return api.post<SimulatorStatus>('/simulator/run');
}

/** GET /api/simulator/bracket-picks — every eligible entry's live standing
 *  + bracket picks, the raw material the pure re-rank engine scenarios
 *  run against. */
export async function getSimulatorBracketPicks(): Promise<SimulatorPicksResponse> {
	return api.get<SimulatorPicksResponse>('/simulator/bracket-picks');
}
