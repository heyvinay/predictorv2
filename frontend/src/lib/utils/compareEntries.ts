/**
 * compareEntries — THE delta engine for head-to-head entry comparison.
 * Consumed by /compare (Plan B) and the wrap-up "How the title was won"
 * matrix (Plan C). One engine, two surfaces — never re-derive deltas
 * elsewhere. Pure: rarity/points always come from served PickPoints,
 * never recomputed client-side (scoring-parity rule).
 */

import type { Fixture } from '$types';
import type { BracketPrediction } from '$types';
import type { BonusPredictionRead } from '$lib/types/leaderboard';
import type { MatchPredictionWithPoints } from '$lib/types/results';

export interface CompareEntryInput {
	entryId: string;
	displayName: string;
	finalRank: number;
	totalPoints: number;
	groupPoints: number;
	knockoutPoints: number;
	bonusPoints: number;
	matches: MatchPredictionWithPoints[];
	bracket: BracketPrediction | null;
	bonusReads: BonusPredictionRead[];
	questionLabels: Map<string, string>;
}

export interface CompareSummary {
	total: number;
	group: number;
	knockout: number;
	bonus: number;
}

export type PickKind = 'exact' | 'result' | 'miss' | 'none';

export interface MatchRow {
	fixtureId: string;
	label: string; // "M11 · England 2–0 Iran"
	aPick: string | null; // "2–0"
	bPick: string | null;
	aPoints: number;
	bPoints: number;
	aKind: PickKind;
	bKind: PickKind;
	delta: number;
}

export function buildSummary(a: CompareEntryInput, b: CompareEntryInput): CompareSummary {
	return {
		total: a.totalPoints - b.totalPoints,
		group: a.groupPoints - b.groupPoints,
		knockout: a.knockoutPoints - b.knockoutPoints,
		bonus: a.bonusPoints - b.bonusPoints
	};
}

function fixtureLabel(f: Fixture): string {
	const score = f.score ? `${f.score.home_score}–${f.score.away_score}` : '';
	const num = f.match_number != null ? `M${f.match_number} · ` : '';
	return `${num}${f.home_team} ${score} ${f.away_team}`.replace(/\s+/g, ' ').trim();
}

function pickOf(m: MatchPredictionWithPoints | undefined): {
	pick: string | null;
	points: number;
	kind: PickKind;
} {
	if (!m) return { pick: null, points: 0, kind: 'none' };
	return {
		pick: `${m.home_score}–${m.away_score}`,
		points: m.points?.total ?? 0,
		kind: (m.points?.base_kind as PickKind | undefined) ?? 'none'
	};
}

export function buildMatchRows(
	a: CompareEntryInput,
	b: CompareEntryInput,
	fixtureById: Map<string, Fixture>
): MatchRow[] {
	const byFixtureA = new Map(a.matches.map((m) => [m.fixture_id, m]));
	const byFixtureB = new Map(b.matches.map((m) => [m.fixture_id, m]));
	const ids = new Set([...byFixtureA.keys(), ...byFixtureB.keys()]);
	const rows: MatchRow[] = [];
	for (const id of ids) {
		const f = fixtureById.get(id);
		if (!f || f.status !== 'finished' || !f.score) continue;
		if (f.stage === 'third_place') continue; // unscored-stage invariant
		const pa = pickOf(byFixtureA.get(id));
		const pb = pickOf(byFixtureB.get(id));
		rows.push({
			fixtureId: id,
			label: fixtureLabel(f),
			aPick: pa.pick,
			bPick: pb.pick,
			aPoints: pa.points,
			bPoints: pb.points,
			aKind: pa.kind,
			bKind: pb.kind,
			delta: pa.points - pb.points
		});
	}
	rows.sort((x, y) => {
		const fx = fixtureById.get(x.fixtureId)!;
		const fy = fixtureById.get(y.fixtureId)!;
		return new Date(fx.kickoff).getTime() - new Date(fy.kickoff).getTime();
	});
	return rows;
}
