/**
 * Team-name normaliser and odds extractor.
 *
 * The Odds API and our tournament config (`config/worldcup2026.yml`) don't
 * always agree on spelling — "USA" vs "United States", "Korea Republic"
 * vs "South Korea", etc. This module canonicalises both sides to a common
 * form (lowercased, trimmed, alias-resolved) before comparing.
 *
 * Adding new aliases: extend ALIASES below. Keys are *variations* (any
 * spelling the API might emit); values are the canonical name as used in
 * `worldcup2026.yml`. Matching is case-insensitive and whitespace-tolerant
 * so e.g. "USA" and "u.s.a" don't both need entries — but punctuation
 * differences do.
 */

import type { OddsApiMatch } from './oddsCache';

/**
 * API variation → canonical (worldcup2026.yml) name.
 * Mirrors the alias conventions already in `smartFill.ts:FIFA_POINTS`.
 */
const ALIASES: Record<string, string> = {
	// United States
	USA: 'United States',
	'United States of America': 'United States',
	// South Korea
	'Korea Republic': 'South Korea',
	// Ivory Coast — not in WC26 groups but harmless to keep
	"Cote d'Ivoire": 'Ivory Coast',
	// Czechia
	'Czech Republic': 'Czechia',
	// Cape Verde
	'Cape Verde Islands': 'Cape Verde',
	// Bosnia
	'Bosnia-Herzegovina': 'Bosnia and Herzegovina'
};

function normalize(name: string): string {
	return name.trim().toLowerCase().replace(/\s+/g, ' ');
}

/**
 * Resolve a team name to its canonical form. Idempotent: calling on an
 * already-canonical name returns the same normalised form.
 */
export function canonicalize(name: string): string {
	const norm = normalize(name);
	for (const [variant, canonical] of Object.entries(ALIASES)) {
		if (normalize(variant) === norm) return normalize(canonical);
	}
	return norm;
}

/**
 * Find the API match for a fixture by team-pair (order-sensitive: home
 * must match home). Returns null if no match.
 */
export function findOddsForFixture(
	fixture: { home_team: string; away_team: string },
	apiMatches: OddsApiMatch[]
): OddsApiMatch | null {
	const fHome = canonicalize(fixture.home_team);
	const fAway = canonicalize(fixture.away_team);
	return (
		apiMatches.find(
			(m) =>
				canonicalize(m.home_team) === fHome && canonicalize(m.away_team) === fAway
		) ?? null
	);
}

/**
 * Extract averaged head-to-head decimal odds from all bookmakers for a
 * given match. Skips bookmakers missing the h2h market or any of the
 * three outcomes. Averaging (vs min/max/median) reduces single-bookmaker
 * bias and smooths transient line moves.
 *
 * @returns `{ home, draw, away }` — averaged decimal odds, or `null` if
 *   no bookmaker had a complete h2h market.
 */
export function extractH2HOdds(
	match: OddsApiMatch
): { home: number; draw: number; away: number } | null {
	const homeCanon = canonicalize(match.home_team);
	const awayCanon = canonicalize(match.away_team);

	const homePrices: number[] = [];
	const drawPrices: number[] = [];
	const awayPrices: number[] = [];

	for (const bm of match.bookmakers) {
		const h2h = bm.markets.find((mk) => mk.key === 'h2h');
		if (!h2h || h2h.outcomes.length < 3) continue;

		let homePrice: number | undefined;
		let drawPrice: number | undefined;
		let awayPrice: number | undefined;

		for (const outcome of h2h.outcomes) {
			const n = canonicalize(outcome.name);
			if (n === 'draw') drawPrice = outcome.price;
			else if (n === homeCanon) homePrice = outcome.price;
			else if (n === awayCanon) awayPrice = outcome.price;
		}

		if (homePrice === undefined || drawPrice === undefined || awayPrice === undefined) {
			continue;
		}
		homePrices.push(homePrice);
		drawPrices.push(drawPrice);
		awayPrices.push(awayPrice);
	}

	if (homePrices.length === 0) return null;

	const avg = (arr: number[]) => arr.reduce((s, n) => s + n, 0) / arr.length;
	return {
		home: avg(homePrices),
		draw: avg(drawPrices),
		away: avg(awayPrices)
	};
}
