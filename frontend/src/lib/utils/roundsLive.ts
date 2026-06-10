/**
 * LIVE-round derivation + default-round selection (spec D.1).
 *
 * One derivation feeds BOTH the round tabs' pulsing dots and the Summary
 * rows' mirrored dots (spec D.1b) — single source so they can't drift.
 */

import type { Fixture } from '$types';
import type { RoundDef, RoundId } from '$lib/types/results';

const LIVE_STATUSES = new Set(['live', 'halftime']);

/** Set of round ids containing at least one LIVE fixture. */
export function roundsWithLive(
	rounds: RoundDef[],
	fixtureById: Map<string, Fixture>
): Set<RoundId> {
	const out = new Set<RoundId>();
	for (const r of rounds) {
		for (const fid of r.fixtureIds) {
			const f = fixtureById.get(fid);
			if (f && LIVE_STATUSES.has(f.status)) {
				out.add(r.id);
				break;
			}
		}
	}
	return out;
}

/** Default selected round on mount.
 *  1. earliest LIVE-containing round in tab order
 *  2. round whose first..last kickoff window contains `now` (±1 day pad)
 *  3. last completed round
 *  4. r1
 */
export function defaultRound(
	rounds: RoundDef[],
	fixtureById: Map<string, Fixture>,
	now: Date
): RoundId {
	const live = roundsWithLive(rounds, fixtureById);
	for (const r of rounds) {
		if (r.id !== 'summary' && r.id !== 'winner' && live.has(r.id)) return r.id;
	}

	const playable = rounds.filter(
		(r) => r.id !== 'summary' && r.id !== 'winner' && r.fixtureIds.length > 0
	);
	const windows = playable.map((r) => {
		const kicks = r.fixtureIds
			.map((fid) => fixtureById.get(fid)?.kickoff)
			.filter(Boolean)
			.map((k) => new Date(k as string).getTime());
		return { id: r.id, start: Math.min(...kicks), end: Math.max(...kicks) };
	});

	const DAY = 24 * 60 * 60 * 1000;
	const t = now.getTime();
	// inside a round window (padded a day each side so the evening gap
	// between the last kickoff and midnight still counts as "inside")
	const inWindow = windows.find((w) => t >= w.start - DAY && t <= w.end + DAY);
	if (inWindow) return inWindow.id;

	const past = windows.filter((w) => w.end < t).sort((a, b) => b.end - a.end);
	if (past.length > 0) return past[0].id;

	return 'r1';
}
