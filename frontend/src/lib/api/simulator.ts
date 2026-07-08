/**
 * What-if bracket simulator API — status + run recording.
 *
 * Mirrors the call style in `api/leaderboard.ts`: thin wrappers around the
 * shared `api` client, typed responses, no local error handling — callers
 * catch `ApiResponseError` and branch on `.status` (see client.ts doc
 * comment). `recordSimulatorRun` MUST propagate a 403 (master switch off)
 * untouched so the caller can route to the right UI state instead of a
 * generic failure toast.
 */

import { api } from './client';
import type { SimulatorPicksResponse, SimulatorStatus } from '$lib/types/simulator';

/** GET /api/simulator/status — feature flag + admin status. */
export async function getSimulatorStatus(): Promise<SimulatorStatus> {
	return api.get<SimulatorStatus>('/simulator/status');
}

/** POST /api/simulator/run — record a what-if run, for auditing. Can
 *  reject with `ApiResponseError` 403 when the competition's master
 *  switch is off (non-admin) — rethrown as-is so the caller's catch
 *  block can branch on `e.status`. */
export async function recordSimulatorRun(): Promise<SimulatorStatus> {
	return api.post<SimulatorStatus>('/simulator/run');
}

/** GET /api/simulator/bracket-picks — every eligible entry's live standing
 *  + bracket picks, the raw material the pure re-rank engine scenarios
 *  run against. */
export async function getSimulatorBracketPicks(): Promise<SimulatorPicksResponse> {
	return api.get<SimulatorPicksResponse>('/simulator/bracket-picks');
}
