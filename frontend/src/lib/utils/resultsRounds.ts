/**
 * Round mapping for the V4 Results page.
 *
 * WC2026 group fixtures bucket into three "rounds" (matchdays) by
 * match_number: MD1 = 1–24, MD2 = 25–48, MD3 = 49–72. Knockout rounds
 * map from Fixture.stage (SINGULAR values — the v2.161.0 invariant).
 * The "Finals" tab (id 'f') carries BOTH the third-place playoff and the
 * final; only the final fixture earns bracket chips/points.
 */

import type { Fixture } from '$types';
import type { RoundDef, RoundId } from '$lib/types/results';

export const ROUND_ORDER: RoundId[] = [
	'summary',
	'r1',
	'r2',
	'r3',
	'r32',
	'r16',
	'qf',
	'sf',
	'f',
	'winner'
];

export const ROUND_LABELS: Record<RoundId, string> = {
	summary: 'Summary',
	r1: 'Round 1',
	r2: 'Round 2',
	r3: 'Round 3',
	r32: 'Round of 32',
	r16: 'Round of 16',
	qf: 'Quarter-Finals',
	sf: 'Semi-Finals',
	f: 'Finals',
	winner: 'Winner'
};

/** KO progression chain — which round a fixture's winners advance to. */
export const NEXT_ROUND: Record<string, RoundId | null> = {
	r32: 'r16',
	r16: 'qf',
	qf: 'sf',
	sf: 'f',
	f: null
};

/** Stage value (singular, as stored) per KO round — used to read the
 *  matching advancement points from scoring-rules and the matching
 *  bracket picks. */
export const ROUND_STAGE: Record<string, string> = {
	r32: 'round_of_32',
	r16: 'round_of_16',
	qf: 'quarter_final',
	sf: 'semi_final',
	f: 'final'
};

const KO_ROUNDS = new Set<RoundId>(['r32', 'r16', 'qf', 'sf', 'f']);

export function isKnockoutRound(id: RoundId): boolean {
	return KO_ROUNDS.has(id);
}

/** Derive each group fixture's matchday (1..3) from per-team kickoff
 *  order: a team's Nth group game is its matchday N. Used as the
 *  fallback when `match_number` is null — TRUE in the dev/prod DB as of
 *  2026-06-10 (verified: all 105 fixtures carry match_number = NULL),
 *  so this is effectively the primary path. */
export function deriveGroupMatchdays(fixtures: Fixture[]): Map<string, 1 | 2 | 3> {
	const groupFixtures = fixtures
		.filter((f) => f.stage === 'group')
		.sort((a, b) => new Date(a.kickoff).getTime() - new Date(b.kickoff).getTime());
	const gamesSeen = new Map<string, number>();
	const out = new Map<string, 1 | 2 | 3>();
	for (const f of groupFixtures) {
		const n = Math.max(gamesSeen.get(f.home_team) ?? 0, gamesSeen.get(f.away_team) ?? 0) + 1;
		out.set(f.id, Math.min(n, 3) as 1 | 2 | 3);
		gamesSeen.set(f.home_team, (gamesSeen.get(f.home_team) ?? 0) + 1);
		gamesSeen.set(f.away_team, (gamesSeen.get(f.away_team) ?? 0) + 1);
	}
	return out;
}

/** Which round a fixture belongs to; null for unknown stages. Group
 *  fixtures use match_number when present, else the caller-supplied
 *  derived matchday map (see deriveGroupMatchdays). */
export function roundIdForFixture(
	f: Fixture,
	derivedMatchdays?: Map<string, 1 | 2 | 3>
): RoundId | null {
	if (f.stage === 'group') {
		const n = f.match_number ?? 0;
		if (n >= 1 && n <= 24) return 'r1';
		if (n >= 25 && n <= 48) return 'r2';
		if (n >= 49 && n <= 72) return 'r3';
		const md = derivedMatchdays?.get(f.id);
		if (md === 1) return 'r1';
		if (md === 2) return 'r2';
		if (md === 3) return 'r3';
		return null;
	}
	switch (f.stage) {
		case 'round_of_32':
			return 'r32';
		case 'round_of_16':
			return 'r16';
		case 'quarter_final':
			return 'qf';
		case 'semi_final':
			return 'sf';
		case 'final':
			return 'f';
		// 'third_place' is omitted on purpose — the prediction game
		// neither collects picks nor awards points for that fixture, so
		// the Results page must not surface it (was previously bucketed
		// into the 'f' round, producing a phantom second row in Finals).
		default:
			return null;
	}
}

/** "11 – 18 Jun" / "28 Jun – 4 Jul" / "19 Jul" from two ISO kickoffs. */
export function formatDateRange(startIso: string, endIso: string): string {
	const start = new Date(startIso);
	const end = new Date(endIso);
	const day = (d: Date) => d.getUTCDate();
	const mon = (d: Date) =>
		d.toLocaleDateString('en-GB', { month: 'short', timeZone: 'UTC' });
	if (day(start) === day(end) && mon(start) === mon(end)) {
		return `${day(end)} ${mon(end)}`;
	}
	if (mon(start) === mon(end)) {
		return `${day(start)} – ${day(end)} ${mon(end)}`;
	}
	return `${day(start)} ${mon(start)} – ${day(end)} ${mon(end)}`;
}

/** Resolve the full ten-round structure from the fixtures list. */
export function buildRounds(fixtures: Fixture[]): RoundDef[] {
	const derivedMatchdays = deriveGroupMatchdays(fixtures);
	const byRound = new Map<RoundId, Fixture[]>();
	for (const f of fixtures) {
		const rid = roundIdForFixture(f, derivedMatchdays);
		if (!rid) continue;
		const list = byRound.get(rid) ?? [];
		list.push(f);
		byRound.set(rid, list);
	}

	return ROUND_ORDER.map((id) => {
		const list = (byRound.get(id) ?? []).sort(
			(a, b) => new Date(a.kickoff).getTime() - new Date(b.kickoff).getTime()
		);
		const dates =
			list.length > 0
				? formatDateRange(list[0].kickoff, list[list.length - 1].kickoff)
				: id === 'summary'
				? 'All rounds'
				: '';
		return {
			id,
			label: ROUND_LABELS[id],
			dates,
			isKnockout: isKnockoutRound(id),
			fixtureIds: list.map((f) => f.id)
		};
	});
}
