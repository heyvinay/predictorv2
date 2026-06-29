/**
 * Bracket geometry helpers (v2.184.x).
 *
 * Maps between Fixture rows and FIFA match numbers, then walks the
 * source graph in bracketConfig.ts to find the local "neighborhood"
 * of any fixture — its sibling R32, the two R16s that feed the same
 * QF, the QF, the SF, the Final.
 *
 * Mirrors backend/app/services/bracket_seeding.py — the same
 * EXT_ID_TO_MATCH_NUMBER table for R32, plus the recursive walk
 * implemented there. Frontend version exists because BracketQuadrant
 * (a client-rendered SVG) needs the structure without a round-trip,
 * and the equivalent info isn't on the FixtureRead schema.
 *
 * IMPORTANT: keep this in lock-step with backend bracket_seeding.py.
 * The R32 ext_id → match number map was hand-verified against the
 * official 2026 FIFA schedule; downstream stages use kickoff-sorted
 * index (FIFA publishes M89, M90, ... in chronological order).
 */

import type { Fixture } from '$types';
import {
	ROUND_OF_32,
	ROUND_OF_16,
	QUARTER_FINALS,
	SEMI_FINALS,
	FINAL,
	type KnockoutMatch
} from '$lib/config/bracketConfig';

// FixtureRead now carries external_id (v2.184.x backend addition). The
// barrel Fixture type is held by user WIP and can't be widened, so we
// cast at the consumption boundary inside this module.
type FixtureWithExt = Fixture & { external_id?: string | null };

// ── R32 ext_id → FIFA match number (v2.183.1). Hand-verified
//    against Wikipedia's 2026 FWC R32 schedule. Mirrors backend
//    EXT_ID_TO_MATCH_NUMBER exactly.
export const R32_EXT_ID_TO_MATCH_NUMBER: Record<string, number> = {
	'537417': 73,
	'537423': 76,
	'537415': 74,
	'537418': 75,
	'537424': 78,
	'537416': 77,
	'537425': 79,
	'537426': 80,
	'537422': 82,
	'537421': 81,
	'537420': 84,
	'537419': 83,
	'537429': 85,
	'537428': 88,
	'537427': 86,
	'537430': 87
};

const STAGE_FIRST_MATCH_NUMBER: Record<string, number> = {
	round_of_16: 89,
	quarter_final: 97,
	semi_final: 101,
	final: 104
};

/**
 * Given a Fixture and the full fixtures list, return the FIFA match
 * number this fixture corresponds to. Null for unrecognised cases
 * (e.g., third_place, group, data drift).
 *
 * For R32: looks up by external_id.
 * For R16+: kickoff-sorted index within stage + the stage's base.
 */
export function matchNumberOf(fixture: Fixture, allFixtures: Fixture[]): number | null {
	if (fixture.stage === 'round_of_32') {
		const ext = (fixture as FixtureWithExt).external_id;
		if (!ext) return null;
		return R32_EXT_ID_TO_MATCH_NUMBER[ext] ?? null;
	}
	const base = STAGE_FIRST_MATCH_NUMBER[fixture.stage];
	if (base === undefined) return null;
	const stageFixtures = allFixtures
		.filter((f) => f.stage === fixture.stage)
		.sort((a, b) => a.kickoff.localeCompare(b.kickoff));
	const idx = stageFixtures.findIndex((f) => f.id === fixture.id);
	return idx >= 0 ? base + idx : null;
}

/**
 * Reverse lookup: given a FIFA match number, return the Fixture row
 * (or undefined). Builds the index on demand from the fixtures list.
 */
export function buildMatchNumberIndex(allFixtures: Fixture[]): Map<number, Fixture> {
	const index = new Map<number, Fixture>();
	// R32 via ext_id
	for (const f of allFixtures) {
		const ext = (f as FixtureWithExt).external_id;
		if (f.stage === 'round_of_32' && ext) {
			const num = R32_EXT_ID_TO_MATCH_NUMBER[ext];
			if (num !== undefined) index.set(num, f);
		}
	}
	// R16/QF/SF/F via kickoff order
	for (const stage of ['round_of_16', 'quarter_final', 'semi_final', 'final']) {
		const base = STAGE_FIRST_MATCH_NUMBER[stage];
		const stageFixtures = allFixtures
			.filter((f) => f.stage === stage)
			.sort((a, b) => a.kickoff.localeCompare(b.kickoff));
		stageFixtures.forEach((f, i) => index.set(base + i, f));
	}
	return index;
}

/** Match numbers grouped by stage — fixed by FIFA's bracket structure. */
export function isStageMatch(num: number): KnockoutMatch['round'] | null {
	if (num >= 73 && num <= 88) return 'round_of_32';
	if (num >= 89 && num <= 96) return 'round_of_16';
	if (num >= 97 && num <= 100) return 'quarter_finals';
	if (num === 101 || num === 102) return 'semi_finals';
	if (num === 103) return 'third_place';
	if (num === 104) return 'final';
	return null;
}

/** Look up a bracket-config match definition by FIFA match number. */
function configFor(num: number): KnockoutMatch | undefined {
	if (num >= 73 && num <= 88) return ROUND_OF_32.find((m) => m.matchNumber === num);
	if (num >= 89 && num <= 96) return ROUND_OF_16.find((m) => m.matchNumber === num);
	if (num >= 97 && num <= 100) return QUARTER_FINALS.find((m) => m.matchNumber === num);
	if (num === 101 || num === 102) return SEMI_FINALS.find((m) => m.matchNumber === num);
	if (num === 104) return FINAL;
	return undefined;
}

/**
 * Given a child match's FIFA number, return the FIFA number of its
 * parent (the next-round match the child's winner feeds into). Walks
 * by scanning ROUND_OF_16/QF/SF/FINAL source descriptors.
 */
export function parentOf(childMatchNum: number): number | null {
	const stage = isStageMatch(childMatchNum);
	if (!stage) return null;
	let candidates: KnockoutMatch[];
	if (stage === 'round_of_32') candidates = ROUND_OF_16;
	else if (stage === 'round_of_16') candidates = QUARTER_FINALS;
	else if (stage === 'quarter_finals') candidates = SEMI_FINALS;
	else if (stage === 'semi_finals') return 104; // both SFs feed the Final (M104)
	else return null;

	for (const m of candidates) {
		if (
			(m.homeSource.type === 'winner' && m.homeSource.matchNumber === childMatchNum) ||
			(m.awaySource.type === 'winner' && m.awaySource.matchNumber === childMatchNum)
		) {
			return m.matchNumber;
		}
	}
	return null;
}

/**
 * Given a parent match's FIFA number, return the two child match
 * numbers (the two upstream matches whose winners feed it). Returns
 * null for R32 (no children) and for any source that isn't a winner
 * lookup (group/third_place — R32 lineup comes from group standings).
 */
export function childrenOf(parentMatchNum: number): [number, number] | null {
	const cfg = configFor(parentMatchNum);
	if (!cfg) return null;
	if (cfg.homeSource.type !== 'winner' || cfg.awaySource.type !== 'winner') return null;
	return [cfg.homeSource.matchNumber, cfg.awaySource.matchNumber];
}

/**
 * Sibling of an R32 match — the OTHER R32 whose winner feeds the
 * same R16. Returns null if the match has no R16 parent we recognise.
 */
export function r32SiblingOf(r32MatchNum: number): number | null {
	const r16Parent = parentOf(r32MatchNum);
	if (r16Parent === null) return null;
	const kids = childrenOf(r16Parent);
	if (!kids) return null;
	return kids[0] === r32MatchNum ? kids[1] : kids[0];
}

/**
 * Quadrant view for an R32 fixture, returned in FIFA WALLCHART ORDER
 * (top-to-bottom on the printed bracket), NOT "current match first"
 * (v2.184.x refactor). The render in BracketQuadrant.svelte then walks
 * `r32` / `r16` in array order and gets a layout that matches FIFA's
 * published bracket diagram regardless of which match the viewer is on.
 *
 * Walking rule: QF's children give the [top R16, bottom R16] pair in
 * wallchart order (QF source-order = FIFA order). Each R16's children
 * give the [top R32, bottom R32] pair, same rule. Flattening yields
 * 4 R32s in correct visual sequence.
 */
export interface R32Quadrant {
	/** 4 R32 match numbers in wallchart top-to-bottom order. */
	r32: [number, number, number, number];
	/** 2 R16 match numbers in wallchart order — top R16 feeds QF home,
	 *  bottom R16 feeds QF away. */
	r16: [number, number];
	qf: number;
}

export function r32QuadrantFor(r32MatchNum: number): R32Quadrant | null {
	const r16Parent = parentOf(r32MatchNum);
	if (r16Parent === null) return null;
	const qf = parentOf(r16Parent);
	if (qf === null) return null;

	// QF source order = FIFA wallchart order: first source is top, second is bottom.
	const r16Pair = childrenOf(qf);
	if (!r16Pair) return null;
	const [topR16, bottomR16] = r16Pair;

	// Each R16's children in FIFA order (top R32, bottom R32 of that R16's sub-bracket).
	const topR16Children = childrenOf(topR16);
	const bottomR16Children = childrenOf(bottomR16);
	if (!topR16Children || !bottomR16Children) return null;

	return {
		r32: [
			topR16Children[0],
			topR16Children[1],
			bottomR16Children[0],
			bottomR16Children[1]
		],
		r16: [topR16, bottomR16],
		qf
	};
}
