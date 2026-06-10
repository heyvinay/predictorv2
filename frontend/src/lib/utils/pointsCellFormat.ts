/**
 * Pure formatting logic for the V4 per-fixture points cells.
 *
 * Extracted from the Svelte components so vitest can pin the display
 * matrix (spec D.2) without a component-render harness — the repo's
 * test stack is pure-TS vitest, no @testing-library.
 */

import type { PickPoints } from '$lib/types/results';

export interface GroupCellFormat {
	/** null → render a muted em-dash, no pill. */
	pill: {
		label: 'EXACT' | 'RESULT' | 'MISS';
		display: string; // "+18" | "0"
		tone: 'exact' | 'result' | 'miss';
		showRarityStar: boolean;
		rarityTitle: string | null;
	} | null;
}

/** Group-round cell: `—` until the backend banks points (fixture
 *  FINISHED); EXACT/RESULT/MISS pill with signed total afterwards. */
export function formatGroupCell(points: PickPoints | null | undefined): GroupCellFormat {
	if (!points) return { pill: null };
	const tone =
		points.base_kind === 'exact' ? 'exact' : points.base_kind === 'result' ? 'result' : 'miss';
	const label = points.base_kind === 'exact' ? 'EXACT' : points.base_kind === 'result' ? 'RESULT' : 'MISS';
	return {
		pill: {
			label,
			display: points.total > 0 ? `+${points.total}` : `${points.total}`,
			tone,
			showRarityStar: points.rarity > 0,
			rarityTitle: points.rarity > 0 ? `Includes +${points.rarity} rarity bonus` : null
		}
	};
}

export interface KoCellFormat {
	/** null → render a muted em-dash (third_place / unseeded). */
	line: {
		breakdown: string; // "+20×2:"
		total: number;
		tone: 'full' | 'half' | 'none';
	} | null;
}

/** KO cell: `+{stagePts}×{hits}: {total}` — lineup-banked, so it renders
 *  for scheduled and live fixtures too. Not applicable → dash. */
export function formatKoCell(
	stagePoints: number,
	hits: number,
	applicable: boolean
): KoCellFormat {
	if (!applicable) return { line: null };
	return {
		line: {
			breakdown: `+${stagePoints}×${hits}:`,
			total: stagePoints * hits,
			tone: hits === 2 ? 'full' : hits === 1 ? 'half' : 'none'
		}
	};
}
