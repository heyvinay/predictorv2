/**
 * Rarity-explainer microcopy — the four locked templates (spec D.4).
 *
 * Spec D.4 assumed these would render server-side in a RarityDetailOut
 * endpoint; that endpoint was never built (client-side composition won),
 * so the templates live here as the single source of truth instead.
 * Wording is LOCKED — change only with a spec amendment.
 */

export interface RarityNoteInput {
	/** Entries (incl. you) that called the same 1/X/2 outcome. */
	n: number;
	/** Eligible pool size for this fixture. */
	total: number;
	/** Rarity bonus that outcome earns (0 in the consensus zone). */
	pts: number;
	/** True once the fixture is FINISHED — switches to the banked variant. */
	finished: boolean;
}

/** One-decimal percentage, trailing ".0" trimmed (9.7% / 50%). */
function pct(n: number, total: number): string {
	const value = (n / total) * 100;
	const rounded = Math.round(value * 10) / 10;
	return `${rounded % 1 === 0 ? rounded.toFixed(0) : rounded.toFixed(1)}%`;
}

export function rarityNote(input: RarityNoteInput): string | null {
	const { n, total, pts, finished } = input;
	if (total <= 0 || n <= 0) return null;

	if (pts <= 0) {
		return `Your outcome was the popular call (${n} of ${total}, ${pct(n, total)}) — no rarity bonus on consensus picks.`;
	}
	if (n === 1) {
		return finished
			? `Only you out of ${total} entries called this outcome — banked +${pts} rarity.`
			: `Only you out of ${total} entries called this outcome — you'd earn +${pts} rarity if it holds.`;
	}
	return finished
		? `Only ${n} of ${total} entries called this outcome (${pct(n, total)}) — banked +${pts} rarity.`
		: `Only ${n} of ${total} entries called this outcome (${pct(n, total)}) — you'd earn +${pts} rarity if it holds.`;
}
