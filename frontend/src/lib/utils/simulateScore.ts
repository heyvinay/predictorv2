/**
 * Simulate a football scoreline from decimal head-to-head odds.
 *
 * Pipeline:
 *   1. Convert (home, draw, away) decimal odds → implied probabilities,
 *      stripping the bookmaker overround so the three sum to 1.
 *   2. Use a seeded PRNG to pick an outcome (home win / draw / away win).
 *   3. Pick a specific scoreline from a weighted table for that outcome.
 *
 * Determinism is the contract: same (odds, seed) always returns the same
 * `{ hs, as }`. Seeds are typically built from `${fixtureId}_${day}` via
 * `buildSeed()` so a user re-running Smart Fill on the same day gets the
 * same picks, but a new fixture or new day gives a fresh draw.
 *
 * The hashing and PRNG approach mirrors `smartFill.ts` (FNV-1a + mulberry32)
 * intentionally — the two modules don't share code because smartFill's
 * `seededRoll` is a single-shot variation roll while we need a multi-step
 * stream here. Kept structurally similar so a reader who knows one knows
 * the other.
 */

const MAX_GOALS = 15;

/**
 * Fast deterministic hash of a string to a non-negative 32-bit int.
 * FNV-1a — same algorithm as `smartFill.ts:hashString` for consistency.
 */
export function hashString(s: string): number {
	let h = 2166136261; // FNV offset basis
	for (let i = 0; i < s.length; i++) {
		h ^= s.charCodeAt(i);
		h = (h * 16777619) >>> 0; // FNV prime, force uint32
	}
	return h >>> 0;
}

/**
 * mulberry32 PRNG — returns a function that yields successive floats
 * in [0, 1) for the given seed. Unlike `smartFill.ts:seededRoll`
 * (single-shot), this returns a stream so we can draw outcome + scoreline
 * from the same seed.
 */
export function mulberry32(seed: number): () => number {
	let state = seed >>> 0;
	return () => {
		state = (state + 0x6d2b79f5) >>> 0;
		let t = state;
		t = Math.imul(t ^ (t >>> 15), t | 1);
		t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

/**
 * Convert decimal odds to fair probabilities, stripping the bookmaker
 * overround (the "vig"). Each raw probability is 1/odds; we normalise
 * so the three sum to 1.
 */
export function impliedProbabilities(
	home: number,
	draw: number,
	away: number
): { home: number; draw: number; away: number } {
	const ph = 1 / home;
	const pd = 1 / draw;
	const pa = 1 / away;
	const sum = ph + pd + pa;
	return { home: ph / sum, draw: pd / sum, away: pa / sum };
}

/**
 * Build a deterministic seed string. Day-level granularity (not hour)
 * so re-running Smart Fill on the same day gives stable picks.
 */
export function buildSeed(fixtureId: string, fetchedAtIso: string): string {
	const day = fetchedAtIso.slice(0, 10); // "YYYY-MM-DD"
	return `${fixtureId}_${day}`;
}

// Weighted scoreline tables. Numbers are relative weights (not %).
// Stronger team's score is first in each tuple, weaker team's second.
// Tables stay well under MAX_GOALS so the clamp is purely defensive.
const WIN_SCORES: Array<[number, number, number]> = [
	[1, 0, 25],
	[2, 0, 20],
	[2, 1, 18],
	[3, 0, 10],
	[3, 1, 10],
	[3, 2, 6],
	[4, 1, 5],
	[4, 0, 4],
	[5, 0, 2]
];
const DRAW_SCORES: Array<[number, number, number]> = [
	[1, 1, 40],
	[0, 0, 25],
	[2, 2, 20],
	[3, 3, 10],
	[4, 4, 5]
];

function pickWeighted(
	rand: () => number,
	table: Array<[number, number, number]>
): [number, number] {
	const total = table.reduce((s, [, , w]) => s + w, 0);
	let r = rand() * total;
	for (const [a, b, w] of table) {
		r -= w;
		if (r <= 0) return [a, b];
	}
	const [a, b] = table[table.length - 1];
	return [a, b];
}

const clamp = (n: number) => Math.min(MAX_GOALS, Math.max(0, n));

/**
 * Pick a scoreline from decimal h2h odds and a numeric seed.
 *
 * @returns `{ hs, as }` — home/away score in the same convention as
 *   smartFillScoreline. Each value is clamped to [0, MAX_GOALS].
 */
export function simulateScore(
	homeOdds: number,
	drawOdds: number,
	awayOdds: number,
	seed: number
): { hs: number; as: number } {
	const rand = mulberry32(seed);
	const { home, draw, away } = impliedProbabilities(homeOdds, drawOdds, awayOdds);

	// 1. Pick outcome by probability
	const r = rand();
	let outcome: 'home' | 'draw' | 'away';
	if (r < home) outcome = 'home';
	else if (r < home + draw) outcome = 'draw';
	else outcome = 'away';

	// 2. Pick scoreline from the corresponding table
	if (outcome === 'draw') {
		const [a, b] = pickWeighted(rand, DRAW_SCORES);
		return { hs: clamp(a), as: clamp(b) };
	}
	const [winner, loser] = pickWeighted(rand, WIN_SCORES);
	return outcome === 'home'
		? { hs: clamp(winner), as: clamp(loser) }
		: { hs: clamp(loser), as: clamp(winner) };
}
