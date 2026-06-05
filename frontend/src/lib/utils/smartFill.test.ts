import { describe, expect, it } from 'vitest';

import { fifaPoints, smartFillScoreline, pickHigherRanked } from './smartFill';
import fifaRankings from '$lib/data/fifaRankings.json';

/**
 * Tests for the §7-A refactor (2026-06-05): FIFA_POINTS extracted to
 * fifaRankings.json, lookups routed through teamMatch.ts:canonicalize().
 *
 * Critical contract: fixture-YAML spellings ("South Korea", "Czech Republic",
 * "Iran", "Ivory Coast", "United States", "Turkey", "Cape Verde", "DR Congo")
 * must resolve to the same points value as FIFA's canonical spellings
 * ("Korea Republic", "Czechia", "IR Iran", "Côte d'Ivoire", "USA", "Türkiye",
 * "Cabo Verde", "Congo DR") — otherwise the FIFA Smart Fill path will return
 * the 1300 default for half the WC2026 teams.
 */

describe('fifaPoints (post §7-A refactor)', () => {
	it('returns the JSON value for a team named exactly as FIFA spells it', () => {
		// Argentina is FIFA's spelling AND the YAML's spelling — identity case.
		const argPts = fifaRankings.points['Argentina' as keyof typeof fifaRankings.points];
		expect(fifaPoints('Argentina')).toBe(argPts);
	});

	it('returns 1300 default for an unknown team', () => {
		expect(fifaPoints('Atlantis')).toBe(1300);
		expect(fifaPoints('')).toBe(1300);
		expect(fifaPoints('NotARealTeam')).toBe(1300);
	});

	it('aliased: South Korea (YAML) resolves to Korea Republic (FIFA)', () => {
		const koreaRepublicPts =
			fifaRankings.points['Korea Republic' as keyof typeof fifaRankings.points];
		expect(koreaRepublicPts).toBeGreaterThan(0); // FIFA does have this spelling
		expect(fifaPoints('South Korea')).toBe(koreaRepublicPts);
		expect(fifaPoints('Korea Republic')).toBe(koreaRepublicPts); // idempotent
	});

	it('aliased: Czech Republic (YAML) resolves to Czechia (FIFA)', () => {
		const czPts = fifaRankings.points['Czechia' as keyof typeof fifaRankings.points];
		expect(czPts).toBeGreaterThan(0);
		expect(fifaPoints('Czech Republic')).toBe(czPts);
		expect(fifaPoints('Czechia')).toBe(czPts);
	});

	it('aliased: United States (YAML) resolves to USA (FIFA)', () => {
		const usaPts = fifaRankings.points['USA' as keyof typeof fifaRankings.points];
		expect(usaPts).toBeGreaterThan(0);
		expect(fifaPoints('United States')).toBe(usaPts);
		expect(fifaPoints('USA')).toBe(usaPts);
	});

	it('aliased: Turkey (YAML) resolves to Türkiye (FIFA)', () => {
		const tukPts = fifaRankings.points['Türkiye' as keyof typeof fifaRankings.points];
		expect(tukPts).toBeGreaterThan(0);
		expect(fifaPoints('Turkey')).toBe(tukPts);
		expect(fifaPoints('Türkiye')).toBe(tukPts);
	});

	it('aliased: Ivory Coast (YAML) resolves to Côte d\'Ivoire (FIFA)', () => {
		const ciPts =
			fifaRankings.points["Côte d'Ivoire" as keyof typeof fifaRankings.points];
		expect(ciPts).toBeGreaterThan(0);
		expect(fifaPoints('Ivory Coast')).toBe(ciPts);
		expect(fifaPoints("Côte d'Ivoire")).toBe(ciPts);
		expect(fifaPoints("Cote d'Ivoire")).toBe(ciPts); // accent-stripped form too
	});

	it('aliased: Iran (YAML) resolves to IR Iran (FIFA)', () => {
		const irPts = fifaRankings.points['IR Iran' as keyof typeof fifaRankings.points];
		expect(irPts).toBeGreaterThan(0);
		expect(fifaPoints('Iran')).toBe(irPts);
		expect(fifaPoints('IR Iran')).toBe(irPts);
	});

	it('aliased: Cape Verde (YAML) resolves to Cabo Verde (FIFA)', () => {
		const cvPts =
			fifaRankings.points['Cabo Verde' as keyof typeof fifaRankings.points];
		expect(cvPts).toBeGreaterThan(0);
		expect(fifaPoints('Cape Verde')).toBe(cvPts);
		expect(fifaPoints('Cabo Verde')).toBe(cvPts);
	});

	it('aliased: DR Congo (YAML) resolves to Congo DR (FIFA)', () => {
		const drcPts =
			fifaRankings.points['Congo DR' as keyof typeof fifaRankings.points];
		expect(drcPts).toBeGreaterThan(0);
		expect(fifaPoints('DR Congo')).toBe(drcPts);
		expect(fifaPoints('Congo DR')).toBe(drcPts);
	});
});

describe('smartFillScoreline (post §7-A refactor)', () => {
	it('produces a deterministic [home, away] tuple for a fixed (user, fixture) pair', () => {
		const a = smartFillScoreline('Argentina', 'Saudi Arabia', 'user-42', 'fix-1');
		const b = smartFillScoreline('Argentina', 'Saudi Arabia', 'user-42', 'fix-1');
		expect(a).toEqual(b);
	});

	it('honours "stronger team always wins" — Argentina beats Saudi Arabia', () => {
		// Massive points gap → Argentina always wins, scoreline varies per seed.
		// Verifies the refactor preserved the orientation logic.
		for (let i = 0; i < 50; i++) {
			const [home, away] = smartFillScoreline(
				'Argentina',
				'Saudi Arabia',
				`user-${i}`,
				`fix-${i}`
			);
			expect(home).toBeGreaterThan(away);
		}
	});

	it('respects fixture-YAML spellings — same result for "South Korea" as for FIFA-side calls', () => {
		// Two equivalent fixtures: one named in YAML style, one in FIFA style.
		// The seeded variation should be the same because both resolve to the
		// same canonical points.
		const ykorea = smartFillScoreline('South Korea', 'Japan', 'user-9', 'fix-9');
		const fkorea = smartFillScoreline('Korea Republic', 'Japan', 'user-9', 'fix-9');
		expect(ykorea).toEqual(fkorea);
	});
});

describe('pickHigherRanked (post §7-A refactor)', () => {
	it('picks the higher-ranked team', () => {
		// Argentina >> Saudi Arabia
		expect(pickHigherRanked('Argentina', 'Saudi Arabia', 'u1', 'm1')).toBe('Argentina');
		// Order-insensitive
		expect(pickHigherRanked('Saudi Arabia', 'Argentina', 'u1', 'm1')).toBe('Argentina');
	});

	it('aliased lookups produce the same winner (canonically)', () => {
		// Two equivalent calls — one with YAML spellings, one with FIFA spellings.
		// pickHigherRanked returns the input form (whichever side won), so the
		// raw strings differ, but the canonical forms must match (i.e. both
		// resolve to the same team).
		const w1 = pickHigherRanked('South Korea', 'Iran', 'u1', 'm1');
		const w2 = pickHigherRanked('Korea Republic', 'IR Iran', 'u1', 'm1');
		// Lazy canonicalize import for test brevity:
		// w1 = 'Iran' (Iran wins on points), w2 = 'IR Iran' (same team, FIFA spelling).
		// Both must lookup to the same fifaPoints value.
		expect(fifaPoints(w1)).toBe(fifaPoints(w2));
	});
});
