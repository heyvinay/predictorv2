/**
 * Bracket-progress helpers. Ported verbatim from upstream
 * laarohi/predictorv2 (which uses it for the Phase 1 dashboard
 * countdown bar). Pure utility; both wizard and dashboard surfaces
 * benefit from a single source of truth on "how many of the 63
 * knockout slots is this entry's bracket filled?"
 *
 * The 63 = 16 (R32) + 8 (R16) + 4 (QF) + 2 (SF) + 1 (Final) + 1 (Winner).
 * Group-stage match predictions and group_position picks are scored
 * separately and don't count here.
 */

import type { BracketPrediction } from '$types';

export const BRACKET_TOTAL_SLOTS = 63;

export interface BracketProgress {
	done: number;
	total: number;
}

export function countBracketSlotsFilled(b: BracketPrediction | null): BracketProgress {
	const total = BRACKET_TOTAL_SLOTS;
	if (!b) return { done: 0, total };
	let done = 0;
	for (const arr of [b.round_of_32, b.round_of_16, b.quarter_finals, b.semi_finals, b.final]) {
		for (const t of arr || []) if (t) done++;
	}
	if (b.winner) done++;
	return { done, total };
}
