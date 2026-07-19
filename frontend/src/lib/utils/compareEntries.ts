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

import type { ScoringRules } from '$lib/types/results';

/** Bridge: BracketPrediction keys (plural QF/SF) ↔ stage keys (singular).
 *  Exported so multi-entry consumers (elementValues below) can resolve a
 *  bracket Swing's `key` (a stage string) back to the BracketPrediction
 *  field without re-deriving the mapping. */
export const BRACKET_STAGES: { key: keyof BracketPrediction; stage: string; label: string }[] = [
	{ key: 'round_of_32', stage: 'round_of_32', label: 'Round of 32' },
	{ key: 'round_of_16', stage: 'round_of_16', label: 'Round of 16' },
	{ key: 'quarter_finals', stage: 'quarter_final', label: 'Quarter-finals' },
	{ key: 'semi_finals', stage: 'semi_final', label: 'Semi-finals' },
	{ key: 'final', stage: 'final', label: 'Final' }
];

export type ActualAdvancement = Partial<Record<string, Set<string>>>;

export interface BracketRow {
	stage: string;
	label: string;
	aTeams: string[];
	bTeams: string[];
	aHits: number;
	bHits: number;
	aPoints: number;
	bPoints: number;
	delta: number;
}

export function buildBracketRows(
	a: CompareEntryInput,
	b: CompareEntryInput,
	actual: ActualAdvancement,
	rules: ScoringRules
): BracketRow[] {
	const rows: BracketRow[] = [];
	for (const { key, stage, label } of BRACKET_STAGES) {
		const reached = actual[stage];
		if (!reached || reached.size === 0) continue; // stage not settled yet
		const aTeams = (a.bracket?.[key] as string[] | undefined) ?? [];
		const bTeams = (b.bracket?.[key] as string[] | undefined) ?? [];
		const per = rules.advancement[stage] ?? 0;
		const aHits = aTeams.filter((t) => reached.has(t)).length;
		const bHits = bTeams.filter((t) => reached.has(t)).length;
		rows.push({
			stage, label, aTeams, bTeams, aHits, bHits,
			aPoints: aHits * per, bPoints: bHits * per,
			delta: (aHits - bHits) * per
		});
	}
	const winners = actual['winner'];
	if (winners && winners.size > 0) {
		const per = rules.advancement['winner'] ?? 0;
		const aHit = a.bracket?.winner && winners.has(a.bracket.winner) ? 1 : 0;
		const bHit = b.bracket?.winner && winners.has(b.bracket.winner) ? 1 : 0;
		rows.push({
			stage: 'winner', label: 'Winner',
			aTeams: a.bracket?.winner ? [a.bracket.winner] : [],
			bTeams: b.bracket?.winner ? [b.bracket.winner] : [],
			aHits: aHit, bHits: bHit,
			aPoints: aHit * per, bPoints: bHit * per,
			delta: (aHit - bHit) * per
		});
	}
	return rows;
}

export interface BonusRow {
	questionId: string;
	label: string;
	aAnswer: string | null;
	bAnswer: string | null;
	aPoints: number;
	bPoints: number;
	aHit: boolean | null;
	bHit: boolean | null;
	delta: number;
}

export function buildBonusRows(a: CompareEntryInput, b: CompareEntryInput): BonusRow[] {
	const ids = new Set([
		...a.bonusReads.map((r) => r.question_id),
		...b.bonusReads.map((r) => r.question_id)
	]);
	const byIdA = new Map(a.bonusReads.map((r) => [r.question_id, r]));
	const byIdB = new Map(b.bonusReads.map((r) => [r.question_id, r]));
	const rows: BonusRow[] = [];
	for (const id of ids) {
		const ra = byIdA.get(id);
		const rb = byIdB.get(id);
		rows.push({
			questionId: id,
			label: a.questionLabels.get(id) ?? b.questionLabels.get(id) ?? 'Bonus question',
			aAnswer: ra?.answer ?? null,
			bAnswer: rb?.answer ?? null,
			aPoints: ra?.points ?? 0,
			bPoints: rb?.points ?? 0,
			aHit: ra?.hit ?? null,
			bHit: rb?.hit ?? null,
			delta: (ra?.points ?? 0) - (rb?.points ?? 0)
		});
	}
	return rows;
}

export interface Swing {
	kind: 'match' | 'bracket' | 'bonus';
	label: string;
	why: string; // "A exact (13.2) · B result (5)"
	delta: number;
	/** Identifying key for the underlying element — fixtureId for 'match',
	 *  stage for 'bracket', questionId for 'bonus'. Additive field (not
	 *  used by the two-entry /compare page) so N-entry consumers like the
	 *  wrap-up Title Matrix can look up each entry's own raw value via
	 *  elementValues() without re-parsing the display label. */
	key: string;
}

const KIND_WORD: Record<PickKind, string> = {
	exact: 'exact', result: 'result', miss: 'miss', none: 'no pick'
};

export function buildSwings(
	a: CompareEntryInput,
	b: CompareEntryInput,
	fixtureById: Map<string, Fixture>,
	actual: ActualAdvancement,
	rules: ScoringRules
): Swing[] {
	const swings: Swing[] = [];
	for (const r of buildMatchRows(a, b, fixtureById)) {
		if (r.delta === 0) continue;
		swings.push({
			kind: 'match',
			label: r.label,
			why: `${KIND_WORD[r.aKind]} (${r.aPoints}) · ${KIND_WORD[r.bKind]} (${r.bPoints})`,
			delta: r.delta,
			key: r.fixtureId
		});
	}
	for (const r of buildBracketRows(a, b, actual, rules)) {
		if (r.delta === 0) continue;
		swings.push({
			kind: 'bracket',
			label: `Bracket — ${r.label}`,
			why: `${r.aHits} vs ${r.bHits} correct (+${r.aPoints} / +${r.bPoints})`,
			delta: r.delta,
			key: r.stage
		});
	}
	for (const r of buildBonusRows(a, b)) {
		if (r.delta === 0) continue;
		swings.push({
			kind: 'bonus',
			label: `Bonus — ${r.label}`,
			why: `${r.aAnswer ?? '—'} (+${r.aPoints}) · ${r.bAnswer ?? '—'} (+${r.bPoints})`,
			delta: r.delta,
			key: r.questionId
		});
	}
	swings.sort((x, y) => Math.abs(y.delta) - Math.abs(x.delta));
	return swings;
}

/**
 * elementValues — the N-entry counterpart to buildSwings' pairwise delta.
 * Given a Swing (identifying one match / bracket stage / bonus question via
 * its `key`) and a list of entries, returns each entry's own raw point
 * value for that element, in the same order as `inputs`. Used by the
 * wrap-up Title Matrix to show top-3 entries side by side rather than a
 * two-way delta — never re-derives scoring, only reads each entry's own
 * already-served points (scoring-parity rule).
 */
export function elementValues(
	inputs: CompareEntryInput[],
	swing: Swing,
	actual: ActualAdvancement,
	rules: ScoringRules
): number[] {
	if (swing.kind === 'match') {
		return inputs.map((inp) => {
			const m = inp.matches.find((mm) => mm.fixture_id === swing.key);
			return m?.points?.total ?? 0;
		});
	}
	if (swing.kind === 'bracket') {
		if (swing.key === 'winner') {
			const per = rules.advancement['winner'] ?? 0;
			const winners = actual['winner'];
			return inputs.map((inp) => {
				const hit = !!inp.bracket?.winner && !!winners?.has(inp.bracket.winner);
				return hit ? per : 0;
			});
		}
		const stageInfo = BRACKET_STAGES.find((s) => s.stage === swing.key);
		const reached = actual[swing.key];
		const per = rules.advancement[swing.key] ?? 0;
		return inputs.map((inp) => {
			const teams = (stageInfo ? (inp.bracket?.[stageInfo.key] as string[] | undefined) : undefined) ?? [];
			const hits = reached ? teams.filter((t) => reached.has(t)).length : 0;
			return hits * per;
		});
	}
	// bonus
	return inputs.map((inp) => {
		const r = inp.bonusReads.find((br) => br.question_id === swing.key);
		return r?.points ?? 0;
	});
}
