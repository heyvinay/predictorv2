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

/** Which round a fixture belongs to; null for unknown stages. */
export function roundIdForFixture(f: Fixture): RoundId | null {
	if (f.stage === 'group') {
		const n = f.match_number ?? 0;
		if (n >= 1 && n <= 24) return 'r1';
		if (n >= 25 && n <= 48) return 'r2';
		if (n >= 49 && n <= 72) return 'r3';
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
		case 'third_place':
			return 'f';
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
	const byRound = new Map<RoundId, Fixture[]>();
	for (const f of fixtures) {
		const rid = roundIdForFixture(f);
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
